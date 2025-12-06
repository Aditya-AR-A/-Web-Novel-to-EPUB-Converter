"""
Multi-source Manga Scraper
Supports: MangaDex, Webtoons, Manga18, and more
"""

from urllib.parse import urlparse
from typing import Dict, Optional

from .scraper_mangadex import (
    get_manga_metadata as _md_meta, 
    get_manga_chapter_manifest as _md_manifest
)
from .scraper_webtoons import (
    get_manga_metadata as _wt_meta,
    get_manga_chapter_manifest as _wt_manifest
)
from .scraper_manga18 import (
    get_manga_metadata as _m18_meta,
    get_manga_chapter_manifest as _m18_manifest
)


# Supported sources and their domain patterns
SOURCES = {
    "mangadex": {
        "domains": ["mangadex.org"],
        "name": "MangaDex",
        "get_metadata": _md_meta,
        "get_manifest": _md_manifest,
    },
    "webtoons": {
        "domains": ["webtoons.com", "www.webtoons.com"],
        "name": "Webtoons",
        "get_metadata": _wt_meta,
        "get_manifest": _wt_manifest,
    },
    "manga18": {
        "domains": ["manga18.club", "manga18.us"],
        "name": "Manga18",
        "get_metadata": _m18_meta,
        "get_manifest": _m18_manifest,
    },
}


def _domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _identify_source(url: str) -> Optional[str]:
    """Identify which source a URL belongs to."""
    domain = _domain(url)
    for source_id, source_info in SOURCES.items():
        for pattern in source_info["domains"]:
            if pattern in domain:
                return source_id
    return None


def get_supported_sources() -> Dict:
    """Get list of supported manga sources."""
    return {
        source_id: {
            "name": info["name"],
            "domains": info["domains"],
        }
        for source_id, info in SOURCES.items()
    }


def get_manga_metadata(url: str) -> Dict:
    """
    Get manga metadata from any supported source.
    
    Args:
        url: Manga URL from any supported source
        
    Returns:
        Dictionary with manga metadata
        
    Raises:
        RuntimeError: If source is not supported
    """
    source_id = _identify_source(url)
    
    if not source_id:
        supported = ", ".join(SOURCES.keys())
        raise RuntimeError(f"Unsupported manga source. Supported: {supported}")
    
    source = SOURCES[source_id]
    print(f"[scraper] Using {source['name']} scraper for: {url}")
    
    metadata = source["get_metadata"](url)
    metadata["source"] = source_id
    metadata["source_name"] = source["name"]
    
    return metadata


def get_manga_manifest(
    url: str, 
    translated_language: Optional[str] = None, 
    use_data_saver: bool = True, 
    limit: Optional[int] = None, 
    page_workers: Optional[int] = None
) -> Dict:
    """
    Get manga chapter manifest from any supported source.
    
    Args:
        url: Manga URL from any supported source
        translated_language: Language filter (MangaDex only)
        use_data_saver: Use data saver images (MangaDex only)
        limit: Max number of chapters to fetch
        page_workers: Number of parallel workers
        
    Returns:
        Dictionary with chapters and page URLs
        
    Raises:
        RuntimeError: If source is not supported
    """
    source_id = _identify_source(url)
    
    if not source_id:
        supported = ", ".join(SOURCES.keys())
        raise RuntimeError(f"Unsupported manga source. Supported: {supported}")
    
    source = SOURCES[source_id]
    print(f"[scraper] Fetching manifest from {source['name']}...")
    
    return source["get_manifest"](
        url,
        translated_language=translated_language,
        use_data_saver=use_data_saver,
        limit=limit,
        page_workers=(page_workers or 4),
    )

