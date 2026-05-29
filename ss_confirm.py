"""
SS-Confirm: Single Source Appointment Confirmation Workflow
Automated intake for Mobile Signing Agency

Flow:
1. Monitor Gmail for closing confirmations from closings@singlesourceproperty.com
2. Extract document link and order details
3. Log in to SingleSource portal with credentials
4. Handle MFA verification (same browser session)
5. Download HTM file
6. Submit to Mobile Signing Agency webhook
"""

import os
import re
import time
import json
import base64
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

import aiohttp
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from playwright.async_api import async_playwright, Browser, Page

# Configure logging
log_dir = os.getenv('LOG_DIR', '/var/log/ss-confirm')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'ss_confirm.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    """SS-Confirm configuration from environment."""
    
    # Base directory (Docker-friendly)
    BASE_DIR = os.getenv('BASE_DIR', '/opt/ss-confirm')
    
    # Gmail OAuth
    GMAIL_OAUTH_CREDENTIALS_FILE = os.getenv('GMAIL_OAUTH_CREDENTIALS_FILE', os.path.join(BASE_DIR, 'credentials.json'))
    GMAIL_TOKEN_FILE = os.getenv('GMAIL_TOKEN_FILE', os.path.join(BASE_DIR, 'token.pickle'))
    GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    
    # SingleSource Portal
    SINGLESOURCE_USERNAME = os.getenv('SINGLESOURCE_USERNAME', 'Hesham.ahsan@gmail.com')
    SINGLESOURCE_PASSWORD = os.getenv('SINGLESOURCE_PASSWORD', '')
    SINGLESOURCE_USERNAME_FIELD = 'username'
    SINGLESOURCE_PASSWORD_FIELD = 'password'
    
    # Mobile Signing Agency Webhook
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://msaok.base44.app/api/functions/webhookCreateSigning')
    WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'cqsstSfDIYg1YiYZQAx9ag-bLpmc9ElEUYeLp9t0QT4')
    
    # Download directory (Docker-friendly)
    DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', os.path.join(BASE_DIR, 'downloads'))
    
    # MFA timeout (seconds)
    MFA_TIMEOUT = int(os.getenv('MFA_TIMEOUT', '300'))  # 5 minutes
    
    # Email monitoring
    MONITORED_EMAIL = os.getenv('MONITORED_EMAIL', 'closings@singlesourceproperty.com')
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))  # 5 minutes


class GmailMonitor:
    """Monitor Gmail for SingleSource closing confirmations."""
    
    def __init__(self):
        self.service = None
        self.processed_messages = set()
    
    def get_gmail_service(self):
        """Authenticate and return Gmail API service."""
        if self.service:
            return self.service
        
        creds = None
        
        # Load token if exists
        import pickle
        if os.path.exists(Config.GMAIL_TOKEN_FILE):
            with open(Config.GMAIL_TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)
        
        # Refresh or re-authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    Config.GMAIL_OAUTH_CREDENTIALS_FILE,
                    Config.GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save token for next run
            import pickle
            with open(Config.GMAIL_TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
        
        self.service = build('gmail', 'v1', credentials=creds)
        return self.service
    
    def get_unread_from_singlesource(self) -> list:
        """Fetch unread emails from SingleSource."""
        service = self.get_gmail_service()
        
        try:
            # Query: from singlesourceproperty.com AND unread AND "Closing Order Confirmation"
            query = f'from:{Config.MONITORED_EMAIL} is:unread subject:"Closing Order Confirmation"'
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=10
            ).execute()
            
            messages = results.get('messages', [])
            logger.info(f"Found {len(messages)} unread SingleSource emails")
            return messages
        
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            return []
    
    def get_message_body(self, message_id: str) -> Dict[str, Any]:
        """Extract message body and metadata."""
        service = self.get_gmail_service()
        
        try:
            msg = service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            headers = {h['name']: h['value'] for h in msg['payload']['headers']}
            
            # Extract HTML body
            body = ''
            if 'parts' in msg['payload']:
                for part in msg['payload']['parts']:
                    if part['mimeType'] == 'text/html':
                        data = part['body'].get('data', '')
                        if data:
                            body = base64.urlsafe_b64decode(data).decode('utf-8')
                            break
            else:
                data = msg['payload']['body'].get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
            
            return {
                'id': message_id,
                'subject': headers.get('Subject', ''),
                'from': headers.get('From', ''),
                'date': headers.get('Date', ''),
                'body': body
            }
        
        except Exception as e:
            logger.error(f"Error extracting message {message_id}: {e}")
            return {}
    
    def parse_confirmation_email(self, msg_body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse closing confirmation email and extract key data."""
        html = msg_body.get('body', '')
        
        # Extract document link
        link_match = re.search(
            r'href="(https://ss\.propertysmart\.us/modules/open_file\.aspx[^"]+)"',
            html
        )
        if not link_match:
            logger.warning("No document link found in email")
            return None
        
        document_link = link_match.group(1)
        
        # Extract order number (from href fname parameter)
        fname_match = re.search(r'fname=([^"&]+)', document_link)
        order_file = fname_match.group(1) if fname_match else 'unknown'
        
        # Extract order number from subject
        subject = msg_body.get('subject', '')
        order_match = re.search(r'Order Number (\d+-[A-Z]+)', subject)
        order_number = order_match.group(1) if order_match else 'unknown'
        
        # Extract closing date
        date_match = re.search(r'(\d+/\d+/\d+\s+\d+:\d+:\d+\s+[AP]M)', subject)
        closing_date = date_match.group(1) if date_match else 'unknown'
        
        # Extract location
        location_match = re.search(r'-\s+([^-]+),([A-Z]{2})-', subject)
        location = f"{location_match.group(1)}, {location_match.group(2)}" if location_match else 'unknown'
        
        # Extract borrower info
        borrower_match = re.search(r'<br>([A-Z\s]+)<br>(\d+)<br>([^<]+@[^<]+)', html)
        borrower = borrower_match.group(1) if borrower_match else 'unknown'
        phone = borrower_match.group(2) if borrower_match else 'unknown'
        email = borrower_match.group(3) if borrower_match else 'unknown'
        
        # Extract fee
        fee_match = re.search(r'Agreed upon fee[^$]*\$([0-9.]+)', html)
        fee = fee_match.group(1) if fee_match else '0.00'
        
        return {
            'order_number': order_number,
            'order_file': order_file,
            'document_link': document_link,
            'closing_date': closing_date,
            'location': location,
            'borrower': borrower,
            'phone': phone,
            'email': email,
            'fee': fee,
            'message_id': msg_body.get('id', ''),
            'timestamp': datetime.now().isoformat()
        }


class MFAHandler:
    """Handle MFA verification during login."""
    
    def __init__(self, gmail_monitor: GmailMonitor):
        self.gmail = gmail_monitor
        self.mfa_code = None
    
    async def wait_for_mfa_code(self, timeout: int = 300) -> Optional[str]:
        """
        Poll Gmail for MFA code email while browser waits.
        Returns 6-character verification code.
        """
        logger.info(f"Waiting for MFA code (timeout: {timeout}s)")
        
        service = self.gmail.get_gmail_service()
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Query for recent emails from SingleSource VM
                query = 'from:VM@singlesourceproperty.com subject:"Verification Code" is:unread'
                results = service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=1
                ).execute()
                
                messages = results.get('messages', [])
                if messages:
                    msg_id = messages[0]['id']
                    msg = service.users().messages().get(
                        userId='me',
                        id=msg_id,
                        format='full'
                    ).execute()
                    
                    # Extract body
                    body = ''
                    if 'parts' in msg['payload']:
                        for part in msg['payload']['parts']:
                            if part['mimeType'] == 'text/plain':
                                data = part['body'].get('data', '')
                                if data:
                                    body = base64.urlsafe_b64decode(data).decode('utf-8')
                                    break
                    else:
                        data = msg['payload']['body'].get('data', '')
                        if data:
                            body = base64.urlsafe_b64decode(data).decode('utf-8')
                    
                    # Extract code (6 chars before "is your SingleSource verification code")
                    code_match = re.search(r'(\w{6})\s+is your SingleSource verification code', body)
                    if code_match:
                        code = code_match.group(1)
                        logger.info(f"MFA code found: {code}")
                        
                        # Mark as read
                        service.users().messages().modify(
                            userId='me',
                            id=msg_id,
                            body={'removeLabelIds': ['UNREAD']}
                        ).execute()
                        
                        return code
            
            except Exception as e:
                logger.warning(f"Error polling for MFA: {e}")
            
            await asyncio.sleep(5)  # Poll every 5 seconds
        
        logger.error("MFA code not received within timeout")
        return None


class BrowserAutomation:
    """Handle browser automation for SingleSource login and file download."""
    
    def __init__(self, mfa_handler: MFAHandler):
        self.mfa = mfa_handler
        self.browser = None
        self.page = None
    
    async def login_and_download(self, document_link: str) -> Optional[str]:
        """
        Complete login flow and download HTM file.
        Returns path to downloaded file.
        """
        try:
            async with async_playwright() as p:
                self.browser = await p.chromium.launch(headless=True)
                self.page = await self.browser.new_page()
                
                # Create download directory
                os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
                
                logger.info(f"Opening document link: {document_link}")
                await self.page.goto(document_link, wait_until='networkidle')
                
                # Wait for login form
                await self.page.wait_for_selector('input[name="username"]', timeout=10000)
                
                # Fill credentials
                logger.info("Filling login credentials")
                await self.page.fill('input[name="username"]', Config.SINGLESOURCE_USERNAME)
                await self.page.fill('input[name="password"]', Config.SINGLESOURCE_PASSWORD)
                
                # Submit login
                await self.page.click('button[type="submit"]')
                
                # Wait for MFA or document page
                logger.info("Waiting for MFA prompt or document")
                await asyncio.sleep(2)
                
                # Check if MFA page appeared
                mfa_field = await self.page.query_selector('input[name*="mfa"], input[name*="verification"], input[name*="code"]')
                if mfa_field:
                    logger.info("MFA field detected, polling for code")
                    # Start MFA polling
                    mfa_task = asyncio.create_task(self.mfa.wait_for_mfa_code(Config.MFA_TIMEOUT))
                    
                    # Wait for MFA code
                    mfa_code = await mfa_task
                    if not mfa_code:
                        logger.error("Failed to get MFA code")
                        return None
                    
                    # Fill and submit MFA
                    logger.info("Submitting MFA code")
                    await self.page.fill('input[name*="mfa"], input[name*="verification"], input[name*="code"]', mfa_code)
                    await self.page.click('button[type="submit"]')
                    await asyncio.sleep(2)
                
                # Wait for document or download button
                logger.info("Waiting for document to load")
                await self.page.wait_for_load_state('networkidle')
                
                # Try to download HTM file
                # Option 1: Direct HTM file link
                htm_link = await self.page.query_selector('a[href*=".htm"]')
                if htm_link:
                    logger.info("Found HTM link, downloading")
                    async with self.page.expect_download() as download_info:
                        await htm_link.click()
                    download = await download_info.value
                    filepath = os.path.join(Config.DOWNLOAD_DIR, download.suggested_filename)
                    await download.save_as(filepath)
                    logger.info(f"File downloaded: {filepath}")
                    return filepath
                
                # Option 2: Check if page content is HTM
                content = await self.page.content()
                if content.startswith('<!DOCTYPE') or content.startswith('<html'):
                    filename = f"closing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.htm"
                    filepath = os.path.join(Config.DOWNLOAD_DIR, filename)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.info(f"HTM content saved: {filepath}")
                    return filepath
                
                logger.error("Could not find HTM file to download")
                return None
        
        except Exception as e:
            logger.error(f"Browser automation error: {e}")
            return None
        
        finally:
            if self.browser:
                await self.browser.close()
    
    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()


class WebhookSubmitter:
    """Submit downloaded HTM file to Mobile Signing Agency webhook."""
    
    async def submit(self, filepath: str, order_data: Dict[str, Any]) -> bool:
        """
        POST HTM file to webhook endpoint.
        Includes order metadata and webhook secret.
        """
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return False
        
        try:
            with open(filepath, 'rb') as f:
                htm_content = f.read()
            
            # Prepare payload
            payload = {
                'webhook_secret': Config.WEBHOOK_SECRET,
                'order_number': order_data.get('order_number'),
                'borrower': order_data.get('borrower'),
                'email': order_data.get('email'),
                'phone': order_data.get('phone'),
                'closing_date': order_data.get('closing_date'),
                'location': order_data.get('location'),
                'fee': order_data.get('fee'),
                'htm_content': base64.b64encode(htm_content).decode('utf-8'),
                'htm_filename': os.path.basename(filepath),
                'submitted_at': datetime.now().isoformat()
            }
            
            logger.info(f"Submitting to webhook: {Config.WEBHOOK_URL}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    Config.WEBHOOK_URL,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200 or resp.status == 201:
                        logger.info(f"Webhook submission successful (status: {resp.status})")
                        result = await resp.json()
                        logger.info(f"Webhook response: {result}")
                        return True
                    else:
                        logger.error(f"Webhook submission failed (status: {resp.status})")
                        text = await resp.text()
                        logger.error(f"Response: {text}")
                        return False
        
        except Exception as e:
            logger.error(f"Webhook submission error: {e}")
            return False


class SSConfirmWorkflow:
    """Main workflow orchestrator."""
    
    def __init__(self):
        self.gmail = GmailMonitor()
        self.mfa = MFAHandler(self.gmail)
        self.browser = BrowserAutomation(self.mfa)
        self.webhook = WebhookSubmitter()
        self.processed = set()
    
    async def process_email(self, message_id: str) -> bool:
        """Process a single confirmation email."""
        if message_id in self.processed:
            logger.debug(f"Message {message_id} already processed")
            return False
        
        try:
            # Fetch and parse email
            msg_body = self.gmail.get_message_body(message_id)
            if not msg_body:
                return False
            
            order_data = self.gmail.parse_confirmation_email(msg_body)
            if not order_data:
                logger.warning(f"Could not parse email {message_id}")
                return False
            
            logger.info(f"Processing order: {order_data.get('order_number')}")
            
            # Login and download
            filepath = await self.browser.login_and_download(order_data.get('document_link'))
            if not filepath:
                logger.error("Failed to download file")
                return False
            
            # Submit to webhook
            success = await self.webhook.submit(filepath, order_data)
            
            if success:
                self.processed.add(message_id)
                logger.info(f"Order {order_data.get('order_number')} completed successfully")
                
                # Mark email as read
                service = self.gmail.get_gmail_service()
                service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()
            
            return success
        
        except Exception as e:
            logger.error(f"Error processing email {message_id}: {e}")
            return False
    
    async def run_once(self):
        """Check for new emails and process them."""
        logger.info("Checking for new SingleSource emails")
        messages = self.gmail.get_unread_from_singlesource()
        
        for msg in messages:
            await self.process_email(msg['id'])
    
    async def run_continuous(self, interval: int = 300):
        """Run continuous monitoring loop."""
        logger.info(f"Starting continuous monitoring (interval: {interval}s)")
        
        while True:
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            logger.info(f"Next check in {interval}s")
            await asyncio.sleep(interval)


async def main():
    """Entry point."""
    import sys
    
    # Verify credentials password is set
    if not Config.SINGLESOURCE_PASSWORD:
        logger.error("SINGLESOURCE_PASSWORD not set in environment")
        sys.exit(1)
    
    workflow = SSConfirmWorkflow()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--continuous':
        # Run continuous monitoring
        await workflow.run_continuous(Config.CHECK_INTERVAL)
    else:
        # Run once
        await workflow.run_once()


if __name__ == '__main__':
    asyncio.run(main())
