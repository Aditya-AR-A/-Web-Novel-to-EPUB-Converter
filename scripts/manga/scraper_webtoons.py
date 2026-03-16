"""
Webtoons Scraper - Scrapes manga/manhwa from webtoons.com
"""

import re
import requests
import contextvars
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from scripts.proxy_manager import fetch_with_proxy_rotation


def _log(msg: str):
    """Log message to stdout."""
    print(f"[webtoons] {msg}")


def _get(url: str, timeout: int = 25, referer: str = None) -> requests.Response:
    """Make a GET request with proper headers for Webtoons."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if referer:
        headers["Referer"] = referer
    
    try:
        return fetch_with_proxy_rotation(url, retries=3, timeout=timeout, headers=headers)
    except Exception:
        return requests.get(url, timeout=timeout, headers=headers)


def extract_title_id_from_url(url: str) -> Optional[str]:
    """Extract title_no from Webtoons URL."""
    m = re.search(r"title_no=(\d+)", url)
    return m.group(1) if m else None


def extract_episode_no_from_url(url: str) -> Optional[str]:
    """Extract episode_no from Webtoons URL."""
    m = re.search(r"episode_no=(\d+)", url)
    return m.group(1) if m else None


def get_manga_metadata(source_url: str) -> Dict:
    """
    Get manga metadata from Webtoons.
    
    Args:
        source_url: Webtoons list URL (e.g., https://www.webtoons.com/en/action/title-slug/list?title_no=1234)
    
    Returns:
        Dictionary with manga metadata
    """
    _log(f"📖 Fetching metadata from: {source_url}")
    
    title_id = extract_title_id_from_url(source_url)
    if not title_id:
        raise RuntimeError("Invalid Webtoons URL - missing title_no")
    
    r = _get(source_url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Extract title
    title_elem = soup.select_one("h1.subj") or soup.select_one(".info h1") or soup.select_one("h1")
    title = title_elem.get_text(strip=True) if title_elem else "Unknown"
    
    # Extract author/creator
    author_elem = soup.select_one(".author_area") or soup.select_one(".info .author") or soup.select_one("a.author")
    author = None
    if author_elem:
        # Clean up author text - remove extra whitespace and "...author info"
        raw_author = author_elem.get_text(strip=True)
        # Clean up multiple spaces and newlines
        author = " ".join(raw_author.split())
        # Remove common suffixes
        author = re.sub(r'\s*\.{3}author\s*info.*$', '', author, flags=re.IGNORECASE)
        author = re.sub(r'\s*,\s*,\s*', ', ', author)  # Clean up multiple commas
        author = author.strip(' ,')
        if not author:
            author = None
    
    # Extract genre from breadcrumb or URL
    genre = None
    genre_elem = soup.select_one(".genre") or soup.select_one("h2.genre")
    if genre_elem:
        genre = genre_elem.get_text(strip=True)
    else:
        # Extract from URL path
        m = re.search(r"webtoons\.com/\w+/(\w+)/", source_url)
        if m:
            genre = m.group(1).replace("-", " ").title()
    
    # Extract description
    desc_elem = soup.select_one(".summary") or soup.select_one("p.summary") or soup.select_one(".info .summary")
    description = desc_elem.get_text(strip=True) if desc_elem else ""
    
    # Extract cover image
    cover_url = None
    cover_elem = soup.select_one("meta[property='og:image']")
    if cover_elem:
        cover_url = cover_elem.get("content")
    else:
        cover_elem = soup.select_one(".detail_body .thmb img") or soup.select_one(".info img")
        if cover_elem:
            cover_url = cover_elem.get("src")
    
    # Extract view count and subscriber count
    views = None
    subscribers = None
    
    view_elem = soup.select_one(".grade_area .grade_num")
    if view_elem:
        views = view_elem.get_text(strip=True)
    
    sub_elem = soup.select_one(".grade_area em")
    if sub_elem:
        subscribers = sub_elem.get_text(strip=True)
    
    # Check status (ongoing/completed)
    status = "ongoing"
    if soup.select_one(".ico_completed") or "completed" in r.text.lower():
        status = "completed"
    
    _log(f"✅ Found: {title} by {author}")
    
    return {
        "manga_id": title_id,
        "title": title,
        "author": author,
        "artist": author,  # Webtoons usually same author/artist
        "status": status,
        "language": "en",
        "genre": genre,
        "description": description,
        "tags": [genre] if genre else [],
        "source_url": source_url,
        "cover_image": cover_url,
        "views": views,
        "subscribers": subscribers,
        "source": "webtoons",
    }


def _get_chapter_list(source_url: str, limit: Optional[int] = None) -> List[Dict]:
    """
    Get list of chapters from Webtoons, starting from chapter 1.
    
    Args:
        source_url: Webtoons list URL
        limit: Max number of chapters to fetch (from the beginning)
    
    Returns:
        List of chapter dictionaries sorted by chapter number (ascending)
    """
    _log(f"📚 Fetching chapter list...")
    
    title_id = extract_title_id_from_url(source_url)
    if not title_id:
        raise RuntimeError("Invalid Webtoons URL")
    
    seen_episode_ids = set()  # Track seen episode IDs to avoid duplicates
    all_chapters = []
    page = 1
    consecutive_empty_pages = 0
    
    # Iterate through ALL pages sequentially (1, 2, 3, ...)
    # Webtoons pagination is tricky - pg_next jumps by 10 pages, so we can't rely on it
    while True:
        # Webtoons uses pagination, showing newest first on page 1
        page_url = f"{source_url}&page={page}"
        r = _get(page_url, referer=source_url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Find episode list - try multiple selectors
        episode_items = soup.select("#_listUl li") or soup.select("ul#_listUl li") or soup.select(".episode_lst li")
        
        if not episode_items:
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= 3:
                # No more episodes after 3 consecutive empty pages
                _log(f"   No more episodes found after page {page - 2}")
                break
            page += 1
            continue
        
        consecutive_empty_pages = 0  # Reset counter on finding episodes
        new_episodes_on_page = 0
        
        for item in episode_items:
            # Get episode link
            link = item.select_one("a")
            if not link:
                continue
            
            href = link.get("href", "")
            if not href or "viewer" not in href:
                continue
            
            # Make absolute URL
            if href.startswith("/"):
                href = f"https://www.webtoons.com{href}"
            
            episode_no = extract_episode_no_from_url(href)
            
            # Skip duplicates (same episode can appear on multiple pages due to pagination)
            if episode_no in seen_episode_ids:
                continue
            seen_episode_ids.add(episode_no)
            new_episodes_on_page += 1
            
            # Get episode title
            title_elem = item.select_one(".subj span") or item.select_one(".sub_title") or item.select_one(".title")
            ep_title = title_elem.get_text(strip=True) if title_elem else f"Episode {episode_no}"
            
            # Get episode number from title or URL
            chapter_num = episode_no or str(len(all_chapters) + 1)
            
            # Get date
            date_elem = item.select_one(".date") or item.select_one(".update")
            date = date_elem.get_text(strip=True) if date_elem else ""
            
            # Get thumbnail
            thumb = None
            thumb_elem = item.select_one("img")
            if thumb_elem:
                thumb = thumb_elem.get("src") or thumb_elem.get("data-src")
            
            all_chapters.append({
                "id": episode_no,
                "chapter": chapter_num,
                "title": ep_title,
                "url": href,
                "date": date,
                "thumbnail": thumb,
            })
        
        # If no new episodes found on this page, we've likely reached the end
        if new_episodes_on_page == 0:
            _log(f"   No new episodes on page {page}, stopping")
            break
        
        page += 1
        if page > 200:  # Safety limit for very long series (2000 chapters max)
            _log(f"   Reached page limit (200)")
            break
    
    # Sort by chapter number (ascending) - chapter 1 first
    all_chapters.sort(key=lambda x: int(x.get("chapter", "0") or "0"))
    
    # Now apply the limit AFTER sorting (so we get chapters 1, 2, 3, ... not the latest ones)
    if limit and len(all_chapters) > limit:
        chapters = all_chapters[:limit]
        _log(f"✅ Found {len(all_chapters)} total chapters, limited to first {limit}")
    else:
        chapters = all_chapters
        _log(f"✅ Found {len(chapters)} chapters")
    
    return chapters


def _get_chapter_images(chapter_url: str, referer: str = None) -> List[str]:
    """
    Get image URLs for a specific chapter.
    
    Args:
        chapter_url: Webtoons viewer URL
        referer: Referer URL
    
    Returns:
        List of image URLs
    """
    r = _get(chapter_url, referer=referer)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    
    images = []
    
    # Primary selector for Webtoons images
    img_container = soup.select_one("#_imageList") or soup.select_one(".viewer_img")
    
    if img_container:
        for img in img_container.select("img"):
            src = img.get("data-url") or img.get("src") or img.get("data-src")
            if src and "webtoon" in src and "bg_transparency" not in src:
                # Clean up URL
                if not src.startswith("http"):
                    src = f"https:{src}" if src.startswith("//") else src
                images.append(src)
    
    # Fallback: look for all webtoon images
    if not images:
        for img in soup.select("img"):
            src = img.get("data-url") or img.get("src")
            if src and "webtoon-phinf" in src and "bg_transparency" not in src:
                if not src.startswith("http"):
                    src = f"https:{src}" if src.startswith("//") else src
                images.append(src)
    
    return images


def get_manga_chapter_manifest(
    source_url: str,
    translated_language: Optional[str] = None,  # Not used for Webtoons
    use_data_saver: bool = True,  # Not used for Webtoons
    limit: Optional[int] = None,
    page_workers: int = 4
) -> Dict:
    """
    Get full chapter manifest with page URLs.
    
    Args:
        source_url: Webtoons list URL
        translated_language: Not used for Webtoons
        use_data_saver: Not used for Webtoons  
        limit: Max number of chapters
        page_workers: Number of parallel workers
    
    Returns:
        Dictionary with chapters and pages
    """
    _log(f"🚀 Getting chapter manifest from: {source_url}")
    
    # Get chapter list
    chapter_list = _get_chapter_list(source_url, limit=limit)
    
    if not chapter_list:
        return {"chapters": []}
    
    _log(f"📖 Fetching page URLs for {len(chapter_list)} chapters (workers={page_workers})...")
    
    chapters_with_pages = []
    
    # Fetch page URLs concurrently
    ctx = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=page_workers) as executor:
        futures = {
            executor.submit(ctx.run, _get_chapter_images, ch["url"], source_url): ch 
            for ch in chapter_list
        }
        
        for future in as_completed(futures):
            ch = futures[future]
            try:
                pages = future.result()
                _log(f"   📄 Chapter {ch['chapter']}: {len(pages)} pages")
                
                chapters_with_pages.append({
                    **ch,
                    "pages": pages,
                })
            except Exception as e:
                _log(f"   ⚠️ Failed to get pages for chapter {ch['chapter']}: {e}")
                chapters_with_pages.append({
                    **ch,
                    "pages": [],
                })
    
    # Sort chapters by number
    chapters_with_pages.sort(key=lambda x: int(x.get("chapter", "0") or "0"))
    
    total_pages = sum(len(ch.get("pages", [])) for ch in chapters_with_pages)
    _log(f"✅ Manifest complete: {len(chapters_with_pages)} chapters, {total_pages} total pages")
    
    return {"chapters": chapters_with_pages}


# For testing
if __name__ == "__main__":
    url = "https://www.webtoons.com/en/action/im-the-max-level-newbie/list?title_no=3915"
    
    print("Testing Webtoons scraper...")
    meta = get_manga_metadata(url)
    print(f"Metadata: {meta}")
    
    manifest = get_manga_chapter_manifest(url, limit=2, page_workers=2)
    print(f"Manifest: {len(manifest.get('chapters', []))} chapters")
    for ch in manifest.get("chapters", []):
        print(f"  Chapter {ch['chapter']}: {len(ch.get('pages', []))} pages")
