"""
Run the Scripts Main file here
"""

from scripts.scraper import get_chapter_metadata, get_chapters
from scripts.convert_to_epub import to_epub
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
import argparse
import os
import sys


def create_ebook(url: str, chapters_per_book: int = 500, chapter_workers: int = 0, chapter_limit: int | None = None) -> str:
    """Process a single novel URL end-to-end and return the output filename prefix.

    Returns the base title or raises an exception for the caller to log.
    """
    metadata = get_chapter_metadata(url)
    chapters = get_chapters(url if chapter_workers > 0 else metadata["starting_url"],
                            chapter_workers=chapter_workers,
                            chapter_limit=chapter_limit)
    # Debug: print chapter titles and text lengths
    titles = chapters.get('title', [])
    texts = chapters.get('text', [])
    print(f"[DEBUG] Chapters fetched: {len(titles)}")
    for i, (t, x) in enumerate(zip(titles, texts)):
        print(f"[DEBUG] Chapter {i+1}: '{t}' - length: {len(x.strip()) if x else 0}")
    valid_chapters = [(t, x) for t, x in zip(titles, texts) if x and x.strip()]
    if not valid_chapters:
        print("[ERROR] No valid chapters found. Chapter data:")
        print(chapters)
        raise RuntimeError("No valid chapter content collected (all chapters empty or failed parsing).")
    to_epub(metadata, chapters, chapters_per_book=chapters_per_book)
    return metadata['title']


def process_job(u: str, chapters_per_book: int, chapter_workers: int, chapter_limit: int | None):
    try:
        title = create_ebook(u, chapters_per_book, chapter_workers, chapter_limit)
        return (True, u, title, None)
    except Exception as e:
        return (False, u, None, str(e))


def read_urls(path: str) -> list[str]:
    with open(path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]




def main(url: str | list | None = None):
    parser = argparse.ArgumentParser(description="Web Novel to EPUB Converter")
    parser.add_argument('-u', '--url', action='append', help='Single URL to process (can be used multiple times)')
    parser.add_argument('-f', '--file', default='urls.txt', help='Path to URLs list file (default: urls.txt)')
    parser.add_argument('-w', '--workers', type=int, default=os.cpu_count() or 2, help='Number of parallel processes')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of URLs to process (0 = all)')
    parser.add_argument('--chapters-per-book', type=int, default=500, help='Max chapters per EPUB volume')
    parser.add_argument('--chapter-workers', type=int, default=0, help='Parallel chapter fetchers (0 = sequential via next links)')
    parser.add_argument('--chapter-limit', type=int, default=0, help='Limit number of chapters to fetch (0 = all discovered)')
    args = parser.parse_args()
    
    if url or args.url:
        urls = [url] if isinstance(url, str) else list(url)
    else:
        urls = read_urls(args.file)
    
    if args.limit and args.limit > 0:
        urls = urls[:args.limit]
    if not urls:
        print("No URLs to process.")
        return 0

    print(f"Processing {len(urls)} novel(s) with {args.workers} worker(s)...")

    # Use separate processes to avoid GIL and isolate memory
    successes, failures = 0, 0
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_job, url, args.chapters_per_book, args.chapter_workers, (args.chapter_limit or None)): url for url in urls}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                ok, u, title, err = fut.result()
                if ok:
                    print(f"✅ Done: {title}")
                    successes += 1
                else:
                    print(f"❌ Failed: {u}\n   {err}")
                    failures += 1
            except Exception as e:
                print(f"❌ Failed: {url}\n   {e}")
                failures += 1

    print(f"All done. Success: {successes}, Failed: {failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
    