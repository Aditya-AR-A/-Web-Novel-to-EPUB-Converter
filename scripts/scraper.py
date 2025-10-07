from bs4 import BeautifulSoup
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Dict
from urllib.parse import urljoin

from scripts.proxy_manager import fetch_with_proxy_rotation, sample_proxy_pool
from scripts.get_text_from_html import get_chapter_data

# Import cancellation support (gracefully handle if not available)
try:
    from scripts.cancellation import raise_if_cancelled, raise_if_stopped, is_stopped
except ImportError:
    def raise_if_cancelled():
        pass
    def raise_if_stopped():
        pass
    def is_stopped():
        return False


# send the link to first page

origin_url = "https://freewebnovel.com"


def get_chapter_metadata(url):

    # Support local file for temp.html or offline parsing
    if url.startswith('file://'):
        path = url[7:]
    else:
        path = url
    if os.path.exists(path):
        with open(path, 'rb') as f:
            content = f.read()
        soup = BeautifulSoup(content, "html.parser")
    else:
        # Use proxy-rotating fetch for metadata page
        html = fetch_with_proxy_rotation(url, retries=5, timeout=30)
        soup = BeautifulSoup(html.content, "html.parser")

    # Helpers
    def sel_text(selector):
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else None

    def meta_content(prop):
        tag = soup.select_one(f'meta[property="{prop}"]')
        return tag.get("content") if tag and tag.get("content") else None

    # Title (prefer visible, fallback to og meta)
    title = sel_text("h1.tit") or meta_content("og:novel:novel_name") or meta_content("og:title") or "Unknown Title"

    # Author
    author = sel_text(".glyphicon-user + .right a") or meta_content("og:novel:author") or "Unknown"

    # Genres
    genres = [a.text.strip() for a in soup.select(".glyphicon-th-list + .right a")]
    if not genres:
        og_genre = meta_content("og:novel:genre")
        if og_genre:
            genres = [g.strip() for g in og_genre.split(",") if g.strip()]

    # Language
    language = sel_text(".glyphicon-globe + .right a") or meta_content("og:novel:category") or "Unknown"

    # Status
    status = sel_text(".glyphicon-time + .right") or meta_content("og:novel:status") or ""

    # Image URL
    img_el = soup.select_one(".m-book1 img")
    img_path = img_el.get("src") if img_el else None
    image_url = meta_content("og:image") or (urljoin(origin_url, img_path) if img_path else None)

    # Synopsis / Summary
    synopsis = " ".join(p.text.strip() for p in soup.select(".m-desc .txt .inner p"))
    if not synopsis:
        synopsis = meta_content("og:description") or ""

    # Read First link – try robust strategies
    read_first_url = meta_content("og:novel:read_url")
    if not read_first_url:
        # Look for anchor with visible text like 'Read first'
        anchor = None
        for a in soup.find_all("a"):
            txt = a.get_text(strip=True).lower()
            if "read" in txt and "first" in txt:
                anchor = a
                break
        if not anchor:
            # Try by title attribute pattern (case-insensitive)
            pattern = re.compile(rf"^read\s+{re.escape(title)}\s+online\s+free", re.IGNORECASE)
            anchor = next((a for a in soup.find_all("a") if pattern.search(a.get("title", ""))), None)
        if anchor and anchor.get("href"):
            read_first_url = urljoin(origin_url, anchor.get("href"))
    if not read_first_url:
        raise RuntimeError("Failed to locate 'Read first' chapter URL.")

    # Prepare image path safely
    def sanitize_filename(name: str) -> str:
        return re.sub(r'[\\\\/:*?"<>|]+', '_', name).strip()

    os.makedirs("media", exist_ok=True)
    filename = os.path.join("media", f"image {sanitize_filename(title)}.jpeg")
    

    if image_url:
        try:
            response = fetch_with_proxy_rotation(image_url, retries=4, timeout=20)
            if response.status_code == 200:
                with open(filename, "wb") as f:
                    f.write(response.content)
            else:
                print(f"Failed to download image. Status code: {response.status_code}")
        except Exception as e:
            print(f"Failed to download image after retries: {e}")
            # leave image missing; EPUB generation can proceed without it
    else:
        print("No image URL found.")


    print(f"\n>>> Got the metadata for {title} by: {author}\n")
    # Final dictionary
    book_data = {
        "title": title,
        "author": author,
        "genres": genres,
        "language": language,
        "status": status,
        "image_url": image_url,
        "synopsis": synopsis,
        "starting_url": read_first_url,
        "image_path": filename
    }
    return book_data




def list_chapter_urls_from_index(index_url: str) -> List[Tuple[int, str]]:
    """Parse the novel's main page and extract absolute chapter URLs with indices.

    Returns a list of tuples: (chapter_number, absolute_url), sorted by chapter_number ascending.
    """
    # Support local file path
    if index_url.startswith('file://'):
        path = index_url[7:]
    else:
        path = index_url
    try:
        if os.path.exists(path):
            with open(path, 'rb') as f:
                content = f.read()
            s = BeautifulSoup(content, "html.parser")
        else:
            resp = fetch_with_proxy_rotation(index_url, retries=4, timeout=15)
            s = BeautifulSoup(resp.content, "html.parser")
    except Exception as e:
        print(f"❌ Failed to fetch index page for chapters: {index_url}\n{e}")
        return []

    # Common pattern: /novel/<slug>/chapter-123 or .../chapter_123, allow variations
    anchors = s.find_all('a', href=True)
    seen: Dict[str, int] = {}
    out: List[Tuple[int, str]] = []
    pat = re.compile(r"/novel/[^/]+/chapter[-_](\d+)", re.IGNORECASE)
    for a in anchors:
        href = a['href']
        m = pat.search(href)
        if not m:
            continue
        num = int(m.group(1))
        abs_url = urljoin(origin_url, href)
        # De-dupe by absolute URL keeping smallest chapter number if duplicates found
        if abs_url in seen:
            if num < seen[abs_url]:
                seen[abs_url] = num
        else:
            seen[abs_url] = num
    for u, n in seen.items():
        out.append((n, u))
    out.sort(key=lambda t: t[0])
    return out


def get_chapters_concurrent_from_index(
    index_url: str,
    *,
    max_workers: int = 5,
    limit: int | None = None,
    start: int = 1,
) -> Dict[str, List[str]]:
    """Fetch chapters concurrently using chapter links parsed from the index page.

    - Assign a sticky proxy per worker stream to reduce blocks and session churn.
    - Retry per request with rotation.
    - Preserve output order by chapter index.
    """
    raise_if_cancelled()
    indexed = list_chapter_urls_from_index(index_url)
    start = max(1, start)
    if start > 1:
        indexed = [pair for pair in indexed if pair[0] >= start]
    if not indexed:
        print("⚠️ No chapter links found on index; falling back to sequential next-links crawl.")
        # Fallback: Follow next links starting from chapter-1 URL
        return get_chapters_sequential(index_url, start_at=start, limit=limit)
    if limit and limit > 0:
        indexed = indexed[:limit]

    # Prepare sticky proxy pool for workers
    workers = max(1, max_workers)
    proxy_pool = sample_proxy_pool(workers)

    results: Dict[int, Tuple[str, str]] = {}
    failed_stack: List[Tuple[int, str]] = []

    def worker(idx_url_pair: Tuple[int, str], stream_id: int, proxy_override=None):
        raise_if_cancelled()
        idx, url = idx_url_pair
        preferred = proxy_override if proxy_override else (proxy_pool[stream_id % len(proxy_pool)] if proxy_pool else None)
        avoid = [p for j, p in enumerate(proxy_pool) if j != (stream_id % len(proxy_pool))]
        next_url, title, text = get_chapter_data(url, preferred_proxy=preferred, avoid_proxies=avoid)
        return idx, title, text

    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {}
        for i, pair in enumerate(indexed):
            future = ex.submit(worker, pair, i)
            future_map[future] = pair
        # Track which chapters failed
        for fut in as_completed(future_map):
            raise_if_cancelled()
            if is_stopped():
                break
            try:
                ch_idx, ch_title, ch_text = fut.result()
            except Exception as e:
                pair = future_map.get(fut)
                print(f"⚠️ Chapter fetch failed for {pair}: {e}")
                failed_stack.append(pair)
                continue
            if not ch_text or not ch_text.strip():
                print(f"⚠️ Skipping empty chapter at index {ch_idx}")
                failed_stack.append((ch_idx, future_map[fut][1]))
                continue
            results[ch_idx] = (ch_title or f"Chapter {ch_idx}", ch_text)
            # After each success, try to retry one from the failed stack
            if failed_stack:
                retry_idx, retry_url = failed_stack.pop(0)
                # Use a new proxy for retry
                retry_proxy = sample_proxy_pool(1)[0]
                try:
                    _, retry_title, retry_text = worker((retry_idx, retry_url), 0, proxy_override=retry_proxy)
                    if retry_text and retry_text.strip():
                        results[retry_idx] = (retry_title or f"Chapter {retry_idx}", retry_text)
                        print(f"✅ Retried and fetched chapter {retry_idx}")
                    else:
                        failed_stack.append((retry_idx, retry_url))
                except Exception as e:
                    print(f"⚠️ Retry failed for chapter {retry_idx}: {e}")
                    failed_stack.append((retry_idx, retry_url))

    # Final batch retry for any remaining failed chapters
    if failed_stack:
        print(f"🔁 Final retry for {len(failed_stack)} missed chapters (up to 10 attempts each)")
        for attempt in range(10):
            still_failed = []
            for ch_idx, ch_url in failed_stack:
                retry_proxy = sample_proxy_pool(1)[0]
                try:
                    _, retry_title, retry_text = worker((ch_idx, ch_url), 0, proxy_override=retry_proxy)
                    if retry_text and retry_text.strip():
                        results[ch_idx] = (retry_title or f"Chapter {ch_idx}", retry_text)
                        print(f"✅ Final retry succeeded for chapter {ch_idx}")
                    else:
                        still_failed.append((ch_idx, ch_url))
                except Exception as e:
                    print(f"⚠️ Final retry failed for chapter {ch_idx}: {e}")
                    still_failed.append((ch_idx, ch_url))
            if not still_failed:
                break
            failed_stack = still_failed
        if failed_stack:
            print(f"❌ Chapters still failed after all retries: {[idx for idx, _ in failed_stack]}")

    # Build ordered lists; if everything failed (no results), fallback sequentially
    if not results:
        print("⚠️ All concurrent chapter fetches failed; falling back to sequential crawl.")
        return get_chapters_sequential(index_url, start_at=start, limit=limit)
    ordered_indices = sorted(results.keys())
    titles = [results[i][0] for i in ordered_indices]
    texts = [results[i][1] for i in ordered_indices]
    return {"title": titles, "text": texts}


def get_chapters_sequential(
    read_first_url: str,
    *,
    start_at: int = 1,
    limit: int | None = None,
) -> Dict[str, List[str]]:
    chapter_title_list: List[str] = []
    chapter_text_list: List[str] = []
    next_url: str | None = read_first_url
    empty_streak = 0
    collected = 0
    start_at = max(1, start_at)
    valid_seen = 0
    while next_url:
        raise_if_cancelled()
        if is_stopped():
            break
        current_url = next_url
        next_url_short, chapter_title, chapter_data = get_chapter_data(current_url)
        if not chapter_data or not chapter_data.strip():
            print("⚠️ Empty chapter encountered in sequential crawl; skipping.")
            empty_streak += 1
            if empty_streak >= 3:
                print("⚠️ Too many consecutive empty chapters; stopping crawl.")
                break
        else:
            empty_streak = 0
            valid_seen += 1
            if valid_seen < start_at:
                next_url = urljoin(origin_url, next_url_short) if next_url_short else None
                continue
            chapter_title_list.append(chapter_title or f"Chapter {valid_seen}")
            chapter_text_list.append(chapter_data)
            collected += 1
            if limit and limit > 0 and collected >= limit:
                break
        next_url = urljoin(origin_url, next_url_short) if next_url_short else None
    return {"title": chapter_title_list, "text": chapter_text_list}


def get_chapters(
    read_first_url_or_index: str,
    *,
    chapter_workers: int = 0,
    chapter_limit: int | None = None,
    start_chapter: int = 1,
):
    """Top-level chapter fetcher.

    If chapter_workers > 0, treat the given URL as the novel index page and fetch
    chapter links concurrently; otherwise, follow next links sequentially from the
    provided chapter-1 URL.
    """
    limit = chapter_limit if chapter_limit and chapter_limit > 0 else None
    start = max(1, start_chapter or 1)
    if chapter_workers and chapter_workers > 0:
        return get_chapters_concurrent_from_index(
            read_first_url_or_index,
            max_workers=chapter_workers,
            limit=limit,
            start=start,
        )
    return get_chapters_sequential(
        read_first_url_or_index,
        start_at=start,
        limit=limit,
    )

    

def scrape_novel(
    url: str,
    tmpdir: str,
    *,
    chapter_workers: int | None = None,
    chapter_limit: int | None = None,
    start_chapter: int = 1,
):
    """Fetch novel metadata and chapters, mirroring the legacy API surface.

    The return signature matches the deprecated ``scraper.scrape_novel`` helper
    that the service layer still depends on. The cover image is copied into the
    provided temporary directory to ensure downstream EPUB builders can access
    it even if the original path is in a shared media folder.
    """

    metadata = get_chapter_metadata(url)

    workers = chapter_workers or 0
    entrypoint = metadata.get("starting_url") or url
    chapter_source = url if workers > 0 else entrypoint

    chapters = get_chapters(
        chapter_source,
        chapter_workers=workers,
        chapter_limit=chapter_limit,
        start_chapter=start_chapter,
    )

    image_path = metadata.get("image_path")
    if image_path and os.path.exists(image_path):
        try:
            copied_path = os.path.join(tmpdir, os.path.basename(image_path))
            shutil.copy(image_path, copied_path)
            metadata["image_path"] = copied_path
        except Exception:
            # If the copy fails the original path is still a valid fallback.
            pass

    return chapters, metadata


