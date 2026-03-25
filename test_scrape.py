from scripts import scraper
novel_link = "https://freewebnovel.com/novel/extras-path-the-eternal-frost-monarch"
try:
    meta = scraper.get_chapter_metadata(novel_link)
    print(meta)
    chap = scraper.get_chapters(
        novel_link,
        meta.get("starting_url", novel_link),
        start_chapter=1,
        chapter_limit=2,
    )
    titles = chap.get("title", [])
    print("Found chapters:", len(titles))
    if titles:
        print("First title:", titles[0])
    else:
        print("No chapter titles returned.")
except Exception as e:
    print(e)
