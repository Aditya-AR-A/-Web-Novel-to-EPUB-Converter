---
title: Web Novel to EPUB Converter
emoji: 📚
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Scrape FreeWebNovel titles and build EPUB volumes via FastAPI.
---

# 📚 Web Novel to EPUB Converter

FastAPI-based web service that scrapes full novels from [FreeWebNovel](https://freewebnovel.com), converts them into polished EPUB files, and persists both metadata and files using **SQLite / PostgreSQL** and pluggable storage adapters (local disk, Amazon S3, or Google Drive).

The project is designed for stateless deployments such as HuggingFace Spaces. Generated EPUBs survive restarts because they are uploaded to durable storage, while metadata is kept in a relational database for quick lookups.

---

## 🧰 Feature Highlights

- Full-novel scraping with retry-aware proxy rotation.
- EPUB generation with clean styling, TOC, intro page, metadata tiles, and embedded cover art.
- REST API (FastAPI) exposing endpoints to generate, list, download (single/many/all), and delete EPUBs.
- Persistent metadata via SQLAlchemy ORM models (default SQLite database under `data/epubs.db`).
- Durable file storage using pluggable adapters (AWS S3, Google Drive Shared Drive, or local filesystem for development demos).
- Modular architecture (`app/`) grouping configuration, database, services, routers, schemas, and storage adapters.

---

## 🏗️ Updated Project Structure

```
|-Web-Novel-to-EPUB-Converter/
│
├── api.py                     # FastAPI application entry point
├── app/
│   ├── config.py              # Environment-driven settings (storage, DB, etc.)
│   ├── db/
│   │   ├── session.py         # SQLAlchemy engine + session helpers
│   │   └── models.py          # ORM models (EpubMetadata)
│   ├── routers/
│   │   └── epubs.py           # FastAPI routes for EPUB actions
│   ├── schemas/
│   │   └── epub.py            # Pydantic response/request models
│   ├── services/
│   │   └── epub_service.py    # High-level orchestration logic
│   └── storage/
│       ├── google_drive.py    # Google Drive (Shared Drive / delegated user) adapter
│       ├── s3.py              # S3 client wrapper with fail-safes
│       └── local.py           # Local filesystem adapter (HuggingFace demo)
├── scripts/                   # Scraping + EPUB conversion helpers (existing logic)
├── media/                     # Sample cover assets
├── books/                     # Legacy local output (optional)
├── requirements.txt
└── README.md
```

---

## ⚙️ Requirements & Installation

- Python 3.10+
- Dependencies (see `requirements.txt`): `fastapi`, `uvicorn`, `sqlalchemy`, `boto3`, `python-multipart`, plus scraping libraries (`requests`, `beautifulsoup4`, `ebooklib`, `PySocks`, `PyYAML`).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## ⚙️ Configuration

Environment variables (or `.env`) drive runtime configuration via `app/config.py`.

### Core settings

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `STORAGE_BACKEND` | ❌ | `local` | One of `local`, `s3`, or `google_drive`. |
| `DATABASE_URL` | ❌ | `sqlite:///data/epubs.db` | SQLAlchemy database URL (Neon/PostgreSQL works great). |
| `LOCAL_STORAGE_PATH` | ❌ | `books` | Target directory for local storage backend. |

### Amazon S3 backend

| Variable | Required when `STORAGE_BACKEND=s3` | Default | Description |
| --- | --- | --- | --- |
| `AWS_S3_BUCKET` | ✅ | — | Bucket that stores generated EPUBs. |
| `AWS_REGION` | ❌ | `us-east-1` | Region for the bucket. |
| `AWS_ACCESS_KEY_ID` | ❌ | — | Access key (omit when using IAM role). |
| `AWS_SECRET_ACCESS_KEY` | ❌ | — | Secret key. |
| `S3_PRESIGN_EXPIRATION` | ❌ | `3600` | Seconds a presigned URL remains valid. |

### Google Drive backend

| Variable | Required when `STORAGE_BACKEND=google_drive` | Default | Description |
| --- | --- | --- | --- |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | ✅* | — | Raw JSON for the service account (mutually exclusive with `_FILE`). |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | ✅* | — | Path to the service account JSON on disk. |
| `GOOGLE_DRIVE_FOLDER_ID` | ✅† | — | Shared Drive folder ID where EPUBs are uploaded. |
| `GOOGLE_IMPERSONATED_USER` | ✅† | — | Email to impersonate when using domain-wide delegation. |

`*` Provide either the inline JSON or a file path. `†` You must supply at least one of `GOOGLE_DRIVE_FOLDER_ID` (recommended) or `GOOGLE_IMPERSONATED_USER`. Service accounts have **no personal storage quota**, so the account must either be a member of a Shared Drive (set the folder ID) or delegate to a Workspace user who has storage.

Example `.env` for Google Drive + Neon PostgreSQL:

```env
STORAGE_BACKEND=google_drive
GOOGLE_SERVICE_ACCOUNT_FILE=/app/credentials/service-account.json
GOOGLE_DRIVE_FOLDER_ID=1AbCdEfGhIjKlMnOpQr
DATABASE_URL=postgresql+psycopg://user:pass@db.neon.tech/dbname
```

For HuggingFace Spaces, store secrets using the built-in **Repository Secrets** UI so they remain encrypted.

---

## 🚀 Running the API

1. Ensure the database path exists (created automatically for SQLite).
2. Run the FastAPI app with Uvicorn:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

3. Visit the interactive docs at `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc`.

On startup the app:

- Creates database tables (`EpubMetadata`).
- Validates the configured storage backend (S3 presign, Google Drive health check, etc.).

---

## 🌐 Core API Endpoints (excerpt)

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/epubs/generate` | Scrape a novel, build an EPUB, upload to the configured storage backend, and return metadata. |
| `GET` | `/epubs/` | List stored EPUB metadata records. |
| `GET` | `/epubs/{ebook_id}` | Retrieve metadata for a single EPUB by ID. |
| `DELETE` | `/epubs/{ebook_id}` | Delete EPUB metadata and the S3 object. |
| `POST` | `/epubs/download` | Stream a single EPUB (via S3 object key). |
| `POST` | `/epubs/download/many` | Stream multiple EPUBs zipped together. |
| `POST` | `/epubs/download/all` | Stream every stored EPUB in one ZIP. |

Responses include the storage key and (when supported) a presigned download URL so clients can fetch files directly without proxying through the API if preferred.

---

## 🗃️ Storage Strategy

- **Database (SQLite by default):** Stores metadata such as title, author, original source URL, storage key/URL, file size, status, and error messages.
- **Storage backend:**
	- _Local_ — drops EPUBs into `LOCAL_STORAGE_PATH` (great for quick tests / Spaces demos).
	- _S3_ — stores EPUBs under keys like `epubs/<slug>-<unique-id>.epub`; download endpoints stream from S3 or return presigned URLs.
	- _Google Drive_ — uploads EPUBs into a Shared Drive folder (or via delegated user) and exposes a shareable download link.

To switch databases (e.g., PostgreSQL, MySQL), update `DATABASE_URL`. SQLAlchemy handles the rest.

---

## 🤖 Development Notes

- Existing scraping and conversion utilities remain under `scripts/`. The service layer orchestrates them while handling temp files, cover uploads, and error propagation.
- When adding new storage backends (e.g., Azure Blob, Google Cloud Storage), implement another adapter under `app/storage/` and swap the dependency injection accordingly.
- Run `python -m compileall app api.py` before deployment to catch syntax issues quickly.

---

## 📜 License

MIT License

---

## 🐳 Docker Usage

### Build Locally

```bash
docker build -t web2epub .
```

### Run

```bash
docker run -p 7860:7860 \
   -e PORT=7860 \
   -e UVICORN_WORKERS=1 \
   -v ${PWD}/books:/app/books \
   -v ${PWD}/media:/app/media \
   web2epub
```

Then open: http://localhost:7860/docs

### Environment Variables (Scraping Tuning)

| Variable | Purpose | Example |
|----------|---------|---------|
| PRIMARY_PROXY | Force a single proxy for all requests | http://user:pass@host:port |
| DISABLE_PUBLIC_PROXIES | Ignore loaded proxy lists | 1 |
| SCRAPER_UA | Override rotating User-Agent | Mozilla/5.0 ... |
| MIN_PROXY_HEALTH | Quarantine threshold (<= value) | -3 |
| RETRY_BACKOFF_BASE | Initial backoff seconds | 0.6 |
| MAX_BACKOFF | Max backoff cap | 4.0 |
| ENABLE_BLOCK_DETECT | Enable block page detection | 1 |
| SHORT_CIRCUIT_ON_FIRST_403 | Stop retry sequence early | 1 |

### Hugging Face Space (Docker)

1. Create a Docker Space.
2. Add the repository contents (or point to your GitHub fork).
3. Ensure `Dockerfile` exists at root (provided).
4. Add environment variables in the Space settings (especially `PRIMARY_PROXY` if needed).
5. Space automatically builds and exposes at port 7860.

### Health Check

```bash
curl -s http://localhost:7860/health
```

### Generate EPUB via API

```bash
curl -X POST http://localhost:7860/epub/generate \
   -H "Content-Type: application/json" \
   -d '{"url":"https://freewebnovel.com/novel/...","chapters_per_book":400,"chapter_workers":0}'
```

---

## 🛠 Future Enhancements

- Add Gradio UI frontend
- Persist proxy health across restarts
- WebSocket progress streaming
- Chapter fetch caching layer
