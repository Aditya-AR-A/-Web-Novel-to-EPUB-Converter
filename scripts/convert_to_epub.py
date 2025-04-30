from ebooklib import epub
import os
import math

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
    total_chapters = len(chapter_data['title'])
    num_books = math.ceil(total_chapters / chapters_per_book)

    for book_index in range(num_books):
        book = epub.EpubBook()
        book.set_identifier(f'id123456-part{book_index+1}')
        book.set_title(metadata['title'])
        book.set_language('en')
        book.add_author(metadata['author'])

        for genre in metadata.get("genres", []):
            book.add_metadata('DC', 'subject', genre)

        # Add cover if exists
        cover_img_item = None
        if os.path.exists(metadata['image_path']):
            with open(metadata['image_path'], 'rb') as img_file:
                cover_image = img_file.read()
            cover_img_item = epub.EpubItem(
                uid="cover_image",
                file_name="images/cover.jpg",
                media_type="image/jpeg",
                content=cover_image
            )
            book.add_item(cover_img_item)
            book.set_cover("cover.jpg", cover_image)

        # Add intro/synopsis chapter
        intro_html = f"""
            <h1>{metadata['title']}</h1>
            <img src="images/cover.jpg" alt="cover" style="width:200px;"/>
            <p><strong>Author:</strong> {metadata['author']}</p>
            <p><strong>Language:</strong> {metadata['language']}</p>
            <p><strong>Status:</strong> {metadata['status']}</p>
            <p><strong>Genres:</strong> {', '.join(metadata['genres'])}</p>
            <h2>Synopsis</h2>
            <p>{metadata['synopsis'].replace('\n', '<br>')}</p>
        """
        intro_chap = epub.EpubHtml(title="Introduction", file_name='intro.xhtml', lang='en')
        intro_chap.content = intro_html
        book.add_item(intro_chap)

        # Add chapters for this volume
        start_idx = book_index * chapters_per_book
        end_idx = min(start_idx + chapters_per_book, total_chapters)
        epub_chapters = [intro_chap]

        for idx in range(start_idx, end_idx):
            title = chapter_data['title'][idx]
            raw_content = chapter_data['text'][idx]
            clean_content = ''.join(f"<p>{para.strip()}</p>" for para in raw_content.split('\n') if para.strip())
            chapter = epub.EpubHtml(
                title=title,
                file_name=f'chap_{idx+1}.xhtml',
                lang='en'
            )
            chapter.content = f"<h1>{title}</h1>{clean_content}"
            book.add_item(chapter)
            epub_chapters.append(chapter)

        # Correct TOC and spine
        book.toc = tuple(epub_chapters)
        book.spine = ['nav'] + epub_chapters  # intro + current chapters

        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Add style
        style = 'body { font-family: Arial, serif; line-height: 1.6; }'
        nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css",
                                media_type="text/css", content=style)
        book.add_item(nav_css)

        if cover_img_item:
            book.add_item(cover_img_item)

        roman_part = int_to_roman(book_index + 1)
        filename = metadata['title'].replace(" ", "_").replace(":", "_").lower() + f"-{roman_part}.epub"

        os.makedirs("books", exist_ok=True)
        epub.write_epub(f'books/{filename}', book, {})
        print(f"✅ EPUB created: {filename}")
