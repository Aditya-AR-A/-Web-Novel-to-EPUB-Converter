import requests
from bs4 import BeautifulSoup as soup

def get_chapter_data(chapter_url: str):
    response = requests.get(chapter_url).content
    chap_soup = soup(response, "html.parser")

    next_chapter_tag = chap_soup.find('a', title="Read Next chapter")
    if next_chapter_tag:
        next_chapter_url = next_chapter_tag['href']
    else:
        next_chapter_url = None
        print("Next Chapter link not found.")


    # Extract chapter title (assumed to be in <h4>)
    chapter_title_tag = chap_soup.find("h4")
    chapter_title = chapter_title_tag.get_text(strip=True) if chapter_title_tag else "No title found"

    # Extract chapter text: all <p> tags after the <h4>
    chapter_text_parts = []
    for tag in chapter_title_tag.find_all_next():
        if tag.name == "p":
            chapter_text_parts.append(tag.get_text(strip=True))
        elif tag.name == "h4":  # Stop at next chapter title (if scraping multiple chapters)
            break

    chapter_text = "\n".join(chapter_text_parts)

    print("Chapter Title:", chapter_title)

    # print("Chapter Text:", chapter_text)
    # print("Next Chapter Link:", next_chapter_url)



    return (next_chapter_url, chapter_title, chapter_text)


if __name__ == "__main__":
    get_chapter_data("https://freewebnovel.com/novel/i-can-transform-into-any-monster/chapter-1")