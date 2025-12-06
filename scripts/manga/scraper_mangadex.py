import re
import requests
from typing import Dict, List, Optional

from scripts.proxy_manager import fetch_with_proxy_rotation


def _log(msg: str):
    """Log message to stdout for the log panel."""
    print(f"[manga] {msg}")


def _get(url: str, timeout: int = 25) -> requests.Response:
    try:
        return fetch_with_proxy_rotation(url, retries=4, timeout=timeout)
    except Exception:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        }
        return requests.get(url, timeout=timeout, headers=headers)


def extract_manga_id_from_url(url: str) -> Optional[str]:
    m = re.search(r"/title/([0-9a-f\-]{36})", url, re.IGNORECASE)
    return m.group(1) if m else None


def _choose_title(attrs: Dict) -> str:
    titles = attrs.get("title") or {}
    en = titles.get("en")
    if en:
        return en
    for v in titles.values():
        if v:
            return v
    alts = attrs.get("altTitles") or []
    if alts:
        alt = alts[0]
        if isinstance(alt, dict):
            for v in alt.values():
                if v:
                    return v
    return "Untitled"


def get_manga_metadata(source_url: str) -> Dict:
    _log(f"📖 Fetching manga metadata from: {source_url}")
    manga_id = extract_manga_id_from_url(source_url) or ""
    if not manga_id:
        _log("❌ Invalid MangaDex URL - could not extract manga ID")
        raise RuntimeError("Invalid MangaDex URL")
    _log(f"🔍 Manga ID: {manga_id}")
    meta_url = f"https://api.mangadex.org/manga/{manga_id}?includes[]=cover_art&includes[]=author&includes[]=artist&includes[]=tag"
    r = _get(meta_url)
    r.raise_for_status()
    data = r.json()
    d = data.get("data") or {}
    attrs = d.get("attributes") or {}
    title = _choose_title(attrs)
    status = (attrs.get("status") or "").lower()
    lang = attrs.get("originalLanguage") or ""
    tags = []
    author = None
    artist = None
    cover_file = None
    for rel in d.get("relationships", []) or []:
        t = rel.get("type")
        if t == "author":
            a = rel.get("attributes") or {}
            n = a.get("name")
            if n:
                author = n
        elif t == "artist":
            a = rel.get("attributes") or {}
            n = a.get("name")
            if n:
                artist = n
        elif t == "cover_art":
            a = rel.get("attributes") or {}
            f = a.get("fileName")
            if f:
                cover_file = f
        elif t == "tag":
            a = rel.get("attributes") or {}
            n = a.get("name") or {}
            v = n.get("en") or next(iter(n.values()), None)
            if v:
                tags.append(v)
    cover_url = None
    if cover_file:
        cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{cover_file}"
    _log(f"✅ Metadata fetched: {title} by {author or 'Unknown'}")
    _log(f"   Status: {status}, Language: {lang}, Tags: {len(tags)}")
    return {
        "manga_id": manga_id,
        "title": title,
        "author": author,
        "artist": artist,
        "status": status,
        "language": lang,
        "tags": tags,
        "source_url": source_url,
        "cover_image": cover_url,
    }


def _chapter_pages(ch_id: str, ch_num: str = "", use_data_saver: bool = True) -> List[str]:
    at_home = _get(f"https://api.mangadex.org/at-home/server/{ch_id}")
    at_home.raise_for_status()
    data = at_home.json()
    base = data.get("baseUrl")
    chapter_data = data.get("chapter") or {}
    h = chapter_data.get("hash") or ""
    files = chapter_data.get("dataSaver" if use_data_saver else "data") or []
    prefix = "data-saver" if use_data_saver else "data"
    out = []
    for f in files:
        out.append(f"{base}/{prefix}/{h}/{f}")
    return out


def get_manga_chapter_manifest(source_url: str, translated_language: Optional[str] = None, use_data_saver: bool = True, limit: Optional[int] = None, page_workers: int = 4) -> Dict:
    manga_id = extract_manga_id_from_url(source_url) or ""
    if not manga_id:
        raise RuntimeError("Invalid MangaDex URL")
    
    _log(f"📚 Fetching chapter list for manga {manga_id}")
    if translated_language:
        _log(f"   Language filter: {translated_language}")
    if limit:
        _log(f"   Chapter limit: {limit}")
    
    offset = 0
    per = 100
    chapters: List[Dict] = []
    total_fetched = 0
    
    while True:
        url = f"https://api.mangadex.org/chapter?manga={manga_id}&limit={per}&order[chapter]=asc&includes[]=scanlation_group&includes[]=user"
        if translated_language:
            url += f"&translatedLanguage[]={translated_language}"
        url += f"&offset={offset}"
        
        _log(f"📥 Fetching chapters batch (offset: {offset})...")
        r = _get(url)
        r.raise_for_status()
        payload = r.json()
        arr = payload.get("data") or []
        total_available = payload.get("total", 0)
        
        if offset == 0:
            _log(f"   Total chapters available: {total_available}")
        
        batch: List[Dict] = []
        for item in arr:
            attrs = item.get("attributes") or {}
            batch.append({
                "id": item.get("id"),
                "chapter": attrs.get("chapter") or "",
                "title": attrs.get("title") or "",
                "translatedLanguage": attrs.get("translatedLanguage") or "",
                "volume": attrs.get("volume") or "",
                "publishAt": attrs.get("publishAt") or attrs.get("createdAt") or "",
            })
        
        # Fetch page lists concurrently
        if batch:
            _log(f"🖼️ Fetching page URLs for {len(batch)} chapters (workers: {page_workers})...")
            from concurrent.futures import ThreadPoolExecutor, as_completed
            workers = max(1, page_workers or 1)
            completed = 0
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_chapter_pages, b["id"], b.get("chapter", ""), use_data_saver): b for b in batch}
                for fut in as_completed(futs):
                    b = futs[fut]
                    try:
                        pgs = fut.result()
                    except Exception as e:
                        _log(f"⚠️ Failed to get pages for chapter {b.get('chapter', '?')}: {e}")
                        pgs = []
                    rec = dict(b)
                    rec["pages"] = pgs
                    chapters.append(rec)
                    completed += 1
                    total_fetched += 1
                    
                    # Progress logging every 5 chapters or at the end
                    if completed % 5 == 0 or completed == len(batch):
                        ch_num = b.get("chapter", "?")
                        _log(f"   ✅ Chapter {ch_num}: {len(pgs)} pages ({completed}/{len(batch)} in batch)")
                    
                    if limit and len(chapters) >= limit:
                        break
        
        if limit and len(chapters) >= limit:
            _log(f"📊 Reached chapter limit ({limit})")
            break
        if len(arr) < per:
            break
        offset += per
    
    _log(f"✅ Manga scraping complete!")
    _log(f"   Total chapters: {len(chapters)}")
    total_pages = sum(len(ch.get("pages") or []) for ch in chapters)
    _log(f"   Total pages: {total_pages}")
    
    return {"chapters": chapters}
