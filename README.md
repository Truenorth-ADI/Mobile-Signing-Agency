# SS-Confirm: Single Source Appointment Confirmation Workflow

Automated intake for Mobile Signing Agency. Monitors Gmail for closing confirmations, logs in, handles MFA, downloads documents, and submits to webhook.

## Quick Start

### 1. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Setup Gmail OAuth

```bash
# Get OAuth credentials from Google Cloud Console
# Save as credentials.json in this directory
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 4. Run

**Once (check emails immediately):**
```bash
python3 ss_confirm.py
```

**Continuous (monitor every 5 minutes):**
```bash
python3 ss_confirm.py --continuous
```

## Workflow

```
📧 Email arrives from closings@singlesourceproperty.com
    ↓
🔍 Extract: Order #, Link, Borrower, Fee
    ↓
🌐 Browser: Open link
    ↓
🔐 Login: Hesham.ahsan@gmail.com + password
    ↓
📱 MFA: Poll Gmail for verification code
    ↓
✅ Submit: MFA code (same session)
    ↓
💾 Download: HTM file
    ↓
🚀 Webhook: POST to Mobile Signing Agency
    ↓
✔️ Success: Mark email as read, log result
```

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `GMAIL_OAUTH_CREDENTIALS_FILE` | `credentials.json` | Google OAuth credentials |
| `SINGLESOURCE_USERNAME` | `Hesham.ahsan@gmail.com` | Login username |
| `SINGLESOURCE_PASSWORD` | *(required)* | Login password |
| `WEBHOOK_URL` | `https://msaok.base44.app/...` | Webhook endpoint |
| `WEBHOOK_SECRET` | *(from Hesham)* | Webhook authentication |
| `DOWNLOAD_DIR` | `./downloads` | HTM file download location |
| `MFA_TIMEOUT` | `300` | MFA code wait timeout (seconds) |
| `CHECK_INTERVAL` | `300` | Email check interval (seconds) |
| `MONITORED_EMAIL` | `closings@singlesourceproperty.com` | Source email address |

## Features

✅ **Email Monitoring** — Gmail OAuth, unread filtering  
✅ **Document Parsing** — Extract order number, borrower, date, location, fee  
✅ **Browser Automation** — Playwright headless browser  
✅ **Credential Management** — Secure environment variable handling  
✅ **MFA Support** — Email-based OTP extraction, same-session verification  
✅ **File Download** — HTM file handling with base64 encoding  
✅ **Webhook Submission** — Async POST with metadata  
✅ **Audit Trail** — Comprehensive logging, processed message tracking  
✅ **Error Handling** — Graceful failures, detailed error logs  
✅ **Duplicate Prevention** — In-memory tracking of processed messages  

## Logging

Logs go to:
- **Console** — Real-time execution trace
- **File** — `ss_confirm.log` for audit

## Security Notes

- ✅ Credentials in `.env` (excluded from git)
- ✅ Webhook secret passed in request body
- ✅ No credentials logged or exposed
- ✅ MFA tokens extracted but not stored
- ✅ Downloaded files stored locally only
- ✅ OAuth tokens refresh automatically

## Troubleshooting

**"Gmail API error: 404 Not Found"**
- Check `credentials.json` exists and is valid

**"MFA code not received within timeout"**
- Verify MFA email arrives at `Hesham.ahsan@gmail.com`
- Increase `MFA_TIMEOUT` in `.env`

**"Webhook submission failed (status: 401)"**
- Verify `WEBHOOK_SECRET` is correct
- Check webhook endpoint is accessible

**"Browser automation error: Timeout waiting for selector"**
- Login form may have different field names
- Update `SINGLESOURCE_USERNAME_FIELD` and `SINGLESOURCE_PASSWORD_FIELD`

## Next Steps

- [ ] Deploy to VPS with cron job for `--continuous` mode
- [ ] Test with real closing confirmation email
- [ ] Add Slack/email notifications on success/failure
- [ ] Monitor and optimize MFA timeout based on email delivery times
- [ ] Build web dashboard for monitoring processed orders

## Mobile Signing Agency Integration

Webhook expects:
```json
{
  "webhook_secret": "cqsstSfDIYg1YiYZQAx9ag-bLpmc9ElEUYeLp9t0QT4",
  "order_number": "483704694-OCK",
  "borrower": "LUCIUS DRAWHORN JR",
  "email": "ldrawhornjr@gmail.com",
  "phone": "4055744297",
  "closing_date": "6/3/2026 5:00:00 PM UTC-5",
  "location": "Oklahoma City, OK",
  "fee": "150.00",
  "htm_content": "base64-encoded-file-contents",
  "htm_filename": "Closing_Engagement_Letter_Hesham Ahsan.htm",
  "submitted_at": "2026-05-28T19:51:34.567890"
}
```
