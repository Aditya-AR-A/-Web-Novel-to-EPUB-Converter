#!/usr/bin/env python3
"""
Database migration script to update column names from s3_* to storage_*
This handles the transition from S3-specific naming to storage-agnostic naming.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings
from sqlalchemy import create_engine, text, inspect


def migrate_postgresql():
    """Migrate PostgreSQL database schema"""
    engine = create_engine(settings.database_url)
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        
        # Check if table exists
        if 'epubs' not in inspector.get_table_names():
            print("ℹ️  Table 'epubs' does not exist. Creating fresh schema...")
            from app.db.models import Base
            Base.metadata.create_all(bind=engine)
            print("✅ Fresh schema created successfully")
            return
        
        # Get current columns
        columns = {col['name']: col for col in inspector.get_columns('epubs')}
        indexes = {idx['name']: idx for idx in inspector.get_indexes('epubs')}
        
        # Check if migration is needed
        if 's3_key' in columns and 'storage_key' not in columns:
            print("🔄 Migrating PostgreSQL schema from s3_* to storage_* columns...")
            
            # Rename columns
            conn.execute(text('ALTER TABLE epubs RENAME COLUMN s3_key TO storage_key'))
            conn.execute(text('ALTER TABLE epubs RENAME COLUMN s3_url TO storage_url'))
            conn.commit()
            
            print("✅ PostgreSQL migration completed successfully")
        elif 'storage_file_id' in columns and 'storage_key' not in columns:
            print("🔄 Migrating PostgreSQL schema from storage_file_* columns to storage_* columns...")

            # Rename primary columns
            conn.execute(text('ALTER TABLE epubs RENAME COLUMN storage_file_id TO storage_key'))
            conn.execute(text('ALTER TABLE epubs RENAME COLUMN download_url TO storage_url'))

            # Ensure the storage_key column matches expected size
            conn.execute(text('ALTER TABLE epubs ALTER COLUMN storage_key TYPE VARCHAR(512)'))

            # Drop legacy filename column if present (new schema no longer uses it)
            if 'storage_file_name' in columns:
                conn.execute(text('ALTER TABLE epubs DROP COLUMN storage_file_name'))

            # Rename index if it exists
            if 'ix_epubs_storage_file_id' in indexes:
                conn.execute(text('ALTER INDEX ix_epubs_storage_file_id RENAME TO ix_epubs_storage_key'))

            conn.commit()

            print("✅ PostgreSQL migration from storage_file_* completed successfully")
        elif 'storage_key' in columns:
            print("✅ Database already migrated (storage_* columns exist)")
        else:
            print("⚠️  Unexpected schema state. Creating fresh schema...")
            from app.db.models import Base
            Base.metadata.create_all(bind=engine)
            print("✅ Schema updated")


def migrate_sqlite():
    """Migrate SQLite database schema"""
    engine = create_engine(settings.database_url)
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        
        # Check if table exists
        if 'epubs' not in inspector.get_table_names():
            print("ℹ️  Table 'epubs' does not exist. Creating fresh schema...")
            from app.db.models import Base
            Base.metadata.create_all(bind=engine)
            print("✅ Fresh schema created successfully")
            return
        
        # Get current columns
        columns = {col['name']: col for col in inspector.get_columns('epubs')}
        
        # Check if migration is needed
        if 's3_key' in columns and 'storage_key' not in columns:
            print("🔄 Migrating SQLite schema from s3_* to storage_* columns...")
            
            # SQLite doesn't support column rename directly, need to recreate table
            # Get all data
            result = conn.execute(text('SELECT * FROM epubs'))
            rows = result.fetchall()
            
            # Drop old table
            conn.execute(text('DROP TABLE epubs'))
            conn.commit()
            
            # Create new table with correct schema
            from app.db.models import Base
            Base.metadata.create_all(bind=engine)
            
            # Restore data with column mapping
            if rows:
                for row in rows:
                    # Map old columns to new ones
                    data = row._mapping if hasattr(row, '_mapping') else row
                    storage_key_val = data.get('s3_key')
                    storage_url_val = data.get('s3_url')
                    if storage_key_val is None and data.get('storage_file_id') is not None:
                        storage_key_val = data.get('storage_file_id')
                    if storage_url_val is None and data.get('download_url') is not None:
                        storage_url_val = data.get('download_url')
                    conn.execute(
                        text("""
                        INSERT INTO epubs 
                        (id, title, author, source_url, storage_key, storage_url, 
                         file_size, status, error_message, created_at, updated_at)
                        VALUES 
                        (:id, :title, :author, :source_url, :s3_key, :s3_url,
                         :file_size, :status, :error_message, :created_at, :updated_at)
                        """),
                        {
                            'id': row.id,
                            'title': row.title,
                            'author': row.author,
                            'source_url': row.source_url,
                            's3_key': storage_key_val,
                            's3_url': storage_url_val,
                            'file_size': row.file_size,
                            'status': row.status,
                            'error_message': row.error_message,
                            'created_at': row.created_at,
                            'updated_at': row.updated_at,
                        }
                    )
                conn.commit()
                print(f"✅ Migrated {len(rows)} records")
            
            print("✅ SQLite migration completed successfully")
        elif 'storage_file_id' in columns and 'storage_key' not in columns:
            print("🔄 Migrating SQLite schema from storage_file_* columns to storage_* columns...")

            result = conn.execute(text('SELECT * FROM epubs'))
            rows = result.fetchall()

            conn.execute(text('DROP TABLE epubs'))
            conn.commit()

            from app.db.models import Base
            Base.metadata.create_all(bind=engine)

            if rows:
                for row in rows:
                    data = row._mapping if hasattr(row, '_mapping') else row
                    conn.execute(
                        text("""
                        INSERT INTO epubs 
                        (id, title, author, source_url, storage_key, storage_url, 
                         file_size, status, error_message, created_at, updated_at)
                        VALUES 
                        (:id, :title, :author, :source_url, :storage_key, :storage_url,
                         :file_size, :status, :error_message, :created_at, :updated_at)
                        """),
                        {
                            'id': data.get('id'),
                            'title': data.get('title'),
                            'author': data.get('author'),
                            'source_url': data.get('source_url'),
                            'storage_key': data.get('storage_file_id') or data.get('storage_key'),
                            'storage_url': data.get('download_url') or data.get('storage_url') or '',
                            'file_size': data.get('file_size') or 0,
                            'status': data.get('status') or 'ready',
                            'error_message': data.get('error_message'),
                            'created_at': data.get('created_at'),
                            'updated_at': data.get('updated_at'),
                        }
                    )
                conn.commit()
                print(f"✅ Migrated {len(rows)} records")

            print("✅ SQLite migration from storage_file_* completed successfully")
        elif 'storage_key' in columns:
            print("✅ Database already migrated (storage_* columns exist)")
        else:
            print("⚠️  Unexpected schema state. Creating fresh schema...")
            from app.db.models import Base
            Base.metadata.create_all(bind=engine)
            print("✅ Schema updated")


def main():
    """Run database migration"""
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   📚 Web Novel to EPUB - Database Migration                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    
    print(f"Database URL: {settings.database_url[:50]}...")
    print()
    
    try:
        if settings.database_url.startswith('sqlite'):
            migrate_sqlite()
        elif settings.database_url.startswith('postgresql'):
            migrate_postgresql()
        else:
            print(f"❌ Unsupported database type: {settings.database_url.split(':')[0]}")
            return 1
        
        print()
        print("✅ Migration completed successfully!")
        print("   You can now start the application.")
        return 0
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
