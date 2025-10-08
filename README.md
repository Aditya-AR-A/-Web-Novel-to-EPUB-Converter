---
title: Web Novel to EPUB Converter
emoji: 📚
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Scrape FreeWebNovel novels to EPUB via FastAPI
---

# 📚 Web Novel to EPUB Converter

Scrape and convert full (or partial) novels from **[FreeWebNovel](https://freewebnovel.com)** into clean EPUB volumes using a FastAPI backend with a built‑in modern web UI. Includes real‑time WebSocket logs, cancel/stop controls, pagination, proxy rotation, selective chapter starting, and robust retry/block detection.

## 🧰 Key Features

### Core

- Full metadata capture (title, author, genres, language, status, synopsis, cover image)
- Robust chapter scraping (concurrent index scan or sequential crawl)
- Automatic EPUB volume splitting (`chapters_per_book`)
- Clean Table of Contents + intro/metadata page
- Embedded cover image (EPUB compatible)
- Paragraph counting per chapter (exposed in API response log_lines/summary)

### Modern Web UI

- Single‑page inline UI served at `/`
- Real‑time log panel via WebSocket (fallback to polling)
- Generate, cancel, download single/many/all, delete single/many/all
- Pagination + selectable page size for EPUB list
- Multi‑select + ZIP download (selected or all)
- Theme toggle (light/dark) persisted locally
- Log filtering (suppress access/polling noise)
- Start from a specific chapter without fetching earlier ones

### Control & Resilience

- Start from arbitrary chapter (`start_chapter`) – auto-switch to index scan mode when needed
- `chapter_workers` concurrent chapter fetchers with sticky per-worker proxies
- Retry with exponential backoff + adaptive block-page heuristics
- Permanent dead proxy disabling (`NEVER_REUSE_FAILED=1`)
- Cancellation endpoint + cooperative checkpoints (scrape + EPUB build)
- Smart adaptive accept heuristics to reduce false positives on block detection

### Deployment Friendly

- Dockerized (non‑root execution)
- Hugging Face Space compatible (Docker SDK header already present)
- Environment variable driven behavior (see full list below)

---

## 🏗️ Project Structure (Current)

```text
webnovel-to-epub/
├── api.py                  # Compatibility wrapper → re-exports scripts.api.app
├── main.py / main_api.py   # Entrypoint (main_api:app recommended)
├── static/
│   └── index.html          # Full single-page UI served at /
├── scripts/
│   ├── scraper.py          # Metadata + chapter acquisition (concurrent/sequential)
│   ├── convert_to_epub.py  # EPUB assembly (splitting & cover embedding)
│   ├── get_text_from_html.py # Chapter parsing helpers
│   ├── proxy_manager.py    # Proxy rotation, block detection, dead/quarantine logic
│   ├── cancellation.py     # Global cancellation token utilities
│   ├── api/                # Modular FastAPI app
│   │   ├── __init__.py     # create_app() and exported app; mounts /static
│   │   ├── routes_root.py  # GET / (serves static UI), GET /health
│   │   ├── routes_epub.py  # /epub/generate, /epub/cancel, /epub/stop, downloads
│   │   ├── routes_files.py # /epubs list + deletes
│   │   └── logs.py         # WebSocket + polling logs, stdout/err tee
│   └── proxy_list.csv      # (Optional) CSV proxy source
├── proxies.yaml            # (Optional) YAML proxy source
├── books/                  # Output EPUB volumes
├── media/                  # Downloaded/override images
├── Dockerfile              # Container build spec
├── entrypoint.sh           # Runtime launcher (uvicorn)
└── requirements.txt        # Dependencies
```

---

## 🧑‍💻 Requirements


```bash
pip install -r requirements.txt
```

Dependencies are pinned in `requirements.txt` (key libs: `requests`, `beautifulsoup4`, `ebooklib`, `fastapi`, `uvicorn`).

### 🔐 Configuration

1. Copy `.env.example` to `.env` and fill in your MongoDB connection plus Cloudflare R2 credentials:

   ```bash
   cp .env.example .env
   ```

   Every variable is optional—unset values fall back to sensible defaults so you can bring the service up locally without credentials.
2. (Optional) Verify Cloudflare R2 connectivity before generating EPUBs:

   ```bash
   python -m scripts.storage.check_r2 --probe
   ```

   The diagnostic lists remote objects and, with `--probe`, performs an upload/download/delete roundtrip to confirm access.


## 🚀 Quick Start (Web UI)

1. Install dependencies: `pip install -r requirements.txt`
2. Run the API (choose one):
   - `python main_api.py`
   - `uvicorn main_api:app --host 0.0.0.0 --port 7860`
   - `uvicorn scripts.api:app --host 0.0.0.0 --port 7860` (or `uvicorn api:app` via wrapper)
3. Open: `http://localhost:7860/` (serves `static/index.html`)
4. Paste a novel URL and click Generate.
5. Watch real‑time logs populate; download resulting EPUB(s).


### 🌩️ Cloudflare R2 Storage (Optional)

Set the following environment variables to automatically mirror generated EPUBs and cover art to Cloudflare R2 (S3-compatible):

| Variable | Purpose | Default |
|----------|---------|---------|
| `R2_ACCESS_KEY_ID` | Cloudflare R2 access key | — |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret | — |
| `R2_ACCOUNT_ID` | Cloudflare account ID (used if endpoint not provided) | — |
| `R2_BUCKET` | Target bucket name | `webnovel` |
| `R2_ENDPOINT_URL` | S3 API endpoint (e.g. `https://d34…r2.cloudflarestorage.com/webnovel`) | Provided default |
| `R2_PUBLIC_BASE_URL` | Optional override for public object URL base (e.g. custom domain) | Derived from endpoint |
| `R2_REGION` | Region hint (`auto` recommended) | `auto` |

When configured, generated files upload to `books/<novel_key>/…` and cover images to `images/<novel_key>/…`. The UI surfaces the public URL for direct downloads while backend endpoints continue to serve files (falling back to R2 if the local copy is absent).

### API Examples

Generate (JSON body):

```bash
curl -X POST http://localhost:7860/epub/generate \
   -H 'Content-Type: application/json' \
   -d '{
            "url":"https://freewebnovel.com/novel/i-can-transform-into-any-monster",
            "chapters_per_book":400,
            "chapter_workers":4,
            "start_chapter":120,
            "chapter_limit":0
         }'
```

Cancel an in‑flight generation:

```bash
curl -X POST http://localhost:7860/epub/cancel -H 'Content-Type: application/json' -d '{}'
```

Soft stop (finish current work and build partial EPUB):
```bash
curl -X POST http://localhost:7860/epub/stop -H 'Content-Type: application/json' -d '{}'
```

List EPUBs (paginated):

```bash
curl 'http://localhost:7860/epubs?offset=0&limit=20'
```

WebSocket logs (example JS snippet):

```js
const ws = new WebSocket('ws://localhost:7860/ws/logs');
ws.onmessage = e => console.log(JSON.parse(e.data));
```

Fallback polling:

```bash
curl 'http://localhost:7860/logs?since=0'
```

---

## 🔧 Parameters & Behavior

| Field | Description | Notes |
|-------|-------------|-------|
| url | Novel index or first chapter URL | Index preferred for concurrency |
| chapters_per_book | Split threshold per EPUB | Default 500 |
| chapter_workers | Parallel fetch workers | 0/None = sequential crawl |
| chapter_limit | Hard cap on number of chapters | 0 = unlimited |
| start_chapter | Skip all chapters before this number | Auto-forces index scan if workers=0 |

When `start_chapter > 1` and `chapter_workers <= 0`, the system automatically promotes to a single‑worker index parsing mode to avoid sequentially traversing unwanted early chapters.

---

## ⚠️ Notes & Heuristics

- Block detection uses status codes + keyword signals (captcha/access denied/etc.) with adaptive fallback.
- `ADAPTIVE_BLOCK` + `LENIENT_ON_BLOCK` can allow near‑valid pages to pass if they have sufficient size or chapter‑like tokens.
- Paragraph counts are approximate (split on blank lines then fallback to single newlines).
- Cover download failures are non‑fatal; EPUB still builds.
- Permanent dead proxies accumulate when `NEVER_REUSE_FAILED=1` (default). Restart resets in‑memory state.

---

## 🌐 Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| PRIMARY_PROXY | Force a single proxy for all requests | (unset) |
| DISABLE_PUBLIC_PROXIES | Ignore loaded proxy lists | 0 |
| SCRAPER_UA | Override User-Agent | (rotating pool) |
| MIN_PROXY_HEALTH | Quarantine threshold (<= triggers) | -3 |
| RETRY_BACKOFF_BASE | Initial backoff seconds | 0.6 |
| MAX_BACKOFF | Max backoff cap | 4.0 |
| ENABLE_BLOCK_DETECT | Enable block page detection | 1 |
| SHORT_CIRCUIT_ON_FIRST_403 | Stop retry chain early on 403 | 1 |
| LENIENT_ON_BLOCK | Accept page even if block flagged | 0 |
| ADAPTIVE_BLOCK | Allow adaptive accept heuristics | 1 |
| BLOCK_MIN_CONTENT_BYTES | Size threshold for adaptive accept | 3000 |
| BLOCK_EXPECT_PATTERNS | CSV of keywords hinting real content | chapter,read,next |
| BLOCK_SIGNAL_MIN_HITS | Min block-signal keywords required | 1 |
| BLOCK_ACCEPT_IF_METADATA | Accept if novel metadata markers present | 1 |
| NEVER_REUSE_FAILED | Permanently retire failing/blocked proxies | 1 |

Tips:

- Use `PRIMARY_PROXY` for a known stable private proxy (reduces rotation noise).
- Set `DISABLE_PUBLIC_PROXIES=1` to force only direct / primary proxy usage.
- Tune `chapter_workers` cautiously—too many parallel requests can trigger anti‑bot responses sooner.

---

## 🧪 Response Example (Truncated)

POST `/epub/generate` returns (on success):

```json
{
   "ok": true,
   "data": {
      "filenames": ["i_can_transform_into_any_monster-i.epub"],
      "count": 1,
      "chapters": 120,
      "paragraph_counts": [34, 29, 31, ...],
      "summary": [
         "Chapter 120 Awakening (28 paragraphs)",
         "Chapter 121 First Trial (31 paragraphs)"
      ],
      "log_lines": [
         ">>> Got the metadata for I Can Transform Into Any Monster by: Someone",
         "✅ Chapter 120 Awakening (28 paragraphs)",
         "✅ Chapter 121 First Trial (31 paragraphs)"
      ]
   }
}
```

If cancelled mid‑process: HTTP 499 with `{ ok:false, error:{ code:"cancelled" ... } }`.

## 📜 License

MIT

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

Then open: <http://localhost:7860/docs>

### Minimal Docker Run

### Hugging Face Space (Docker)

1. Create a Docker Space.
2. Add the repository contents (or point to your GitHub fork).
3. Ensure `Dockerfile` exists at root (provided).
4. Add environment variables in the Space settings (especially `PRIMARY_PROXY` if needed).
5. Space automatically builds and exposes at port 7860.

#### Using as a Hugging Face Docker Space

This repo is configured for `sdk: docker` (see YAML header). The Space build process will:

1. Install dependencies from `requirements.txt` inside the Docker image.
2. Expose port `7860` (FastAPI served by Uvicorn).
3. Run `entrypoint.sh` which launches `main_api:app`.

You can monitor build logs in the Space "Logs" tab. On success, open the **App** tab or call the documented endpoints under `/docs`.

#### Custom Environment Variables (set in Space Settings)

| Variable | Purpose |
|----------|---------|
| PRIMARY_PROXY | Force a single proxy for all requests |
| DISABLE_PUBLIC_PROXIES | If `1`, ignore rotating proxy list |
| SCRAPER_UA | Override default/rotating User-Agent header |
| MIN_PROXY_HEALTH | Threshold to quarantine poor proxies (default -3) |
| RETRY_BACKOFF_BASE | Initial backoff in seconds (float) |
| MAX_BACKOFF | Cap for exponential backoff |
| ENABLE_BLOCK_DETECT | If `1`, enable simple block-page detection |
| SHORT_CIRCUIT_ON_FIRST_403 | If `1`, abort retry sequence early on 403 |
| LENIENT_ON_BLOCK | If `1`, accept suspected block pages instead of failing |
| ADAPTIVE_BLOCK | If `1`, allow heuristic accept of large pages w/ chapter keywords |
| BLOCK_MIN_CONTENT_BYTES | Size threshold for adaptive accept (default 3000) |
| BLOCK_EXPECT_PATTERNS | Comma list of keywords hinting real content (default: chapter,read,next) |
| BLOCK_SIGNAL_MIN_HITS | Minimum block-indicator terms before treating as blocked (default 1) |
| BLOCK_ACCEPT_IF_METADATA | If `1`, allow pages with novel metadata even if block signals present |

Add them as **Variables** (non-sensitive) or **Secrets** (for proxy credentials). They are read via standard `os.environ.get()` calls inside the proxy logic.

#### Persistent Storage

If you enable persistent storage for the Space, adjust paths to store produced books under `/data/books` (create directory) and media under `/data/media` for durability. Current default writes to in-container `books/` and `media/` which are ephemeral across restarts without persistence.

#### Health & Testing

After build:
```bash
curl -s https://<space-subdomain>.hf.space/health
```
Expect: `{ "status": "ok" }`

Generate EPUB via API (example):
```bash
curl -X POST https://<space-subdomain>.hf.space/epub/generate \
   -H "Content-Type: application/json" \
   -d '{"url":"https://freewebnovel.com/novel/i-can-transform-into-any-monster","chapters_per_book":400,"chapter_workers":0}'
```

List produced EPUBs:
```bash
curl -s https://<space-subdomain>.hf.space/epubs | jq
```

Download one (GET endpoint):
```bash
curl -L "https://<space-subdomain>.hf.space/epub/download?name=i_can_transform_into_any_monster-i.epub" -o book.epub
```

---

### Health & Basic Checks

```bash
curl -s http://localhost:7860/health
curl -s http://localhost:7860/logs?since=0
```

---

## 🛠 Potential Future Enhancements

- Persist proxy health across restarts (file/DB)
- Progress/status endpoint (percentage, current chapter)
- Search/filter logs client-side
- Export logs as downloadable text
- Chapter content caching layer
- Multi-source site abstraction

---

Happy scraping & reading! 📚
