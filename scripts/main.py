from scraper import get_chapter_metadata, get_chapters
from convert_to_epub import to_epub


if __name__ == "__main__":
    url = "https://freewebnovel.com/novel/martial-peak-rise-of-the-human-emperor"

    metadata = get_chapter_metadata(url)
    chapters = get_chapters(metadata["starting_url"])
    to_epub(metadata, chapters)
