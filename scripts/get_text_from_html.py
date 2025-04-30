import requests
from bs4 import BeautifulSoup as soup
import time

def get_chapter_data(chapter_url: str):
    try:
        response = requests.get(chapter_url, timeout=10)
        response.raise_for_status()
        chap_soup = soup(response.content, "html.parser")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching chapter URL: {chapter_url}\n{e}")
        return None, "Error fetching page", ""

    # Get next chapter URL
    next_chapter_tag = chap_soup.find('a', title="Read Next chapter")
    next_chapter_url = next_chapter_tag['href'] if next_chapter_tag else None
    if not next_chapter_tag:
        print("⚠️ Next Chapter link not found.")

    chapter_title = ""
    chapter_text_parts = []

    # Find the parent div with class "txt "
    txt_div = chap_soup.find("div", class_="m-read")
    if txt_div:
        # Extract title from the first heading inside #article (if it exists)
        chapter_span = txt_div.find("span", class_="chapter")
        if chapter_span:
            chapter_title =  chapter_span.get_text(strip=True)
        article_div = txt_div.find("div", id="article")
        if not chapter_title:
            chapter_title_tag = txt_div.find(["h1", "h2", "h3", "h4", "span"])
            chapter_title = chapter_title_tag.get_text(strip=True) if chapter_title_tag else ""

        # Extract all <p> tags within the "txt " div
        for p in txt_div.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                chapter_text_parts.append(text)

        if not chapter_title and article_div:
            # Fallback title if not found in headings within article
            first_paragraph = article_div.find("p")
            if first_paragraph and len(first_paragraph.get_text(strip=True)) > 5:
                chapter_title = first_paragraph.get_text(strip=True)[:60] + "..."
            elif chapter_text_parts and len(chapter_text_parts[0]) > 5:
                chapter_title = chapter_text_parts[0][:60] + "..."
            else:
                chapter_title = "Untitled Chapter"

        elif not chapter_title and chapter_text_parts:
            # Fallback title if no article div but text exists
            if len(chapter_text_parts[0]) > 5:
                chapter_title = chapter_text_parts[0][:60] + "..."
            else:
                chapter_title = "Untitled Chapter"
        elif not chapter_title:
            chapter_title = "Untitled Chapter"

    else:
        print("❌ Parent div with class 'txt ' not found.")
        return next_chapter_url, "No content found", ""

    chapter_text = "\n\n".join(chapter_text_parts)

    if len(chapter_text.strip()) == 0:
        print("⚠️ Chapter text appears empty.")
        next_chapter_url = None  # Prevents infinite loop on dead pages

    print(f"✅ {chapter_title} ({len(chapter_text_parts)} paragraphs)")

    # time.sleep(1.5)  # be polite to server

    return next_chapter_url, chapter_title, chapter_text

if __name__ == "__main__":
    get_chapter_data("https://freewebnovel.com/novel/god-of-milfs-the-gods-request-me-to-make-a-milf-harem/chapter-75")
    # Test with another URL where content might be structured differently
    # get_chapter_data("ANOTHER_URL_HERE")