from pathlib import Path
from typing import Optional

def _get_safe_path(base_dir: str, filename: str) -> Optional[Path]:
    """Resolve filename against base_dir and ensure it stays within base_dir."""
    try:
        base_path = Path(base_dir).resolve()
        target_path = (base_path / filename).resolve()
        # Verify that the resolved target path is under the base path
        target_path.relative_to(base_path)
        return target_path
    except (ValueError, RuntimeError):
        return None

def test_get_safe_path():
    import os
    import shutil
    # Setup
    base_dir = "test_books"
    os.makedirs(base_dir, exist_ok=True)

    # Create a dummy file inside base_dir
    safe_file = Path(base_dir) / "safe.epub"
    safe_file.touch()

    # Create a dummy file outside base_dir
    outside_file = Path("outside.txt")
    outside_file.touch()

    try:
        # Test valid path
        res = _get_safe_path(base_dir, "safe.epub")
        assert res is not None
        assert res.name == "safe.epub"

        # Test path traversal (absolute)
        assert _get_safe_path(base_dir, "/etc/passwd") is None

        # Test path traversal (relative)
        assert _get_safe_path(base_dir, "../outside.txt") is None
        assert _get_safe_path(base_dir, "../../etc/passwd") is None

        # Test non-existent but safe path
        assert _get_safe_path(base_dir, "non_existent.epub") is not None

        print("Security tests passed!")
    finally:
        # Cleanup
        shutil.rmtree(base_dir)
        outside_file.unlink()

if __name__ == "__main__":
    test_get_safe_path()
