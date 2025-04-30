from ebooklib import epub
import os

def to_epub(metadata, chapter_data):
    book = epub.EpubBook()

    # Basic metadata
    book.set_identifier('id123456')
    book.set_title(metadata['title'])
    book.set_language(metadata['language'])
    book.add_author(metadata['author'])

    # Add genres to metadata
    for genre in metadata.get("genres", []):
        book.add_metadata('DC', 'subject', genre)

    # Add cover image
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
        book.set_cover("cover.jpg", cover_image)  # still sets thumbnail

    # Create intro with image and metadata
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

    # === Chapters ===
    epub_chapters = [intro_chap]
    for idx, (title, raw_content) in enumerate(zip(chapter_data['title'], chapter_data['text'])):
        clean_content = ''.join(f"<p>{para.strip()}</p>" for para in raw_content.split('\n') if para.strip())
        chapter = epub.EpubHtml(title=title, file_name=f'chap_{idx+1}.xhtml', lang='en')
        chapter.content = f"<h1>{title}</h1>{clean_content}"
        book.add_item(chapter)
        epub_chapters.append(chapter)

    # === TOC, Spine, CSS ===
    book.toc = tuple(epub_chapters)

    # Put intro before nav
    book.spine = epub_chapters + ['nav']
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Add optional CSS
    style = 'body { font-family: Arial, serif; line-height: 1.6; }'
    nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css",
                            media_type="text/css", content=style)
    book.add_item(nav_css)

    # Add cover image to manifest explicitly
    if cover_img_item:
        book.add_item(cover_img_item)

    # Save
    filename = metadata['title'].replace(" ", "_").lower() + '.epub'
    epub.write_epub('books\\' + filename, book, {})
    print(f"✅ EPUB created: {filename}")
