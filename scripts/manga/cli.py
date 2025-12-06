"""
Terminal CLI for Manga Scraper
Supports: MangaDex, Webtoons

Usage: python -m scripts.manga.cli <url> [--chapters N]
"""

import argparse
import sys
import json

from scripts.manga.scraper import get_manga_metadata, get_manga_manifest, get_supported_sources


def scrape_manga(url: str, num_chapters: int = 10, language: str = None, data_saver: bool = True):
    """Scrape manga from given URL."""
    print(f"\n{'='*60}")
    print(f"Manga Scraper CLI")
    print(f"{'='*60}")
    print(f"URL: {url}")
    print(f"Chapters to fetch: {num_chapters}")
    print(f"Language: {language or 'any'}")
    print(f"Data Saver: {data_saver}")
    print(f"{'='*60}\n")
    
    try:
        # Get manga metadata
        print("[1/2] Fetching manga metadata...")
        metadata = get_manga_metadata(url)
        
        print(f"  Source: {metadata.get('source_name', 'Unknown')}")
        print(f"  Title: {metadata.get('title', 'Unknown')}")
        print(f"  Author: {metadata.get('author', 'Unknown')}")
        print(f"  Artist: {metadata.get('artist', 'Unknown')}")
        print(f"  Status: {metadata.get('status', 'Unknown')}")
        print(f"  Language: {metadata.get('language', 'Unknown')}")
        if metadata.get('genre'):
            print(f"  Genre: {metadata.get('genre')}")
        if metadata.get('tags'):
            print(f"  Tags: {', '.join(metadata.get('tags', [])[:5])}")
        if metadata.get('cover_image'):
            print(f"  Cover: {metadata.get('cover_image')[:60]}...")
        
        # Get chapters
        print(f"\n[2/2] Fetching chapters (limit: {num_chapters})...")
        manifest = get_manga_manifest(
            url, 
            translated_language=language,  # None = all languages
            use_data_saver=data_saver,
            limit=num_chapters,
            page_workers=4
        )
        
        chapters = manifest.get('chapters', [])
        
        if not chapters:
            print("  ERROR: No chapters found")
            return None
        
        # Sort chapters by chapter number
        def sort_key(ch):
            try:
                return float(ch.get('chapter', '0') or '0')
            except ValueError:
                return 0
        chapters.sort(key=sort_key)
        
        print(f"  Found {len(chapters)} chapters")
        
        # Display chapters
        print("\n" + "-" * 60)
        print("Chapter Details:")
        print("-" * 60)
        
        for i, chapter in enumerate(chapters, 1):
            ch_num = chapter.get('chapter', 'N/A') or 'N/A'
            ch_title = chapter.get('title', '') or f"Chapter {ch_num}"
            ch_id = chapter.get('id', 'N/A')
            pages = chapter.get('pages', [])
            lang = chapter.get('translatedLanguage', language)
            
            print(f"\n  {i:2}. Chapter {ch_num}: {ch_title}")
            print(f"      ID: {ch_id}")
            print(f"      Language: {lang}")
            print(f"      Pages: {len(pages)}")
            
            if pages:
                print(f"      First page: {pages[0][:70]}...")
        
        print(f"\n{'='*60}")
        print("Summary:")
        print(f"  Total chapters fetched: {len(chapters)}")
        total_pages = sum(len(ch.get('pages', [])) for ch in chapters)
        print(f"  Total pages: {total_pages}")
        print(f"{'='*60}")
        
        return {
            "metadata": metadata,
            "chapters": chapters
        }
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    # Get supported sources for help text
    sources = get_supported_sources()
    source_list = ", ".join(f"{s['name']} ({', '.join(s['domains'])})" for s in sources.values())
    
    parser = argparse.ArgumentParser(
        description="Scrape manga from various sites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Supported Sources:
  {source_list}

Examples:
  # MangaDex
  python -m scripts.manga.cli https://mangadex.org/title/d8a959f7-648e-4c8d-8f23-f1f3f8e129f3/one-punch-man --chapters 10
  
  # Webtoons
  python -m scripts.manga.cli https://www.webtoons.com/en/action/im-the-max-level-newbie/list?title_no=3915 -n 5
        """
    )
    parser.add_argument("url", help="Manga URL to scrape")
    parser.add_argument(
        "-n", "--chapters", 
        type=int, 
        default=10, 
        help="Number of chapters to fetch (default: 10)"
    )
    parser.add_argument(
        "-l", "--language",
        type=str,
        default=None,
        help="Language code (e.g., 'en', 'it', 'pt-br'). Default: any language"
    )
    parser.add_argument(
        "--full-quality",
        action="store_true",
        help="Use full quality images instead of data-saver"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output JSON file path (optional)"
    )
    
    args = parser.parse_args()
    
    # Run scraper
    result = scrape_manga(
        args.url, 
        args.chapters, 
        args.language,
        data_saver=not args.full_quality
    )
    
    if result and args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {args.output}")
    
    print(f"\n{'='*60}")
    print("Scraping complete!")
    print(f"{'='*60}")
    
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
