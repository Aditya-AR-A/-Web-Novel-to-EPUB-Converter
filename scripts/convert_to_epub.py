from __future__ import annotations

import math
import os
from pathlib import Path

from ebooklib import epub

from scripts.cancellation import raise_if_cancelled
from scripts.config import BOOKS_DIR as DEFAULT_BOOKS_DIR

def int_to_roman(input):
    if not isinstance(input, int):
        raise TypeError("Expected integer")
    if not 0 < input < 4000:
        raise ValueError("Argument must be between 1 and 3999")
    numerals = [
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")
    ]
    result = ""
    for value, numeral in numerals:
        while input >= value:
            result += numeral
            input -= value
    return result


def to_epub(metadata, chapter_data, chapters_per_book=500, *, output_dir: str | os.PathLike[str] | None = None):
    # Minimal valid EPUB: only chapters, no custom CSS, no extra pages
    titles_in = chapter_data.get('title', []) or []
    texts_in = chapter_data.get('text', []) or []
    total = min(len(titles_in), len(texts_in))
    filtered_titles = []
    filtered_texts = []
    for i in range(total):
        t = (titles_in[i] or '').strip()
        x = (texts_in[i] or '').strip()
        if not x:
            continue
        if not t:
            t = f"Chapter {i+1}"
        filtered_titles.append(t)
        filtered_texts.append(x)

    if not filtered_titles:
        raise RuntimeError("No valid chapter content collected (all chapters empty).")

    total_chapters = len(filtered_titles)
    num_books = math.ceil(total_chapters / chapters_per_book)

    output_base = Path(output_dir or DEFAULT_BOOKS_DIR)
    output_base.mkdir(parents=True, exist_ok=True)
    produced_files: list[str] = []

    for book_index in range(num_books):
        raise_if_cancelled()
        book = epub.EpubBook()
        book.set_identifier(f'id123456-part{book_index+1}')
        book.set_title(metadata.get('title', 'Untitled'))
        book.set_language('en')
        book.add_author(metadata.get('author', 'Unknown'))

        # Enhanced front page HTML with simple styling and more metadata
        title = metadata.get('title', 'Untitled')
        author = metadata.get('author', 'Unknown')
        genres_list = metadata.get('genres', [])
        tags = ', '.join(metadata.get('tags', [])) if 'tags' in metadata else ''
        status = metadata.get('status', '')
        language = metadata.get('language', '')
        synopsis = metadata.get('synopsis', '')
        cover_img_html = ''
        cover_path = metadata.get('image_path')
        if cover_path and os.path.exists(cover_path):
            with open(cover_path, 'rb') as img_file:
                cover_image = img_file.read()
            book.set_cover("cover.jpg", cover_image)
            cover_img_html = '<img src="cover.jpg" alt="cover" style="max-width:220px;display:block;margin:2rem auto 1rem auto;border-radius:8px;box-shadow:0 2px 8px #aaa;" />'

        # Enhanced CSS for genre tiles and spacing
        style = "body{font-family:sans-serif;background:#f8f8f8;margin:0;} .front-container{max-width:500px;margin:3rem auto 2rem auto;padding:2rem 2rem 2rem 2rem;background:#fff;border-radius:12px;box-shadow:0 2px 12px #ddd;} h1{font-size:2rem;margin-bottom:0.5rem;} h2{font-size:1.2rem;color:#555;margin-top:0;} .meta{margin:1rem 0 1.5rem 0;font-size:1rem;color:#444;} .genres{margin:1rem 0 1.5rem 0;display:flex;flex-wrap:wrap;gap:0.5em;} .genre-tile{display:inline-block;background:#ffe0e0;color:#a33;padding:0.35em 1em;margin:0.2em 0.4em 0.2em 0;border-radius:8px;font-size:1em;box-shadow:0 1px 4px #f3bcbc;} .tags{margin:0.5rem 0;} .tag{display:inline-block;background:#e0e7ff;color:#333;padding:0.2em 0.7em;margin:0 0.3em 0.3em 0;border-radius:6px;font-size:0.95em;} .cover{margin-bottom:1.5rem;} .synopsis{margin-top:1.5rem;font-size:1.05rem;color:#222;}"

        tags_html = ''
        if tags:
            tags_html = '<div class="tags">' + ''.join(f'<span class="tag">{t.strip()}</span>' for t in tags.split(',')) + '</div>'

        genres_html = ''
        if genres_list:
            genres_html = '<div class="genres">' + ''.join(f'<span class="genre-tile">{g.strip()}</span>' for g in genres_list) + '</div>'

        front_body = (
            "<div class='front-container'>"
            + (f"<div class='cover'>{cover_img_html}</div>" if cover_img_html else '')
            + f"<h1>{title}</h1>"
            + f"<h2>by {author}</h2>"
            + "<div class='meta'>"
            + (f"<b>Status:</b> {status} &nbsp; " if status else '')
            + (f"<b>Language:</b> {language} &nbsp; " if language else '')
            + "</div>"
            + genres_html
            + tags_html
            + (f"<div class='synopsis'><b>Synopsis:</b> {synopsis}</div>" if synopsis else '')
            + "</div>"
        )

        front_page = epub.EpubHtml(title="Front Page", file_name="front.xhtml", lang="en")
        front_page.content = f"<html><head><title>{title} - Front Page</title><style>{style}</style></head><body>{front_body}</body></html>"
        book.add_item(front_page)
        start_idx = book_index * chapters_per_book
        end_idx = min(start_idx + chapters_per_book, total_chapters)
        epub_chapters = [front_page]

        for idx in range(start_idx, end_idx):
            raise_if_cancelled()
            title = filtered_titles[idx]
            raw_content = filtered_texts[idx]
            paras = [p.strip() for p in raw_content.split('\n') if p.strip()]
            chapter_body = f"<h1>{title}</h1>" + ''.join(f"<p>{p}</p>" for p in paras)
            chapter = epub.EpubHtml(
                title=title,
                file_name=f'chap_{idx+1}.xhtml',
                lang='en'
            )
            chapter.content = f"<html><head><title>{title}</title></head><body>{chapter_body}</body></html>"
            book.add_item(chapter)
            epub_chapters.append(chapter)

        # TOC and spine: front page first
        book.toc = tuple(epub_chapters)
        book.spine = epub_chapters

        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        roman_part = int_to_roman(book_index + 1)
        filename = metadata.get('title', 'untitled').replace(" ", "_").replace(":", "_").lower() + f"-{roman_part}.epub"

        target_path = output_base / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)
        epub.write_epub(str(target_path), book, {})
        produced_files.append(filename)
        print(f"✅ EPUB created: {target_path}")

    return produced_files
