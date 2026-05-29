# SS-Confirm Docker Deployment

## Quick Start

### 1. Prepare Environment

```bash
cd /opt/ss-confirm

# Copy environment template
cp .env.docker .env

# Edit with your credentials
nano .env
```

### 2. Copy Google Credentials

```bash
# Copy credentials.json to the directory
cp /path/to/credentials.json /opt/ss-confirm/
```

### 3. Build and Run

```bash
# Build image
docker build -t ss-confirm:latest .

# Run with docker-compose
docker-compose up -d

# Or run directly
docker run -d \
  --name ss-confirm-workflow \
  --restart unless-stopped \
  -e SINGLESOURCE_USERNAME=Hesham.ahsan@gmail.com \
  -e SINGLESOURCE_PASSWORD='***' \
  -e WEBHOOK_URL=https://msaok.base44.app/api/functions/webhookCreateSigning \
  -e WEBHOOK_SECRET=cqsstS...n \
  -v $(pwd)/credentials.json:/opt/ss-confirm/credentials.json:ro \
  -v $(pwd)/downloads:/opt/ss-confirm/downloads \
  -v $(pwd)/logs:/var/log/ss-confirm \
  ss-confirm:latest
```

### 4. Monitor

```bash
# View logs
docker logs -f ss-confirm-workflow

# Check status
docker ps | grep ss-confirm

# View downloaded files
ls -la /opt/ss-confirm/downloads
```

## Docker Network Integration

If running on the same Docker network as Hermes:

```bash
# Create network (if not exists)
docker network create hermes-network

# Run with network
docker-compose -f docker-compose.yml up -d
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_DIR` | `/opt/ss-confirm` | Working directory |
| `LOG_DIR` | `/var/log/ss-confirm` | Log file location |
| `DOWNLOAD_DIR` | `/opt/ss-confirm/downloads` | Downloaded HTM files |
| `SINGLESOURCE_USERNAME` | *(required)* | Login username |
| `SINGLESOURCE_PASSWORD` | *(required)* | Login password |
| `WEBHOOK_URL` | *(required)* | Mobile Signing Agency endpoint |
| `WEBHOOK_SECRET` | *(required)* | Webhook authentication |
| `MFA_TIMEOUT` | `300` | MFA code wait (seconds) |
| `CHECK_INTERVAL` | `300` | Email check interval (seconds) |
| `MONITORED_EMAIL` | `closings@singlesourceproperty.com` | Source email |

## Docker Compose Integration

To integrate with existing Hermes Docker setup:

```bash
# Add to your main docker-compose.yml:

services:
  ss-confirm:
    build: ./ss-confirm
    container_name: ss-confirm-workflow
    restart: unless-stopped
    env_file: ./ss-confirm/.env
    volumes:
      - ./ss-confirm/credentials.json:/opt/ss-confirm/credentials.json:ro
      - ./ss-confirm/downloads:/opt/ss-confirm/downloads
      - ./ss-confirm/logs:/var/log/ss-confirm
    networks:
      - hermes-network
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Then run:

```bash
docker-compose up -d ss-confirm
```

## Troubleshooting

**"Gmail API error: 401"**
```bash
# Remove token and re-auth
docker exec ss-confirm-workflow rm /opt/ss-confirm/token.pickle

# Restart (will trigger browser auth)
docker restart ss-confirm-workflow
```

**"Connection refused to webhook"**
```bash
# Test endpoint from container
docker exec ss-confirm-workflow \
  curl -v https://msaok.base44.app/api/functions/webhookCreateSigning
```

**"Playwright: Chromium not found"**
```bash
# Rebuild image (ensures Chromium installed)
docker build --no-cache -t ss-confirm:latest .
```

## Logs

Logs are written to:
- **Container stdout**: `docker logs ss-confirm-workflow`
- **File**: `/opt/ss-confirm/logs/ss_confirm.log`
- **Docker JSON logs**: `/var/lib/docker/containers/.../...json.log`

## Health Check

Container includes health check:
```bash
# Check health
docker inspect --format='{{.State.Health.Status}}' ss-confirm-workflow
```

## Production Notes

- ✅ Runs as continuous daemon
- ✅ Auto-restart on failure
- ✅ Resource limits configured
- ✅ Logs rotated automatically
- ✅ Clean shutdown support
- ⚠️ Credentials should be in secrets manager (not in .env)
- ⚠️ Use volume mounts for persistence

## Next Steps

1. Build and run container
2. Monitor logs for OAuth auth flow
3. Test with real closing email
4. Set up log aggregation/monitoring
