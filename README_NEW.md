# 📚 Web Novel to EPUB Converter

FastAPI-based web service that scrapes full novels from [FreeWebNovel](https://freewebnovel.com), converts them into polished EPUB files, and provides multiple storage backends with real-time logging.

The project supports both **stateless cloud deployments** (HuggingFace Spaces, Docker) and **database-backed** persistent storage with AWS S3, Google Drive, or local file storage.

---

## 🧰 Feature Highlights

- **Full-novel scraping** with retry-aware proxy rotation and cancellation support
- **EPUB generation** with clean styling, TOC, intro page, metadata tiles, and embedded cover art
- **Multiple storage backends**: Local files, AWS S3, or Google Drive
- **Database persistence** with SQLAlchemy ORM (PostgreSQL/Neon, SQLite)
- **Real-time WebSocket logging** for live progress updates
- **Job cancellation** - stop long-running scraping operations
- **Modern Web UI** with dark/light theme and responsive design
- **REST API** (FastAPI) for generating, listing, downloading, and managing EPUBs
- **Docker support** with HuggingFace Spaces compatibility

---

## 🏗️ Project Structure

```
|-Web-Novel-to-EPUB-Converter/
│
├── api.py                     # FastAPI application entry point
├── main_api.py                # Uvicorn server launcher
├── Dockerfile                 # Production container image
├── entrypoint.sh              # Container startup script
├── static/                    # Web UI assets
│   ├── index.html            # Main application UI
│   └── logo.png              # Application logo
├── app/
│   ├── config.py              # Environment-driven settings
│   ├── db/
│   │   ├── session.py         # SQLAlchemy engine + session
│   │   └── models.py          # ORM models (EpubMetadata)
│   ├── routers/
│   │   ├── epubs_enhanced.py  # EPUB API routes (dual mode)
│   │   └── logs.py            # WebSocket logging
│   ├── schemas/
│   │   └── epub.py            # Pydantic models
│   ├── services/
│   │   └── epub_service.py    # Business logic
│   └── storage/
│       ├── s3.py              # AWS S3 adapter
│       ├── google_drive.py    # Google Drive adapter
│       └── local.py           # Local file storage
├── scripts/                   # Scraping & EPUB conversion
│   ├── scraper.py            # Novel scraping with cancellation
│   ├── convert_to_epub.py    # EPUB generation
│   ├── cancellation.py       # Job cancellation system
│   └── ...
├── books/                     # Local EPUB storage (default)
├── media/                     # Cover images cache
└── requirements.txt
```

---

## ⚙️ Requirements & Installation

- Python 3.10+
- Dependencies: See `requirements.txt`

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 🔧 Configuration

Environment variables (or `.env`) drive runtime configuration. See `.env.example` for all options.

### Storage Backend

| Variable | Options | Default | Description |
| --- | --- | --- | --- |
| `STORAGE_BACKEND` | `local`, `s3`, `google_drive` | `local` | Storage system to use |

### AWS S3 Configuration (when `STORAGE_BACKEND=s3`)

| Variable | Required | Description |
| --- | --- | --- |
| `AWS_S3_BUCKET` | ✅ | Target S3 bucket name |
| `AWS_REGION` | ❌ | AWS region (default: us-east-1) |
| `AWS_ACCESS_KEY_ID` | ❌ | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | ❌ | AWS secret key |

### Google Drive Configuration (when `STORAGE_BACKEND=google_drive`)

| Variable | Required | Description |
| --- | --- | --- |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | One of these | Service account JSON as string |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | One of these | Path to service account JSON file |
| `GOOGLE_DRIVE_FOLDER_ID` | ❌ | Specific folder ID to store files |
| `GOOGLE_IMPERSONATED_USER` | ❌ | User email for domain-wide delegation |

### Database Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/epubs.db` | SQLAlchemy database URL |

Example for **Neon PostgreSQL**:
```env
DATABASE_URL=postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/neondb
```

### Local Storage Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `LOCAL_STORAGE_PATH` | `books` | Directory for local EPUB storage |

---

## 🚀 Running the API

### Local Development

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Or using the launcher:

```bash
python main_api.py
```

Visit:
- Web UI: `http://localhost:8000/`
- API Docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Docker Deployment

```bash
docker build -t webnovel-epub .
docker run -p 7860:7860 \
  -e STORAGE_BACKEND=local \
  -e DATABASE_URL=sqlite:///./data/epubs.db \
  webnovel-epub
```

### HuggingFace Spaces

The included `Dockerfile` and `entrypoint.sh` are configured for HuggingFace Spaces deployment. The app auto-detects the `PORT` environment variable.

---

## 📡 API Endpoints

### EPUB Generation

**Local Mode (File-based)**
```bash
POST /epubs/epub/generate
{
  "url": "https://freewebnovel.com/novel/...",
  "chapters_per_book": 500,
  "chapter_workers": 5,
  "chapter_limit": 0,
  "start_chapter": 1
}
```

**Database Mode (with Storage)**
```bash
POST /epubs/generate
FormData:
  - url: string
  - title: string
  - author: string (optional)
  - genres: string (comma-separated, optional)
  - tags: string (comma-separated, optional)
  - cover: file (optional)
```

### Job Control

```bash
POST /epubs/epub/cancel    # Cancel ongoing generation
POST /epubs/epub/stop      # Gracefully stop generation
```

### Listing EPUBs

```bash
GET /epubs/epubs?offset=0&limit=100    # Local mode
GET /epubs/                             # Database mode
```

### Downloading

```bash
GET /epubs/epub/download?name=file.epub           # Local mode - single
POST /epubs/epubs/download {"names": [...]}       # Local mode - multiple
POST /epubs/epubs/download/all                    # Local mode - all

POST /epubs/download {"key": "..."}                # Database mode - single
POST /epubs/download/many {"keys": [...]}         # Database mode - multiple
POST /epubs/download/all                           # Database mode - all
```

### Deletion

```bash
DELETE /epubs/{ebook_id}                  # Database mode
DELETE /epubs/epubs?names=[...]           # Local mode - multiple
DELETE /epubs/epubs/all                   # Local mode - all
```

### Real-time Logging

```bash
GET /logs?since=0&limit=400              # Poll logs
WS /ws/logs                               # WebSocket stream
```

---

## 🎨 Web Interface

The modern web UI (`static/index.html`) provides:

- **EPUB Generation Form**: URL input with advanced options (chapter limits, workers, etc.)
- **File Management**: List, download, and delete generated EPUBs
- **Real-time Logs**: WebSocket-powered live console with scrollable output
- **Job Control**: Cancel/stop buttons for long-running operations
- **Theme Toggle**: Dark/light mode support
- **Responsive Design**: Works on desktop and mobile devices

---

## 🐳 Docker & Deployment

### Building the Image

```bash
docker build -t webnovel-epub-converter .
```

### Running with Environment Variables

```bash
docker run -p 7860:7860 \
  -e STORAGE_BACKEND=google_drive \
  -e GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}' \
  -e GOOGLE_DRIVE_FOLDER_ID=your-folder-id \
  -e DATABASE_URL=postgresql://user:pass@host/db \
  webnovel-epub-converter
```

### HuggingFace Spaces Configuration

1. Push code to your HF repository
2. Set repository secrets in Settings:
   - `GOOGLE_SERVICE_ACCOUNT_JSON`
   - `DATABASE_URL` (if using external PostgreSQL)
   - Other storage credentials as needed
3. The app will automatically start on port 7860

---

## 🔄 Migration from HF Version

The main repository now includes all features from the HuggingFace live version:

✅ **Copied from HF repo:**
- Static web UI (`static/index.html`, `static/logo.png`)
- Dockerfile and entrypoint.sh
- Cancellation system (`scripts/cancellation.py`)
- WebSocket logging (`app/routers/logs.py`)
- Enhanced API routes supporting both modes

✅ **Added from main repo:**
- Google Drive storage integration
- Neon PostgreSQL support
- S3 storage (existing)
- Database models and migrations

✅ **Merged features:**
- Unified EPUB router supporting both local and database modes
- Scraper with cancellation hooks
- Configurable storage backends
- Environment-based configuration

---

## 📝 License

See LICENSE file for details.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 🐛 Troubleshooting

### Database Issues
- For Neon PostgreSQL, ensure your connection string includes SSL: `?sslmode=require`
- SQLite databases are created automatically in the `data/` directory

### Storage Issues
- **S3**: Verify bucket permissions and AWS credentials
- **Google Drive**: Ensure service account has proper permissions
- **Local**: Check `LOCAL_STORAGE_PATH` directory is writable

### Scraping Issues
- Proxy rotation may be needed for rate-limited sites
- Configure proxies in `proxies.yaml`
- Use cancellation endpoints if jobs hang

---

## 📚 Future Enhancements

- [ ] Support for additional novel sources
- [ ] Batch processing queue
- [ ] User authentication and multi-tenancy
- [ ] Advanced EPUB customization options
- [ ] CDN integration for faster downloads
- [ ] Scheduled scraping jobs
