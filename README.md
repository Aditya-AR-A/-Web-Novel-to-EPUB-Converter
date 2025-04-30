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

## 🚀 Usage

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