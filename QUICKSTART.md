# 🚀 Quick Start Guide

## Choose Your Deployment Mode

### 1️⃣ Local Development (Simplest)

Perfect for testing and development on your local machine.

```bash
# 1. Clone and setup
git clone <your-repo-url>
cd -Web-Novel-to-EPUB-Converter
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Run with local storage (no external services needed)
export STORAGE_BACKEND=local
export DATABASE_URL=sqlite:///./data/epubs.db

# 3. Start the server
uvicorn api:app --reload

# 4. Open browser
# UI: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

---

### 2️⃣ HuggingFace Spaces (Cloud - Easiest)

Deploy to HuggingFace Spaces for free cloud hosting.

**Step 1: Prepare Repository**
```bash
# Push to HuggingFace
git remote add hf https://huggingface.co/spaces/<username>/<space-name>
git push hf main
```

**Step 2: Configure Space**
- Go to your Space settings on HuggingFace
- Set to "Docker" SDK
- Add secrets (if using external storage):
  - `GOOGLE_SERVICE_ACCOUNT_JSON` (for Google Drive)
  - `DATABASE_URL` (for external PostgreSQL)

**Step 3: Deploy**
- HuggingFace will auto-build and deploy
- Access at: `https://huggingface.co/spaces/<username>/<space-name>`

**Default .env for HF:**
```env
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=books
DATABASE_URL=sqlite:///./data/epubs.db
```

---

### 3️⃣ Production with Google Drive + Neon PostgreSQL

Enterprise-grade setup with cloud storage and database.

**Step 1: Setup Google Drive**
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a service account
3. Download JSON key file
4. Share Drive folder with service account email

**Step 2: Setup Neon PostgreSQL**
1. Sign up at [Neon](https://neon.tech)
2. Create a new database
3. Copy connection string

**Step 3: Configure**
```bash
# Create .env file
cat > .env << EOF
STORAGE_BACKEND=google_drive
GOOGLE_SERVICE_ACCOUNT_FILE=./service-account.json
GOOGLE_DRIVE_FOLDER_ID=your-folder-id-here
DATABASE_URL=postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
EOF

# Place service account JSON
cp /path/to/downloaded-key.json ./service-account.json
```

**Step 4: Run**
```bash
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 8000
```

---

### 4️⃣ Docker Deployment

Containerized deployment for any platform.

**Step 1: Build Image**
```bash
docker build -t webnovel-epub .
```

**Step 2: Run with Local Storage**
```bash
docker run -d \
  -p 7860:7860 \
  -e STORAGE_BACKEND=local \
  -e DATABASE_URL=sqlite:///./data/epubs.db \
  -v $(pwd)/books:/home/appuser/app/books \
  -v $(pwd)/data:/home/appuser/app/data \
  --name webnovel \
  webnovel-epub
```

**Step 3: Run with Google Drive**
```bash
docker run -d \
  -p 7860:7860 \
  -e STORAGE_BACKEND=google_drive \
  -e GOOGLE_SERVICE_ACCOUNT_JSON='<paste-json-here>' \
  -e GOOGLE_DRIVE_FOLDER_ID=your-folder-id \
  -e DATABASE_URL=postgresql://user:pass@host/db \
  --name webnovel \
  webnovel-epub
```

**Step 4: Check Logs**
```bash
docker logs -f webnovel
```

---

### 5️⃣ AWS S3 Deployment

Using S3 for storage (original configuration).

**Step 1: Setup AWS**
1. Create S3 bucket
2. Create IAM user with S3 permissions
3. Get access keys

**Step 2: Configure**
```bash
cat > .env << EOF
STORAGE_BACKEND=s3
AWS_S3_BUCKET=my-epub-bucket
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIAXXXXXXXX
AWS_SECRET_ACCESS_KEY=xxxxxxxxxx
DATABASE_URL=postgresql://...
EOF
```

**Step 3: Run**
```bash
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 8000
```

---

## 🎯 Feature Testing Checklist

After deployment, test these features:

### Basic EPUB Generation
1. Open Web UI
2. Enter novel URL: `https://freewebnovel.com/novel/...`
3. Configure options (chapters, workers)
4. Click "Generate EPUB"
5. Monitor real-time logs
6. Download generated file

### Job Control
1. Start EPUB generation
2. Click "Cancel" to stop immediately
3. Or click "Stop" for graceful shutdown
4. Verify job stops and cleans up

### File Management
1. List generated EPUBs
2. Download individual files
3. Download multiple as ZIP
4. Download all as ZIP
5. Delete unwanted files

### WebSocket Logging
1. Open browser console (F12)
2. Watch WebSocket connection
3. See real-time log updates
4. Test connection resilience

### Storage Backend
1. Verify files in configured storage:
   - Local: Check `books/` directory
   - S3: Check AWS console
   - Google Drive: Check Drive folder
2. Test download URLs
3. Verify database records

---

## 🔧 Troubleshooting

### Issue: Cannot connect to database
**Solution:**
```bash
# For Neon PostgreSQL, add SSL:
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require

# For local SQLite, ensure directory exists:
mkdir -p data
```

### Issue: Google Drive upload fails
**Solution:**
```bash
# Verify service account permissions
# Share folder with: service-account@project.iam.gserviceaccount.com
# Check JSON is valid:
cat service-account.json | jq .
```

### Issue: Static files not loading
**Solution:**
```bash
# Ensure static directory exists
ls -la static/

# Check mount in api.py
# Verify path: http://localhost:8000/static/index.html
```

### Issue: Docker container exits
**Solution:**
```bash
# Check logs
docker logs webnovel

# Verify environment variables
docker inspect webnovel | jq '.[0].Config.Env'

# Test locally first
uvicorn api:app --host 0.0.0.0 --port 8000
```

---

## 📊 Performance Tips

1. **Concurrent Scraping**: Use `chapter_workers: 5-10` for faster downloads
2. **Proxy Rotation**: Configure `proxies.yaml` to avoid rate limits
3. **Database**: Use PostgreSQL for production (faster than SQLite)
4. **Storage**: Use S3/Drive for durability, local for speed
5. **Caching**: Browser caches static files automatically

---

## 🔒 Security Best Practices

1. **Secrets Management**
   - Use environment variables, not hardcoded values
   - For HF Spaces: Use repository secrets
   - For Docker: Use Docker secrets or external secret managers

2. **Database Security**
   - Always use SSL for remote PostgreSQL
   - Restrict database access by IP
   - Use strong passwords

3. **Storage Security**
   - S3: Enable bucket encryption
   - Google Drive: Use service accounts, not user accounts
   - Local: Ensure proper file permissions

---

## 📈 Scaling Considerations

### Small Scale (< 100 EPUBs/day)
- Local storage
- SQLite database
- Single server
- Default configuration

### Medium Scale (100-1000 EPUBs/day)
- Google Drive or S3 storage
- PostgreSQL database
- Multiple workers
- Load balancer

### Large Scale (> 1000 EPUBs/day)
- S3 with CloudFront CDN
- Managed PostgreSQL (RDS/Neon)
- Kubernetes deployment
- Redis caching
- Queue system (Celery/RabbitMQ)

---

## 🎓 Next Steps

1. **Customize**: Modify `static/index.html` for branding
2. **Extend**: Add new novel sources in `scripts/scraper.py`
3. **Monitor**: Set up logging/metrics (Datadog, Sentry)
4. **Automate**: Create CI/CD pipeline (GitHub Actions)
5. **Scale**: Add caching layer and queue system

---

## 📞 Support & Resources

- **Documentation**: See `README_NEW.md`
- **Configuration**: See `.env.example`
- **Migration Guide**: See `MIGRATION_SUMMARY.md`
- **API Reference**: http://localhost:8000/docs
- **Source Code**: Check inline comments

---

**Happy EPUB Converting! 📚✨**
