from bs4 import BeautifulSoup as soup
import time
from scripts.proxy_manager import fetch_with_proxy_rotation
import requests
from urllib.parse import urljoin
import re

def get_chapter_data(chapter_url: str, *, preferred_proxy: str | None = None, avoid_proxies: list[str | None] | None = None):
    try:
        response = fetch_with_proxy_rotation(
            chapter_url,
            retries=5,
            timeout=15,
            preferred_first_proxy=preferred_proxy,
            allow_no_proxy=True,
            avoid_proxies=avoid_proxies,
        )
        chap_soup = soup(response.content, "html.parser")
    except Exception as e:
        print(f"❌ Exhausted retries for chapter URL: {chapter_url}\n{e}")
        return None, "Error fetching page", ""

    # Get next chapter URL (robust variants)
    next_chapter_url = None
    # Common patterns for next chapter anchors
    title_variants = [
        "Read Next chapter",
        "Next Chapter",
        "Read Next Chapter",
        "Next",
    ]
    # 1) Try title attribute variants
    for t in title_variants:
        tag = chap_soup.find('a', title=t)
        if tag and tag.get('href'):
            next_chapter_url = tag['href']
            break
    # 2) Try rel="next"
    if not next_chapter_url:
        tag = chap_soup.find('a', rel=lambda v: v and 'next' in v)
        if tag and tag.get('href'):
            next_chapter_url = tag['href']
    # 3) Try text-based match
    if not next_chapter_url:
        for a in chap_soup.find_all('a'):
            txt = a.get_text(strip=True).lower()
            if re.search(r"\bnext\b", txt) and a.get('href'):
                next_chapter_url = a['href']
                break
    # 4) Try chapter number increment heuristic
    if not next_chapter_url:
        m = re.search(r"/chapter[-_](\d+)", chapter_url, re.IGNORECASE)
        if m:
            try:
                n = int(m.group(1))
                next_num = n + 1
                for a in chap_soup.find_all('a', href=True):
                    href = a['href']
                    if re.search(rf"/chapter[-_]({next_num})(?:\b|/|$)", href, re.IGNORECASE):
                        next_chapter_url = href
                        break
            except Exception:
                pass
    if not next_chapter_url:
        print("⚠️ Next Chapter link not found.")

    chapter_title = ""
    chapter_text_parts = []

    # Find the main content container
    txt_div = (
        chap_soup.find("div", class_="m-read")
        or chap_soup.find("div", id="article")
        or chap_soup.select_one("#article, .txt, .txt-article, .read-content, .chapter-content")
    )
    if txt_div:
        # Extract title from the first heading inside #article (if it exists)
        chapter_span = txt_div.find("span", class_="chapter")
        if chapter_span:
            chapter_title =  chapter_span.get_text(strip=True)
        article_div = txt_div if getattr(txt_div, 'get', None) and txt_div.get('id') == 'article' else txt_div.find("div", id="article")
        if not chapter_title:
            chapter_title_tag = txt_div.find(["h1", "h2", "h3", "h4", "span"])
            chapter_title = chapter_title_tag.get_text(strip=True) if chapter_title_tag else ""

        # Extract all <p> tags within the "txt " div
        for p in (article_div or txt_div).find_all("p"):
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
        print("❌ Chapter content container not found.")
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