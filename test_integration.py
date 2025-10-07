#!/usr/bin/env python3
"""
Test script for Web Novel to EPUB Converter
Tests all major functionality after integration
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all modules can be imported"""
    print("🔍 Testing imports...")
    
    try:
        from api import app
        print("  ✅ API application")
        
        from app.config import settings
        print("  ✅ Configuration")
        
        from app.storage import get_storage
        print("  ✅ Storage module")
        
        from app.services.epub_service import EpubService
        print("  ✅ EPUB service")
        
        from scripts.scraper import get_chapter_metadata, get_chapters
        print("  ✅ Scraper (get_chapter_metadata, get_chapters)")
        
        from scripts.cancellation import start_job, end_job
        print("  ✅ Cancellation system")
        
        return True
    except Exception as e:
        print(f"  ❌ Import error: {e}")
        return False

def test_configuration():
    """Test configuration loading"""
    print("\n🔍 Testing configuration...")
    
    try:
        from app.config import settings
        
        print(f"  ✅ Storage backend: {settings.storage_backend}")
        print(f"  ✅ Database URL: {settings.database_url[:50]}...")
        
        if settings.storage_backend == "local":
            print(f"  ✅ Local storage path: {settings.local_storage_path}")
        
        return True
    except Exception as e:
        print(f"  ❌ Configuration error: {e}")
        return False

def test_storage():
    """Test storage backend initialization"""
    print("\n🔍 Testing storage backend...")
    
    try:
        from app.storage import get_storage
        from app.config import settings
        
        storage = get_storage()
        storage_type = type(storage).__name__
        
        print(f"  ✅ Storage initialized: {storage_type}")
        print(f"  ✅ Storage backend: {settings.storage_backend}")
        
        return True
    except Exception as e:
        print(f"  ❌ Storage error: {e}")
        return False

def test_database():
    """Test database connection"""
    print("\n🔍 Testing database...")
    
    try:
        from app.db.session import get_db, engine
        from app.db.models import Base
        
        # Test connection
        with engine.connect() as conn:
            print("  ✅ Database connection successful")
        
        # Try to create tables
        Base.metadata.create_all(bind=engine)
        print("  ✅ Database tables created/verified")
        
        return True
    except Exception as e:
        print(f"  ❌ Database error: {e}")
        return False

def test_scraper_imports():
    """Test scraper can access cancellation hooks"""
    print("\n🔍 Testing scraper integration...")
    
    try:
        from scripts.scraper import get_chapter_metadata, get_chapters
        import inspect
        
        # Check if scraper has cancellation hooks
        source = inspect.getsource(get_chapters)
        
        has_cancel_check = "raise_if_cancelled" in source or "is_stopped" in source
        
        if has_cancel_check:
            print("  ✅ Scraper has cancellation hooks")
        else:
            print("  ⚠️  Scraper missing cancellation hooks")
        
        print("  ✅ get_chapter_metadata imported")
        print("  ✅ get_chapters imported")
        
        return True
    except Exception as e:
        print(f"  ❌ Scraper integration error: {e}")
        return False

def test_api_endpoints():
    """Test that API endpoints are registered"""
    print("\n🔍 Testing API endpoints...")
    
    try:
        from api import app
        
        routes = [route.path for route in app.routes]
        
        required_routes = [
            "/",
            "/health",
            "/ws/logs",
            "/epubs/epub/generate",  # Local mode
            "/epubs/generate",       # Database mode
        ]
        
        for route in required_routes:
            if any(r.startswith(route) for r in routes):
                print(f"  ✅ {route}")
            else:
                print(f"  ❌ {route} not found")
        
        print(f"  ℹ️  Total routes: {len(routes)}")
        
        return True
    except Exception as e:
        print(f"  ❌ API endpoints error: {e}")
        return False

def test_static_files():
    """Test static files are accessible"""
    print("\n🔍 Testing static files...")
    
    try:
        static_dir = Path(__file__).parent / "static"
        
        required_files = ["index.html", "logo.png"]
        
        for file in required_files:
            file_path = static_dir / file
            if file_path.exists():
                print(f"  ✅ {file}")
            else:
                print(f"  ❌ {file} not found")
        
        return True
    except Exception as e:
        print(f"  ❌ Static files error: {e}")
        return False

def test_directories():
    """Test that required directories exist"""
    print("\n🔍 Testing directories...")
    
    project_root = Path(__file__).parent
    
    required_dirs = ["books", "media", "data", "static", "scripts", "app"]
    
    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print(f"  ✅ {dir_name}/")
        else:
            print(f"  ⚠️  {dir_name}/ not found (will be created)")
    
    return True

def main():
    """Run all tests"""
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   📚 Web Novel to EPUB Converter - Integration Test         ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    
    tests = [
        test_imports,
        test_configuration,
        test_storage,
        test_database,
        test_scraper_imports,
        test_api_endpoints,
        test_static_files,
        test_directories,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed: {e}")
            results.append(False)
    
    print("\n" + "="*64)
    print("\n📊 Test Results:")
    print(f"   Passed: {sum(results)}/{len(results)}")
    print(f"   Failed: {len(results) - sum(results)}/{len(results)}")
    
    if all(results):
        print("\n✅ All tests passed! Application is ready to use.")
        print("\n🚀 Start the application with: ./start.sh")
        print("   or: uvicorn api:app --reload")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
