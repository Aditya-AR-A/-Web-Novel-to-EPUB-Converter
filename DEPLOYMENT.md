# 🚀 Deployment Guide - Web Novel to EPUB Converter

This guide covers deploying the application in various environments after the HuggingFace integration.

## 📋 Table of Contents

- [Prerequisites](#prerequisites)
- [Database Migration](#database-migration)
- [Local Development](#local-development)
- [Storage Backend Configuration](#storage-backend-configuration)
- [Production Deployment](#production-deployment)
- [HuggingFace Spaces](#huggingface-spaces)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements
- Python 3.11+
- PostgreSQL (optional, for production)
- AWS S3 or Google Drive (optional, for cloud storage)

### Install Dependencies

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Database Migration

**⚠️ Important:** If upgrading from an older version, run the migration script first:

```bash
python migrate_database.py
```

This will:
- Update column names from `s3_key/s3_url` to `storage_key/storage_url`
- Preserve existing data
- Support both SQLite and PostgreSQL

---

## Local Development

### Quick Start (Local Storage)

The easiest way to get started:

```bash
# Use the startup script
./start.sh

# Or manually:
export STORAGE_BACKEND=local
uvicorn api:app --reload
```

Visit: **http://localhost:8000**

### Configuration Options

Create a `.env` file (or use environment variables):

```bash
# Storage Backend (local/s3/google_drive)
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=books

# Database (optional - defaults to SQLite)
DATABASE_URL=sqlite:///./data/epubs.db
```

---

## Storage Backend Configuration

### 1. Local Storage (Default)

**Pros:** No external dependencies, perfect for development  
**Cons:** Not suitable for distributed deployments

```bash
export STORAGE_BACKEND=local
export LOCAL_STORAGE_PATH=books  # Optional, defaults to "books"
```

Files stored in: `./books/`

### 2. AWS S3

**Pros:** Scalable, reliable, industry standard  
**Cons:** Requires AWS account and credentials

```bash
export STORAGE_BACKEND=s3
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_REGION=us-east-1
export AWS_S3_BUCKET=your-bucket-name
```

**Setup Steps:**
1. Create S3 bucket in AWS Console
2. Create IAM user with S3 permissions
3. Generate access keys
4. Configure environment variables

### 3. Google Drive

**Pros:** Free storage (15GB), familiar interface  
**Cons:** Requires service account setup

```bash
export STORAGE_BACKEND=google_drive
export GOOGLE_SERVICE_ACCOUNT_FILE=./service-account.json
export GOOGLE_DRIVE_FOLDER_ID=your_folder_id  # Optional
```

**Setup Steps:**
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Enable Google Drive API
4. Create Service Account
5. Download JSON credentials
6. Share Drive folder with service account email

Alternative (JSON string):
```bash
export GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
```

---

## Production Deployment

### Option 1: Traditional Server (systemd)

**1. Create systemd service:**

```bash
sudo nano /etc/systemd/system/epub-converter.service
```

```ini
[Unit]
Description=Web Novel to EPUB Converter
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/epub-converter
Environment="PATH=/var/www/epub-converter/.venv/bin"
Environment="STORAGE_BACKEND=s3"
Environment="DATABASE_URL=postgresql://user:pass@localhost/epubs"
ExecStart=/var/www/epub-converter/.venv/bin/uvicorn api:app --host 0.0.0.0 --port 8000

[Install]
WantedBy=multi-user.target
```

**2. Start service:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable epub-converter
sudo systemctl start epub-converter
```

### Option 2: Docker

**Build and run:**

```bash
# Build image
docker build -t epub-converter .

# Run with local storage
docker run -p 8000:8000 \
  -e STORAGE_BACKEND=local \
  -v $(pwd)/books:/app/books \
  epub-converter

# Run with cloud storage
docker run -p 8000:8000 \
  -e STORAGE_BACKEND=s3 \
  -e AWS_ACCESS_KEY_ID=xxx \
  -e AWS_SECRET_ACCESS_KEY=xxx \
  -e AWS_S3_BUCKET=xxx \
  epub-converter
```

### Option 3: Cloud Platforms

#### Railway
1. Connect GitHub repository
2. Set environment variables in dashboard
3. Deploy automatically

#### Render
1. Create new Web Service
2. Connect repository
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn api:app --host 0.0.0.0 --port $PORT`

#### Fly.io
```bash
fly launch
fly secrets set STORAGE_BACKEND=s3 AWS_ACCESS_KEY_ID=xxx ...
fly deploy
```

---

## HuggingFace Spaces

The application includes full HuggingFace Spaces support with Docker.

### Deployment Steps

**1. Create Space on HuggingFace:**
- Go to https://huggingface.co/spaces
- Click "Create new Space"
- Choose "Docker" as SDK
- Clone the repo

**2. Copy deployment files:**

```bash
# Files are already in place:
# - Dockerfile
# - entrypoint.sh
# - static/index.html
```

**3. Configure Secrets (HF Dashboard):**

```
STORAGE_BACKEND=local
DATABASE_URL=sqlite:///./data/epubs.db
```

For cloud storage, add:
```
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_S3_BUCKET=xxx
```

**4. Push to HuggingFace:**

```bash
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE
git push hf main
```

**5. Access your Space:**
- Space URL: `https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE`
- Direct app: `https://YOUR_USERNAME-YOUR_SPACE.hf.space`

### HuggingFace-Specific Features

The deployment includes:
- ✅ WebSocket logging for real-time feedback
- ✅ Job cancellation controls
- ✅ Dark/light theme UI
- ✅ Responsive design
- ✅ Direct EPUB downloads
- ✅ Port 7860 (HF standard)

---

## Database Configuration

### SQLite (Default - Development)

```bash
export DATABASE_URL=sqlite:///./data/epubs.db
```

**Pros:** No setup required  
**Cons:** Single file, not for production

### PostgreSQL (Recommended - Production)

```bash
export DATABASE_URL=postgresql://user:password@host:5432/dbname
```

#### Neon (Serverless PostgreSQL)

1. Create account at [neon.tech](https://neon.tech)
2. Create new project
3. Copy connection string
4. Set `DATABASE_URL`

```bash
export DATABASE_URL=postgresql://user:pass@ep-xxxx.neon.tech/neondb?sslmode=require
```

#### Supabase (Alternative)

1. Create project at [supabase.com](https://supabase.com)
2. Go to Settings → Database
3. Copy connection string (Session mode)
4. Set `DATABASE_URL`

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STORAGE_BACKEND` | No | `local` | Storage type: `local`, `s3`, or `google_drive` |
| `DATABASE_URL` | No | SQLite | Database connection string |
| `LOCAL_STORAGE_PATH` | No | `books` | Path for local file storage |
| `AWS_ACCESS_KEY_ID` | S3 only | - | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | S3 only | - | AWS secret key |
| `AWS_REGION` | No | `us-east-1` | AWS region |
| `AWS_S3_BUCKET` | S3 only | - | S3 bucket name |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | GDrive | - | Path to service account JSON |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | GDrive | - | Service account JSON string |
| `GOOGLE_DRIVE_FOLDER_ID` | No | - | Specific Drive folder ID |

---

## Troubleshooting

### WebSocket Connection Failed

**Error:** `No supported WebSocket library detected`

**Solution:**
```bash
pip install 'uvicorn[standard]' websockets
```

### Database Column Error

**Error:** `column epubs.s3_key does not exist`

**Solution:** Run migration script:
```bash
python migrate_database.py
```

### Google Drive 403 Error

**Error:** `RuntimeError: Google service account credentials not provided`

**Solution:** Check credentials:
```bash
# Verify file exists
ls -la service-account.json

# Or check env variable
echo $GOOGLE_SERVICE_ACCOUNT_FILE

# Test credentials
python -c "from app.storage.google_drive import GoogleDriveStorage; GoogleDriveStorage()"
```

### S3 Upload Fails

**Error:** `NoCredentialsError`

**Solution:**
```bash
# Verify credentials
aws configure list

# Or export directly
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
```

### Port Already in Use

**Error:** `Address already in use`

**Solution:**
```bash
# Find process using port 8000
lsof -i :8000

# Kill it
kill -9 <PID>

# Or use different port
uvicorn api:app --port 8001
```

---

## Testing Checklist

After deployment, verify:

- [ ] Homepage loads at root URL
- [ ] `/health` endpoint returns `{"status": "ok"}`
- [ ] `/docs` shows Swagger UI
- [ ] WebSocket connects (check browser console)
- [ ] File upload works (if applicable)
- [ ] EPUB generation completes
- [ ] Download link works
- [ ] Storage backend saves files correctly

---

## Performance Tuning

### Production Settings

```bash
# Use multiple workers
uvicorn api:app --workers 4 --host 0.0.0.0 --port 8000

# With Gunicorn (better for production)
pip install gunicorn
gunicorn api:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Security Considerations

### Production Checklist

- [ ] Use HTTPS (Let's Encrypt)
- [ ] Set secure environment variables (not in code)
- [ ] Use secrets management (AWS Secrets Manager, etc.)
- [ ] Enable CORS properly
- [ ] Rate limit API endpoints
- [ ] Validate file uploads
- [ ] Sanitize user inputs
- [ ] Keep dependencies updated
- [ ] Monitor logs for errors

### CORS Configuration

If needed for web clients:

```python
# In api.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Support & Resources

- **Documentation:** See README.md
- **API Docs:** Visit `/docs` on your deployment
- **Issues:** Check GitHub Issues
- **Examples:** See `QUICKSTART.md`

---

## Quick Commands Reference

```bash
# Start development server
./start.sh

# Run tests
python test_integration.py

# Migrate database
python migrate_database.py

# Build Docker image
docker build -t epub-converter .

# Check logs
tail -f logs/app.log  # If logging configured

# Restart service
sudo systemctl restart epub-converter
```

---

**Last Updated:** October 2025  
**Version:** 2.0.0 (Post-HF Integration)
