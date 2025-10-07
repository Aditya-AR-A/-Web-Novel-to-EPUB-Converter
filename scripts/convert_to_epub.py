from ebooklib import epub
import os
import math
import uuid
from html import escape as _esc

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


def to_epub(metadata, chapter_data, chapters_per_book=500):
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

    for book_index in range(num_books):
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

        front_body = "<div class='front-container'>" + \
            (f"<div class='cover'>{cover_img_html}</div>" if cover_img_html else '') + \
            f"<h1>{title}</h1>" + \
            f"<h2>by {author}</h2>" + \
            "<div class='meta'>" + \
            (f"<b>Status:</b> {status} &nbsp; " if status else '') + \
            (f"<b>Language:</b> {language} &nbsp; " if language else '') + \
            "</div>" + \
            genres_html + \
            tags_html + \
            (f"<div class='synopsis'><b>Synopsis:</b> {synopsis}</div>" if synopsis else '') + \
            "</div>"

        front_page = epub.EpubHtml(title="Front Page", file_name="front.xhtml", lang="en")
        front_page.content = f"<html><head><title>{title} - Front Page</title><style>{style}</style></head><body>{front_body}</body></html>"
        book.add_item(front_page)
        start_idx = book_index * chapters_per_book
        end_idx = min(start_idx + chapters_per_book, total_chapters)
        epub_chapters = [front_page]

        for idx in range(start_idx, end_idx):
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

        os.makedirs("books", exist_ok=True)
        epub.write_epub(f'books/{filename}', book, {})
        print(f"✅ EPUB created: {filename}")


def create_epub(
    *,
    chapters,
    title=None,
    author=None,
    cover_image=None,
    genres=None,
    tags=None,
    output_path=None,
    metadata=None,
):
    """Build a single EPUB file at the requested ``output_path``.

    This mirrors the interface used by the FastAPI service layer while
    reusing the richer styling already present in ``to_epub``.
    """

    if not output_path:
        raise ValueError("output_path is required for create_epub")

    meta = dict(metadata or {})
    book_title = meta.get("title") or title or "Untitled"
    book_author = meta.get("author") or author or "Unknown"
    book_language = meta.get("language") or "en"
    book_status = meta.get("status") or ""
    book_synopsis = meta.get("synopsis") or ""
    book_genres = genres or meta.get("genres") or []
    book_tags = tags or meta.get("tags") or []

    titles_in = chapters.get("title", []) or []
    texts_in = chapters.get("text", []) or []
    total = min(len(titles_in), len(texts_in))
    filtered_titles = []
    filtered_texts = []
    for idx in range(total):
        t = (titles_in[idx] or "").strip()
        x = (texts_in[idx] or "").strip()
        if not x:
            continue
        if not t:
            t = f"Chapter {idx+1}"
        filtered_titles.append(t)
        filtered_texts.append(x)

    if not filtered_titles:
        raise RuntimeError("No valid chapter content collected (all chapters empty).")

    book = epub.EpubBook()
    book.set_identifier(meta.get("identifier") or f"webnovel-{uuid.uuid4()}")
    book.set_title(book_title)
    book.set_language(book_language)
    if book_author:
        book.add_author(book_author)

    cover_img_html = ""
    cover_path = cover_image or meta.get("image_path")
    if cover_path and os.path.exists(cover_path):
        with open(cover_path, "rb") as img_file:
            cover_image_bytes = img_file.read()
        book.set_cover("cover.jpg", cover_image_bytes)
        cover_img_html = "<img src=\"cover.jpg\" alt=\"cover\" style=\"max-width:220px;display:block;margin:2rem auto 1rem auto;border-radius:8px;box-shadow:0 2px 8px #aaa;\" />"

    style = (
        "body{font-family:sans-serif;background:#f8f8f8;margin:0;}"
        " .front-container{max-width:500px;margin:3rem auto 2rem auto;padding:2rem;background:#fff;border-radius:12px;box-shadow:0 2px 12px #ddd;}"
        " h1{font-size:2rem;margin-bottom:0.5rem;}"
        " h2{font-size:1.2rem;color:#555;margin-top:0;}"
        " .meta{margin:1rem 0 1.5rem 0;font-size:1rem;color:#444;}"
        " .genres{margin:1rem 0 1.5rem 0;display:flex;flex-wrap:wrap;gap:0.5em;}"
        " .genre-tile{display:inline-block;background:#ffe0e0;color:#a33;padding:0.35em 1em;margin:0.2em 0.4em 0.2em 0;border-radius:8px;font-size:1em;box-shadow:0 1px 4px #f3bcbc;}"
        " .tags{margin:0.5rem 0;}"
        " .tag{display:inline-block;background:#e0e7ff;color:#333;padding:0.2em 0.7em;margin:0 0.3em 0.3em 0;border-radius:6px;font-size:0.95em;}"
        " .cover{margin-bottom:1.5rem;}"
        " .synopsis{margin-top:1.5rem;font-size:1.05rem;color:#222;}"
    )

    tags_html = ""
    if book_tags:
        tags_html = '<div class="tags">' + ''.join(f'<span class="tag">{_esc(str(tag).strip())}</span>' for tag in book_tags) + '</div>'

    genres_html = ""
    if book_genres:
        genres_html = '<div class="genres">' + ''.join(f'<span class="genre-tile">{_esc(str(genre).strip())}</span>' for genre in book_genres) + '</div>'

    synopsis_html = f"<div class='synopsis'><b>Synopsis:</b> {_esc(book_synopsis)}</div>" if book_synopsis else ""

    front_body = (
        "<div class='front-container'>"
        + (f"<div class='cover'>{cover_img_html}</div>" if cover_img_html else "")
        + f"<h1>{_esc(book_title)}</h1>"
        + (f"<h2>by {_esc(book_author)}</h2>" if book_author else "")
        + "<div class='meta'>"
        + (f"<b>Status:</b> {_esc(book_status)} &nbsp; " if book_status else "")
        + (f"<b>Language:</b> {_esc(book_language)} &nbsp; " if book_language else "")
        + "</div>"
        + genres_html
        + tags_html
        + synopsis_html
        + "</div>"
    )

    front_page = epub.EpubHtml(title="Front Page", file_name="front.xhtml", lang="en")
    front_page.content = f"<html><head><title>{_esc(book_title)} - Front Page</title><style>{style}</style></head><body>{front_body}</body></html>"
    book.add_item(front_page)

    epub_chapters = [front_page]
    for idx, (chapter_title, raw_content) in enumerate(zip(filtered_titles, filtered_texts), start=1):
        safe_title = _esc(chapter_title)
        paragraphs = [para.strip() for para in raw_content.split('\n') if para.strip()]
        chapter_body = f"<h1>{safe_title}</h1>" + ''.join(f"<p>{_esc(para)}</p>" for para in paragraphs)
        chapter = epub.EpubHtml(
            title=chapter_title or f"Chapter {idx}",
            file_name=f"chap_{idx:04d}.xhtml",
            lang=book_language,
        )
        chapter.content = f"<html><head><title>{safe_title}</title></head><body>{chapter_body}</body></html>"
        book.add_item(chapter)
        epub_chapters.append(chapter)

    book.toc = tuple(epub_chapters)
    book.spine = epub_chapters

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    epub.write_epub(output_path, book, {})
    print(f"✅ EPUB created: {output_path}")
    return output_path
