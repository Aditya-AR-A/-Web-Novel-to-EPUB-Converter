from scraper import get_chapter_metadata, get_chapters
from convert_to_epub import to_epub


def create_ebook(url):
    metadata = get_chapter_metadata(url)
    chapters = get_chapters(metadata["starting_url"])
    to_epub(metadata, chapters)



if __name__ == "__main__":
    # url = "https://freewebnovel.com/novel/god-of-milfs-the-gods-request-me-to-make-a-milf-harem"
    with open('urls.txt', 'r') as f:
        for link in f.readlines():
            final_link = link.split('\n')[0]
            create_ebook(final_link)
    