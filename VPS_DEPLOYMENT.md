# SS-Confirm VPS Deployment Guide

## Quick Deploy to Production (VPS)

### On Your VPS:

```bash
# 1. Clone the repo
cd /opt
git clone https://github.com/Truenorth-ADI/mobile-signing-agency.git ss-confirm
cd ss-confirm

# 2. Set up Python venv
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright chromium
python -m playwright install chromium

# 5. Copy credentials
cp credentials.json .  # (you'll need to transfer this file)

# 6. Create .env with your config
cat > .env << 'EOF'
GMAIL_OAUTH_CREDENTIALS_FILE=credentials.json
SINGLESOURCE_USERNAME=Hesham.ahsan@gmail.com
SINGLESOURCE_PASSWORD=Livelife482!
WEBHOOK_URL=https://msaok.base44.app/api/functions/webhookCreateSigning
WEBHOOK_SECRET=cqsstSfDIYg1YiYZQAx9ag-bLpmc9ElEUYeLp9t0QT4
DOWNLOAD_DIR=/opt/ss-confirm/downloads
MFA_TIMEOUT=300
CHECK_INTERVAL=300
MONITORED_EMAIL=closings@singlesourceproperty.com
EOF

# 7. First run (interactive OAuth)
python ss_confirm.py

# This will open a browser for you to authorize Gmail access
# Approve and it will save token.pickle for future runs

# 8. Test with --continuous mode
python ss_confirm.py --continuous &

# 9. Set up cron for continuous monitoring
crontab -e
# Add this line:
# */5 * * * * cd /opt/ss-confirm && source .venv/bin/activate && python ss_confirm.py >> /opt/ss-confirm/ss_confirm_cron.log 2>&1
```

## What Happens Next

Once deployed:
1. **Email arrives** from closings@singlesourceproperty.com
2. **SS-Confirm detects it** (checks every 5 minutes via cron)
3. **Extracts order details** (order #, borrower, closing date, fee)
4. **Opens browser** → logs in with credentials
5. **Handles MFA** → watches for verification email
6. **Downloads HTM file** from SingleSource
7. **POSTs to webhook** → Mobile Signing Agency receives file
8. **Logs result** → marked as processed

## Files Needed

- ✅ `ss_confirm.py` — Main automation script (in repo)
- ✅ `requirements.txt` — Dependencies (in repo)
- ✅ `README.md` — Full documentation (in repo)
- 📝 `credentials.json` — Google OAuth (you just downloaded)
- 📝 `.env` — Configuration (create on VPS)

## Testing

**One-time test:**
```bash
python ss_confirm.py
```

**Continuous monitoring:**
```bash
python ss_confirm.py --continuous
```

**Check logs:**
```bash
tail -f ss_confirm.log
tail -f ss_confirm_cron.log
```

## Troubleshooting

**"Gmail API error: 401 Unauthorized"**
- Delete `token.pickle` and run `python ss_confirm.py` again to re-authorize

**"MFA code not received"**
- Check spam folder for verification email
- Increase `MFA_TIMEOUT=600` in .env

**"Webhook submission failed"**
- Verify webhook secret is correct
- Check webhook endpoint is accessible from VPS

## Next Steps

1. Deploy code to VPS
2. First run with `python ss_confirm.py` (one-time OAuth auth)
3. Enable cron job for continuous monitoring
4. Test with real closing confirmation email
5. Monitor logs for any issues
