from __future__ import annotations

import json
from pathlib import Path

from scripts.db.manga_operations import save_manga_manifest


def main() -> int:
    base_meta = {
        "manga_id": "test-id",
        "title": "ワンパンマン",
        "author": "ONE",
        "artist": "村田 雄介",
        "status": "ongoing",
        "language": "ja",
        "tags": ["アクション", "コメディ"],
        "source_url": "https://example.test",
        "cover_image": "https://example.test/cover.jpg",
    }
    manifest = {
        "chapters": [
            {
                "id": "c1",
                "chapter": "1",
                "title": "最強",
                "translatedLanguage": "ja",
                "pages": ["https://example.test/1.jpg"],
                "volume": "1",
                "publishAt": "2020-01-01T00:00:00Z",
            }
        ]
    }
    saved = save_manga_manifest(base_meta, manifest)
    p = Path(saved["local_path"]).resolve()
    assert p.exists(), "manifest file missing"
    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["manga"]["title"] == "ワンパンマン"
    assert data["manga"]["artist"] == "村田 雄介"
    assert data["chapters"][0]["title"] == "最強"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

