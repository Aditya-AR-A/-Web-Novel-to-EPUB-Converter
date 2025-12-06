from __future__ import annotations

import threading
from pathlib import Path
from time import sleep

from scripts.db.manga_operations import save_manga_manifest


def _job(title: str, out: list):
    meta = {
        "manga_id": f"{title}-id",
        "title": title,
        "author": "Author",
        "artist": "Artist",
        "status": "ongoing",
        "language": "en",
        "tags": ["Action"],
        "source_url": "https://example",
        "cover_image": None,
    }
    manifest = {"chapters": [{"id": "c", "chapter": "1", "title": "t", "translatedLanguage": "en", "pages": ["u"], "volume": "1", "publishAt": "2020-01-01T00:00:00Z"}]}
    out.append(save_manga_manifest(meta, manifest))


def main() -> int:
    titles = [f"Series_{i}" for i in range(5)]
    results: list = []
    threads = [threading.Thread(target=_job, args=(t, results)) for t in titles]
    for th in threads: th.start()
    for th in threads: th.join()
    assert len(results) == len(titles)
    for r in results:
        p = Path(r["local_path"]).resolve()
        assert p.exists()
    sleep(0.05)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

