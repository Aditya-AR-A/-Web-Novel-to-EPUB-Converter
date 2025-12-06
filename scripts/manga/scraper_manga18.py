"""
Manga18.club Scraper
Scrapes manga/manhwa from manga18.club

URL Format: https://manga18.club/manhwa/{slug}
Chapter URL: https://manga18.club/manhwa/{slug}/chap-{num}
"""

import re
import base64
import json
import cloudscraper
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


# Create a shared cloudscraper instance with browser emulation
_scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'mobile': False
    }
)


def _log(msg: str):
    print(f"[manga18] {msg}")


def _get(url: str, referer: str = None):
    """Make a GET request with cloudscraper to bypass Cloudflare."""
    headers = {
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    return _scraper.get(url, headers=headers, timeout=30)


def extract_slug_from_url(url: str) -> Optional[str]:
    """Extract manga slug from manga18.club URL."""
    # https://manga18.club/manhwa/family-secret
    # https://manga18.club/manhwa/family-secret/chap-1
    m = re.search(r"manga18\.club/manhwa/([^/]+)", url)
    return m.group(1) if m else None


def get_manga_metadata(source_url: str) -> Dict:
    """
    Get manga metadata from manga18.club.
    
    Args:
        source_url: Manga18.club manga URL
    
    Returns:
        Dictionary with manga metadata
    """
    _log(f"📖 Fetching metadata from: {source_url}")
    
    slug = extract_slug_from_url(source_url)
    if not slug:
        raise RuntimeError("Invalid manga18.club URL - could not extract slug")
    
    # Ensure we're on the main manga page, not a chapter
    base_url = f"https://manga18.club/manhwa/{slug}"
    
    r = _get(base_url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Extract title - usually in h1
    title_elem = soup.select_one("h1")
    title = title_elem.get_text(strip=True) if title_elem else slug.replace("-", " ").title()
    
    # Extract metadata from info section
    author = None
    artist = None
    status = "ongoing"
    categories = []
    views = None
    
    # Look for info items - manga18.club uses various formats
    info_section = soup.select_one(".manga-info") or soup.select_one(".info") or soup.select_one("body")
    
    if info_section:
        # Try to find author
        author_match = re.search(r"Author[:\s]+([^<\n]+)", info_section.get_text())
        if author_match:
            author = author_match.group(1).strip()
        
        # Try to find artist
        artist_match = re.search(r"Artist[:\s]+([^<\n]+)", info_section.get_text())
        if artist_match:
            artist = artist_match.group(1).strip()
        
        # Try to find status
        status_match = re.search(r"Status[:\s]+(On Going|Completed|Ongoing|Complete)", info_section.get_text(), re.IGNORECASE)
        if status_match:
            status = status_match.group(1).lower()
            if status == "on going":
                status = "ongoing"
            elif status == "complete":
                status = "completed"
        
        # Try to find categories/genres
        category_links = info_section.select("a[href*='manga-list']")
        categories = [a.get_text(strip=True) for a in category_links]
        
        # Try to find views
        views_match = re.search(r"Views[:\s]+([\d,]+)", info_section.get_text())
        if views_match:
            views = views_match.group(1)
    
    # Extract description/summary
    description = ""
    summary_elem = soup.select_one(".summary") or soup.select_one(".description") or soup.select_one("p.summary")
    if summary_elem:
        description = summary_elem.get_text(strip=True)
    else:
        # Try finding by text content
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) > 50 and not any(skip in text.lower() for skip in ["copyright", "contact", "disclaimer"]):
                description = text
                break
    
    # Extract cover image
    cover_url = None
    # Look for og:image first
    og_image = soup.select_one("meta[property='og:image']")
    if og_image:
        cover_url = og_image.get("content")
    else:
        # Try finding main cover image
        cover_elem = soup.select_one(".manga-cover img") or soup.select_one(".cover img") or soup.select_one(".info img")
        if cover_elem:
            cover_url = cover_elem.get("src") or cover_elem.get("data-src")
    
    _log(f"✅ Found: {title} by {author or 'Unknown'}")
    
    return {
        "manga_id": slug,
        "title": title,
        "author": author,
        "artist": artist or author,
        "status": status,
        "language": "en",
        "genre": ", ".join(categories) if categories else None,
        "description": description,
        "tags": categories,
        "source_url": base_url,
        "cover_image": cover_url,
        "views": views,
        "source": "manga18",
    }


def _get_chapter_list(source_url: str, limit: Optional[int] = None) -> List[Dict]:
    """
    Get list of chapters from manga18.club.
    
    Args:
        source_url: Manga page URL
        limit: Max number of chapters to fetch (from the beginning)
    
    Returns:
        List of chapter dictionaries sorted by chapter number (ascending)
    """
    _log(f"📚 Fetching chapter list...")
    
    slug = extract_slug_from_url(source_url)
    if not slug:
        raise RuntimeError("Invalid manga18.club URL")
    
    base_url = f"https://manga18.club/manhwa/{slug}"
    r = _get(base_url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    
    chapters = []
    
    # Find chapter links - manga18.club typically lists chapters in a table or list
    # Pattern: /manhwa/{slug}/chap-{num}
    chapter_links = soup.select("a[href*='/chap-']")
    
    seen_chapters = set()
    
    for link in chapter_links:
        href = link.get("href", "")
        if not href or slug not in href:
            continue
        
        # Extract chapter number from URL
        ch_match = re.search(r"chap-(\d+)", href)
        if not ch_match:
            continue
        
        ch_num = ch_match.group(1)
        
        # Skip duplicates
        if ch_num in seen_chapters:
            continue
        seen_chapters.add(ch_num)
        
        # Make absolute URL
        if href.startswith("/"):
            href = f"https://manga18.club{href}"
        
        # Get chapter title from link text
        ch_title = link.get_text(strip=True) or f"Chapter {ch_num}"
        
        # Try to find date if available (parent element might have it)
        date = ""
        parent = link.find_parent("tr") or link.find_parent("li") or link.find_parent("div")
        if parent:
            date_elem = parent.select_one(".date") or parent.select_one("td:last-child") or parent.select_one("span")
            if date_elem and date_elem != link:
                potential_date = date_elem.get_text(strip=True)
                # Check if it looks like a date
                if re.search(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", potential_date):
                    date = potential_date
        
        chapters.append({
            "id": ch_num,
            "chapter": ch_num,
            "title": ch_title,
            "url": href,
            "date": date,
        })
    
    # Sort by chapter number (ascending) - chapter 1 first
    chapters.sort(key=lambda x: int(x.get("chapter", "0") or "0"))
    
    # Apply limit after sorting
    if limit and len(chapters) > limit:
        chapters = chapters[:limit]
        _log(f"✅ Found {len(seen_chapters)} total chapters, limited to first {limit}")
    else:
        _log(f"✅ Found {len(chapters)} chapters")
    
    return chapters


def _get_chapter_images(chapter_url: str, referer: str = None) -> List[str]:
    """
    Get image URLs for a specific chapter.
    
    manga18.club stores image URLs as base64-encoded strings in a JavaScript 
    variable called 'slides_p_path'. We need to extract and decode them.
    
    Args:
        chapter_url: Full URL to the chapter page
        referer: Referer URL for the request
    
    Returns:
        List of image URLs
    """
    r = _get(chapter_url, referer=referer or "https://manga18.club/")
    r.raise_for_status()
    html = r.text
    
    images = []
    
    # Method 1: Extract base64-encoded image URLs from slides_p_path variable
    # Format: var slides_p_path = ["base64url1","base64url2",...];
    slides_match = re.search(r'var\s+slides_p_path\s*=\s*\[(.*?)\];', html, re.DOTALL)
    if slides_match:
        urls_str = slides_match.group(1)
        # Extract base64 strings
        b64_urls = re.findall(r'"([A-Za-z0-9+/=]+)"', urls_str)
        
        for b64_url in b64_urls:
            try:
                decoded = base64.b64decode(b64_url).decode('utf-8')
                if decoded.startswith('http') and any(ext in decoded.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                    images.append(decoded)
            except Exception:
                # Not a valid base64 or not a valid URL
                continue
        
        if images:
            return images
    
    # Method 2: Fallback - try to find images in HTML directly
    soup = BeautifulSoup(html, "html.parser")
    img_elements = soup.select("img[src*='manga18.club']") or soup.select(".chapter-content img") or soup.select(".reading-content img")
    
    for img in img_elements:
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        
        # Filter out non-content images (ads, logos, etc.)
        if any(skip in src.lower() for skip in ["logo", "banner", "ajax-loader", "avatar", "icon", "fav.png", "1.jpg"]):
            continue
        
        images.append(src)
    
    return images


def get_manga_chapter_manifest(
    source_url: str,
    limit: Optional[int] = None,
    page_workers: int = 4,
    **kwargs
) -> Dict:
    """
    Get complete manga manifest with all chapters and page URLs.
    
    Args:
        source_url: Manga page URL
        limit: Maximum number of chapters to fetch
        page_workers: Number of parallel workers for fetching page URLs
    
    Returns:
        Dictionary with manga info and chapters with page URLs
    """
    _log(f"🚀 Getting chapter manifest from: {source_url}")
    
    # Get metadata
    manga_info = get_manga_metadata(source_url)
    
    # Get chapter list
    chapters = _get_chapter_list(source_url, limit=limit)
    
    if not chapters:
        _log("⚠️ No chapters found")
        return {
            "manga": manga_info,
            "chapters": [],
            "total_chapters": 0,
            "total_pages": 0,
        }
    
    _log(f"📖 Fetching page URLs for {len(chapters)} chapters (workers={page_workers})...")
    
    def fetch_chapter_pages(ch: Dict) -> Dict:
        """Fetch pages for a single chapter."""
        ch_url = ch["url"]
        ch_num = ch["chapter"]
        try:
            pages = _get_chapter_images(ch_url, referer=source_url)
            _log(f"   📄 Chapter {ch_num}: {len(pages)} pages")
            return {**ch, "pages": pages}
        except Exception as e:
            _log(f"   ⚠️ Chapter {ch_num} failed: {e}")
            return {**ch, "pages": []}
    
    # Fetch pages in parallel
    chapters_with_pages = []
    with ThreadPoolExecutor(max_workers=page_workers) as executor:
        futures = {executor.submit(fetch_chapter_pages, ch): ch for ch in chapters}
        for future in as_completed(futures):
            result = future.result()
            chapters_with_pages.append(result)
    
    # Sort by chapter number again (parallel execution may have shuffled them)
    chapters_with_pages.sort(key=lambda x: int(x.get("chapter", "0") or "0"))
    
    total_pages = sum(len(ch.get("pages", [])) for ch in chapters_with_pages)
    
    _log(f"✅ Manifest complete: {len(chapters_with_pages)} chapters, {total_pages} total pages")
    
    return {
        "manga": manga_info,
        "chapters": chapters_with_pages,
        "total_chapters": len(chapters_with_pages),
        "total_pages": total_pages,
    }
