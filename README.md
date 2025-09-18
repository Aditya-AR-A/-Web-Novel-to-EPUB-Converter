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

This project allows you to **scrape full novels from [FreeWebNovel](https://freewebnovel.com)** and convert them into a clean `.epub` file, including metadata like title, author, cover image, synopsis, and chapter formatting.

## 🧰 Features

- Automatically scrapes all chapters of a web novel.
- Saves metadata: title, author, genres, language, status, cover image, synopsis.
- Converts content into a structured EPUB file.
- Includes **TOC (Table of Contents)** and **intro section**.
- Downloads and embeds **cover image** as proper EPUB cover.

---

## 🏗️ Project Structure

```
Web-to-EPUB/
│
├── main.py                  # Entry point
├── scraper.py              # Scrapes metadata and chapter content
├── convert_to_epub.py      # Converts data to .epub file
├── get_text_from_html.py   # Extracts chapter content (your logic here)
├── media/                  # Downloaded images
└── output/                 # Final EPUB files (recommended)
```

---

## 🧑‍💻 Requirements

- Python 3.8+
- Install dependencies:

```bash
pip install -r requirements.txt
```

### `requirements.txt`
```
requests
beautifulsoup4
ebooklib
```

---

## 🚀 Usage (CLI)

```bash
python main.py
```

The script:
1. Scrapes metadata from the novel page.
2. Extracts all chapters sequentially.
3. Builds a styled `.epub` file with:
   - Title, author, cover image
   - Intro page with genres, status, and synopsis
   - TOC
   - All chapters with formatting preserved

Final output: `output/i_can_transform.epub`

---

## 📝 Customization

- To change the novel, modify the `url` variable in `main.py`:

```python
url = "https://freewebnovel.com/novel/i-can-transform-into-any-monster"
```

---

## ⚠️ Notes

- Make sure the novel title in the `<a title=...>` selector matches exactly (watch for quotes and symbols).
- If EPUB readers don’t show the **cover image**, it's likely due to EPUB2/EPUB3 reader compatibility — the image is correctly embedded.

---

## 📖 Example

Example EPUB created:
- Title: *I Can Transform Into Any Monster*
- Chapters: ~200
- EPUB Size: ~1–2 MB with cover and formatted text

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
