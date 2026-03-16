from scripts import scraper
try:
    meta = scraper.get_chapter_metadata("https://freewebnovel.com/novel/martial-god-asura.html")
    print(meta)
    chap = scraper.get_chapters("https://freewebnovel.com/novel/martial-god-asura.html", start_chapter=500, chapter_limit=2)
    print("Found chapters:", len(chap.get("title", [])))
    print("First title:", chap.get("title", [])[0])
except Exception as e:
    print(e)
