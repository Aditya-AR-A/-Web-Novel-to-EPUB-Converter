from __future__ import annotations

from scripts.manga.scraper_mangadex import extract_manga_id_from_url, _choose_title


def main() -> int:
    url = "https://mangadex.org/title/d8a959f7-648e-4c8d-8f23-f1f3f8e129f3/one-punch-man"
    mid = extract_manga_id_from_url(url)
    assert mid == "d8a959f7-648e-4c8d-8f23-f1f3f8e129f3"

    attrs = {
        "title": {"en": "One Punch Man"},
        "altTitles": [{"ja": "ワンパンマン"}],
    }
    assert _choose_title(attrs) == "One Punch Man"

    attrs2 = {
        "title": {"ja": "ワンパンマン"},
        "altTitles": [{"en": "One Punch Man"}],
    }
    assert _choose_title(attrs2) == "ワンパンマン"

    attrs3 = {
        "title": {},
        "altTitles": [{"en": "OPM"}],
    }
    assert _choose_title(attrs3) == "OPM"

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

