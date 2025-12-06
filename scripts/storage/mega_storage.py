"""
MEGA Cloud Storage Integration for Manga Images

Uploads manga images to MEGA cloud storage and provides public download URLs.
Images are organized as: /manga/{manga_key}/chapters/{chapter_num}/{page_num}.{ext}

Environment variables required:
- MEGA_EMAIL: Your MEGA account email
- MEGA_PASSWORD: Your MEGA account password
"""

import os
import io
import hashlib
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import cloudscraper

try:
    from mega import Mega
except ImportError:
    Mega = None


def _log(msg: str):
    print(f"[mega] {msg}")


class MegaStorage:
    """MEGA cloud storage handler for manga images."""
    
    def __init__(self, email: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize MEGA storage.
        
        Args:
            email: MEGA account email (or use MEGA_EMAIL env var)
            password: MEGA account password (or use MEGA_PASSWORD env var)
        """
        if Mega is None:
            raise ImportError("mega.py library not installed. Run: pip install mega.py")
        
        self.email = email or os.getenv("MEGA_EMAIL")
        self.password = password or os.getenv("MEGA_PASSWORD")
        
        if not self.email or not self.password:
            raise ValueError("MEGA credentials required. Set MEGA_EMAIL and MEGA_PASSWORD environment variables.")
        
        self._mega = Mega()
        self._m = None
        self._folder_cache: Dict[str, str] = {}  # path -> folder handle
        
        # Create scraper for downloading images
        self._scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
    
    def login(self) -> bool:
        """Login to MEGA account."""
        try:
            _log(f"Logging in as {self.email}...")
            self._m = self._mega.login(self.email, self.password)
            _log("✅ Login successful")
            return True
        except Exception as e:
            _log(f"❌ Login failed: {e}")
            return False
    
    def ensure_logged_in(self):
        """Ensure we're logged in."""
        if self._m is None:
            if not self.login():
                raise RuntimeError("Failed to login to MEGA")
    
    def get_or_create_folder(self, path: str) -> str:
        """
        Get or create a folder at the given path.
        
        Args:
            path: Folder path like "manga/one_punch-man/chapters/1"
            
        Returns:
            Folder handle/ID
        """
        self.ensure_logged_in()
        
        # Check cache first
        if path in self._folder_cache:
            return self._folder_cache[path]
        
        import threading
        
        # Use a lock to prevent race conditions when multiple threads create folders
        if not hasattr(self, '_folder_lock'):
            self._folder_lock = threading.Lock()
        
        with self._folder_lock:
            # Check cache again inside lock
            if path in self._folder_cache:
                return self._folder_cache[path]
            
            parts = path.strip("/").split("/")
            
            # Refresh files list once
            files = self._m.get_files()
            parent_id = None
            
            # Find root folder
            for file_id, file_info in files.items():
                if file_info.get('t') == 2:  # Root folder (Cloud Drive)
                    parent_id = file_id
                    break
            
            # Build folder path incrementally
            current_path = ""
            for part in parts:
                current_path = f"{current_path}/{part}" if current_path else part
                
                # Check if already cached
                if current_path in self._folder_cache:
                    parent_id = self._folder_cache[current_path]
                    continue
                
                # Look for existing folder in current files
                found_id = None
                for file_id, file_info in files.items():
                    if (file_info.get('t') == 1 and  # Folder type
                        file_info.get('a', {}).get('n') == part and
                        file_info.get('p') == parent_id):
                        found_id = file_id
                        break
                
                if found_id:
                    parent_id = found_id
                else:
                    # Create folder
                    import time
                    for attempt in range(3):
                        try:
                            folder = self._m.create_folder(part, parent_id)
                            parent_id = folder[part]
                            # Refresh files list after creation
                            files = self._m.get_files()
                            break
                        except Exception as e:
                            err_str = str(e)
                            # Error -12 means folder already exists (race condition)
                            if "-12" in err_str or "EEXIST" in err_str:
                                # Refresh and find it
                                time.sleep(0.5)
                                files = self._m.get_files()
                                for file_id, file_info in files.items():
                                    if (file_info.get('t') == 1 and
                                        file_info.get('a', {}).get('n') == part and
                                        file_info.get('p') == parent_id):
                                        parent_id = file_id
                                        break
                                break
                            elif attempt < 2:
                                time.sleep(1)
                            else:
                                _log(f"⚠️ Error creating folder {part}: {e}")
                                raise
                
                # Cache this path
                self._folder_cache[current_path] = parent_id
            
            return parent_id
    
    def file_exists_in_folder(self, folder_path: str, filename: str) -> Optional[Dict]:
        """
        Check if a file already exists in a MEGA folder.
        
        Args:
            folder_path: Folder path in MEGA
            filename: Name of the file to check
            
        Returns:
            Dict with file info (including 'link') if exists, None otherwise
        """
        self.ensure_logged_in()
        
        try:
            folder_id = self.get_or_create_folder(folder_path)
            files = self._m.get_files()
            
            for file_id, file_info in files.items():
                # Check if it's a file (not folder) in the target folder with matching name
                if (file_info.get('t') == 0 and  # 0 = file, 1 = folder
                    file_info.get('p') == folder_id and
                    file_info.get('a', {}).get('n') == filename):
                    # Get existing link
                    try:
                        link = self._m.get_link(file_info)
                        return {
                            'id': file_id,
                            'name': filename,
                            'size': file_info.get('s', 0),
                            'link': link
                        }
                    except:
                        return {'id': file_id, 'name': filename, 'size': file_info.get('s', 0)}
        except Exception as e:
            _log(f"⚠️ Error checking file existence: {e}")
        
        return None
    
    def list_folder_files(self, folder_path: str) -> List[Dict]:
        """
        List all files in a MEGA folder.
        
        Returns:
            List of dicts with file info
        """
        self.ensure_logged_in()
        
        result = []
        try:
            folder_id = self.get_or_create_folder(folder_path)
            files = self._m.get_files()
            
            for file_id, file_info in files.items():
                if (file_info.get('t') == 0 and file_info.get('p') == folder_id):
                    result.append({
                        'id': file_id,
                        'name': file_info.get('a', {}).get('n', ''),
                        'size': file_info.get('s', 0)
                    })
        except Exception as e:
            _log(f"⚠️ Error listing folder: {e}")
        
        return result
    
    def upload_file(self, file_path: str, folder_path: str, dest_filename: Optional[str] = None, 
                    skip_existing: bool = True) -> Optional[str]:
        """
        Upload a file to MEGA.
        
        Args:
            file_path: Local file path to upload
            folder_path: Destination folder path in MEGA
            dest_filename: Optional destination filename (uses original if not specified)
            skip_existing: If True, return existing file's link instead of re-uploading
            
        Returns:
            Public URL or None if failed
        """
        self.ensure_logged_in()
        
        import time
        
        filename = dest_filename or os.path.basename(file_path)
        
        # Check if file already exists
        if skip_existing:
            existing = self.file_exists_in_folder(folder_path, filename)
            if existing:
                _log(f"   ℹ️ File already exists in MEGA: {filename}")
                return existing.get('link')
        
        try:
            folder_id = self.get_or_create_folder(folder_path)
            
            # Retry with backoff
            for attempt in range(3):
                try:
                    uploaded = self._m.upload(file_path, folder_id)
                    link = self._m.get_link(uploaded)
                    return link
                except Exception as e:
                    err_str = str(e)
                    # Error -12 means file already exists
                    if "-12" in err_str:
                        _log(f"   ℹ️ File already exists (MEGA error -12): {filename}")
                        existing = self.file_exists_in_folder(folder_path, filename)
                        if existing:
                            return existing.get('link')
                        return None
                    if attempt < 2:
                        wait = 5 * (attempt + 1)
                        _log(f"⚠️ Upload attempt {attempt+1} failed, retrying in {wait}s...")
                        time.sleep(wait)
                    else:
                        raise
            
        except Exception as e:
            _log(f"⚠️ Upload failed for {file_path}: {e}")
            return None
    
    def upload_cbz(self, cbz_path: str, manga_key: str, chapter_num: str, 
                   skip_existing: bool = True) -> Optional[str]:
        """
        Upload a CBZ file to MEGA.
        
        Args:
            cbz_path: Local path to CBZ file
            manga_key: Manga identifier
            chapter_num: Chapter number/identifier
            
        Returns:
            Public URL or None if failed
        """
        folder_path = f"manga/{manga_key}"
        filename = f"ch_{chapter_num}.cbz"
        
        _log(f"📤 Uploading {filename} to MEGA...")
        
        url = self.upload_file(cbz_path, folder_path, filename)
        
        if url:
            _log(f"   ✅ Uploaded: {filename}")
        else:
            _log(f"   ❌ Failed: {filename}")
        
        return url
    
    def get_folder_link(self, folder_path: str) -> Optional[str]:
        """Get a public link to a folder."""
        self.ensure_logged_in()
        
        try:
            folder_id = self.get_or_create_folder(folder_path)
            # Get folder info and create link
            files = self._m.get_files()
            if folder_id in files:
                link = self._m.get_link(files[folder_id])
                return link
        except Exception as e:
            _log(f"⚠️ Failed to get folder link: {e}")
        
        return None
    
    def upload_image(self, image_data: bytes, folder_path: str, filename: str) -> Optional[str]:
        """
        Upload an image to MEGA.
        
        Args:
            image_data: Raw image bytes
            folder_path: Destination folder path
            filename: Filename to use
            
        Returns:
            Public URL or None if failed
        """
        self.ensure_logged_in()
        
        import tempfile
        
        try:
            folder_id = self.get_or_create_folder(folder_path)
            
            # mega.py requires a real file path, not BytesIO
            # Write to temp file first
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
                tmp.write(image_data)
                tmp_path = tmp.name
            
            try:
                # Upload from temp file
                uploaded = self._m.upload(tmp_path, folder_id)
                
                # Get public link
                link = self._m.get_link(uploaded)
                return link
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            
        except Exception as e:
            _log(f"⚠️ Upload failed for {filename}: {e}")
            return None
    
    def download_and_upload_image(self, image_url: str, folder_path: str, filename: str,
                                   referer: Optional[str] = None) -> Optional[str]:
        """
        Download an image from URL and upload to MEGA.
        
        Args:
            image_url: Source image URL
            folder_path: MEGA destination folder
            filename: Filename to use
            referer: Referer header for download
            
        Returns:
            MEGA public URL or None if failed
        """
        try:
            headers = {
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            if referer:
                headers["Referer"] = referer
            
            resp = self._scraper.get(image_url, timeout=45, headers=headers)
            resp.raise_for_status()
            
            if len(resp.content) < 1000:
                _log(f"⚠️ Image too small, likely error page: {image_url}")
                return None
            
            return self.upload_image(resp.content, folder_path, filename)
            
        except Exception as e:
            _log(f"⚠️ Failed to download {image_url}: {e}")
            return None
    
    def upload_manga_chapter(self, manga_key: str, chapter_num: str, 
                             pages: List[str], source_url: str = "",
                             workers: int = 1) -> List[Dict]:
        """
        Upload all pages of a manga chapter to MEGA.
        
        Args:
            manga_key: Manga identifier
            chapter_num: Chapter number
            pages: List of page image URLs
            source_url: Source manga URL (for referer)
            workers: Ignored - always sequential to avoid rate limits and duplicates
            
        Returns:
            List of dicts with original_url and mega_url
        """
        import time
        
        self.ensure_logged_in()
        
        folder_path = f"manga/{manga_key}/ch_{chapter_num}"
        results = []
        
        # Determine referer based on source
        referer = None
        if "webtoons.com" in source_url:
            referer = "https://www.webtoons.com/"
        elif "manga18" in source_url:
            referer = "https://manga18.club/"
        elif "mangadex" in source_url:
            referer = "https://mangadex.org/"
        
        _log(f"📤 Uploading chapter {chapter_num}: {len(pages)} pages to MEGA (sequential)...")
        
        # Pre-create the folder ONCE before uploading
        try:
            folder_id = self.get_or_create_folder(folder_path)
            _log(f"   📁 Folder ready: {folder_path}")
        except Exception as e:
            _log(f"   ❌ Failed to create folder: {e}")
            return [{"page": i+1, "original_url": url, "mega_url": None, "success": False} 
                    for i, url in enumerate(pages)]
        
        # Upload pages SEQUENTIALLY to avoid rate limits and duplicates
        for idx, page_url in enumerate(pages):
            # Determine extension
            ext = ".jpg"
            if ".png" in page_url.lower():
                ext = ".png"
            elif ".webp" in page_url.lower():
                ext = ".webp"
            elif ".gif" in page_url.lower():
                ext = ".gif"
            
            filename = f"{idx+1:04d}{ext}"
            
            # Single attempt with longer wait on failure
            mega_url = None
            for attempt in range(3):
                mega_url = self.download_and_upload_image(page_url, folder_path, filename, referer)
                if mega_url:
                    break
                # Rate limited - wait longer before retry
                wait_time = 5 * (attempt + 1)  # 5s, 10s, 15s
                _log(f"   ⏳ Rate limited, waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            
            results.append({
                "page": idx + 1,
                "original_url": page_url,
                "mega_url": mega_url,
                "success": mega_url is not None
            })
            
            if mega_url:
                _log(f"   ✅ Page {idx+1}/{len(pages)} uploaded")
            else:
                _log(f"   ❌ Page {idx+1}/{len(pages)} failed")
            
            # Delay between uploads to avoid rate limiting (1.5 seconds)
            if idx < len(pages) - 1:
                time.sleep(1.5)
        
        success_count = sum(1 for r in results if r["success"])
        _log(f"   ✅ Uploaded {success_count}/{len(pages)} pages")
        
        return results
    
    def get_storage_quota(self) -> Dict:
        """Get MEGA storage quota info."""
        self.ensure_logged_in()
        
        try:
            quota = self._m.get_quota()
            used = self._m.get_storage_space(giga=True)
            return {
                "total_gb": quota,
                "used_gb": used.get('used', 0),
                "free_gb": quota - used.get('used', 0) if quota else None
            }
        except Exception as e:
            _log(f"⚠️ Failed to get quota: {e}")
            return {}
    
    def find_file(self, path: str) -> Optional[str]:
        """
        Find a file by path and return its public URL if exists.
        
        Args:
            path: File path like "manga/one_punch-man/chapters/1/0001.jpg"
            
        Returns:
            Public URL or None if not found
        """
        self.ensure_logged_in()
        
        try:
            file = self._m.find(path)
            if file:
                return self._m.get_link(file)
        except Exception:
            pass
        return None


# Singleton instance
_mega_storage: Optional[MegaStorage] = None


def get_mega_storage() -> Optional[MegaStorage]:
    """Get or create MEGA storage instance."""
    global _mega_storage
    
    if _mega_storage is None:
        email = os.getenv("MEGA_EMAIL")
        password = os.getenv("MEGA_PASSWORD")
        
        if email and password:
            try:
                _mega_storage = MegaStorage(email, password)
                _mega_storage.login()
            except Exception as e:
                _log(f"⚠️ MEGA storage initialization failed: {e}")
                return None
    
    return _mega_storage


def is_mega_configured() -> bool:
    """Check if MEGA credentials are configured."""
    return bool(os.getenv("MEGA_EMAIL") and os.getenv("MEGA_PASSWORD"))
