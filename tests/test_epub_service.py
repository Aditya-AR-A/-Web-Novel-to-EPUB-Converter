import re
import uuid
import sys
from unittest.mock import MagicMock

# Mock dependencies of app.services.epub_service
sys.modules["fastapi"] = MagicMock()
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["app.db.models"] = MagicMock()
sys.modules["app.db.session"] = MagicMock()
sys.modules["app.storage"] = MagicMock()
sys.modules["scripts"] = MagicMock()
sys.modules["scripts.convert_to_epub"] = MagicMock()
sys.modules["scripts.scraper"] = MagicMock()

from app.services.epub_service import _slugify

def test_slugify_normal_string():
    assert _slugify("Hello World") == "hello-world"

def test_slugify_special_characters():
    assert _slugify("Hello @ World!") == "hello-world"

def test_slugify_multiple_hyphens_and_spaces():
    assert _slugify("Hello---World   Test") == "hello-world-test"

def test_slugify_numbers():
    assert _slugify("Chapter 123") == "chapter-123"

def test_slugify_mixed_case():
    assert _slugify("MyTitle") == "mytitle"

def test_slugify_empty_string():
    result = _slugify("")
    # Should return a UUID string
    assert len(result) == 36
    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", result)

def test_slugify_only_special_characters():
    result = _slugify("!!!")
    # Should return a UUID string
    assert len(result) == 36
    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", result)

def test_slugify_strips_leading_trailing_hyphens():
    assert _slugify("--Hello World--") == "hello-world"

if __name__ == "__main__":
    try:
        test_slugify_normal_string()
        test_slugify_special_characters()
        test_slugify_multiple_hyphens_and_spaces()
        test_slugify_numbers()
        test_slugify_mixed_case()
        test_slugify_empty_string()
        test_slugify_only_special_characters()
        test_slugify_strips_leading_trailing_hyphens()
        print("All tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        sys.exit(1)
