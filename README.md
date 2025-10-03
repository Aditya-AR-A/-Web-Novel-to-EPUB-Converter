# 📚 Web Novel to EPUB Converter

FastAPI-based web service that scrapes full novels from [FreeWebNovel](https://freewebnovel.com), converts them into polished EPUB files, and persists both metadata and files using **SQLite** (or any SQLAlchemy-compatible database) plus **Amazon S3**.

The project is designed for stateless deployments such as HuggingFace Spaces. Generated EPUBs survive restarts because they are stored in S3, while metadata is kept in a relational database for quick lookups.

---

## 🧰 Feature Highlights

- Full-novel scraping with retry-aware proxy rotation.
- EPUB generation with clean styling, TOC, intro page, metadata tiles, and embedded cover art.
- REST API (FastAPI) exposing endpoints to generate, list, download (single/many/all), and delete EPUBs.
- Persistent metadata via SQLAlchemy ORM models (default SQLite database under `data/epubs.db`).
- Durable file storage on AWS S3 with presigned download URLs and streaming download endpoints.
- Modular architecture (`app/`) grouping configuration, database, services, routers, schemas, and storage adapters.

---

## 🏗️ Updated Project Structure

```
|-Web-Novel-to-EPUB-Converter/
│
├── api.py                     # FastAPI application entry point
├── app/
│   ├── config.py              # Environment-driven settings (AWS, DB, etc.)
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
│       └── s3.py              # S3 client wrapper with fail-safes
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

## � Configuration

Environment variables (or `.env`) drive runtime configuration via `app/config.py`.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `AWS_S3_BUCKET` | ✅ | — | Target bucket that stores generated EPUBs. |
| `AWS_REGION` | ❌ | `us-east-1` | AWS region for the S3 bucket. |
| `AWS_ACCESS_KEY_ID` | ❌ | — | Access key for S3. Use IAM role/instance profile if omitted. |
| `AWS_SECRET_ACCESS_KEY` | ❌ | — | Secret key for S3. |
| `DATABASE_URL` | ❌ | `sqlite:///data/epubs.db` | SQLAlchemy database URL. |
| `S3_PRESIGN_EXPIRATION` | ❌ | `3600` | Seconds a presigned URL remains valid. |

Example `.env` for local development:

```env
AWS_S3_BUCKET=my-epub-bucket
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=xxxxxxxx
AWS_SECRET_ACCESS_KEY=yyyyyyyy
DATABASE_URL=sqlite:///data/epubs.db
S3_PRESIGN_EXPIRATION=3600
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
- Verifies S3 configuration by generating a short-lived presigned URL.

---

## 🌐 Core API Endpoints (excerpt)

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/epubs/generate` | Scrape a novel, build an EPUB, upload to S3, and return metadata. |
| `GET` | `/epubs/` | List stored EPUB metadata records. |
| `GET` | `/epubs/{ebook_id}` | Retrieve metadata for a single EPUB by ID. |
| `DELETE` | `/epubs/{ebook_id}` | Delete EPUB metadata and the S3 object. |
| `POST` | `/epubs/download` | Stream a single EPUB (via S3 object key). |
| `POST` | `/epubs/download/many` | Stream multiple EPUBs zipped together. |
| `POST` | `/epubs/download/all` | Stream every stored EPUB in one ZIP. |

Responses include the S3 key and a presigned download URL so clients can fetch files directly without proxying through the API if preferred.

---

## 🗃️ Storage Strategy

- **Database (SQLite by default):** Stores metadata such as title, author, original source URL, S3 key, presigned URL, file size, status, and error messages.
- **S3:** Stores the binary EPUB files using keys like `epubs/<slug>-<unique-id>.epub`. All download endpoints stream from S3 or return presigned URLs. The app never relies on ephemeral local filesystem beyond temporary generation directories.

To switch databases (e.g., PostgreSQL, MySQL), update `DATABASE_URL`. SQLAlchemy handles the rest.

---

## 🤖 Development Notes

- Existing scraping and conversion utilities remain under `scripts/`. The service layer orchestrates them while handling temp files, cover uploads, and error propagation.
- When adding new storage backends (e.g., Azure Blob, Google Cloud Storage), implement another adapter under `app/storage/` and swap the dependency injection accordingly.
- Run `python -m compileall app api.py` before deployment to catch syntax issues quickly.

---

## 📜 License

MIT License