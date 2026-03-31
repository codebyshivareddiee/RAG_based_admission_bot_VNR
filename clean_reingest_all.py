"""
Clean re-ingestion: Delete entire database and re-ingest all files.
Use this if you've modified many files or want a fresh start.
"""
from pathlib import Path
from app.rag.ingest import ingest_file, _get_index
from app.config import get_settings

def clear_entire_database():
    """Delete ALL vectors from Pinecone index."""
    index = _get_index()
    
    # Delete all vectors (this might take a while for large databases)
    try:
        index.delete(delete_all=True)
        print("🗑️  Cleared entire vector database")
        return True
    except Exception as e:
        print(f"❌ Error clearing database: {e}")
        return False

def main():
    """Clear database and re-ingest all files."""
    
    print("⚠️  WARNING: This will delete ALL existing vectors and re-ingest everything!")
    response = input("Are you sure you want to continue? (yes/no): ").strip().lower()
    
    if response != "yes":
        print("❌ Operation cancelled")
        return
    
    # Step 1: Clear database
    if not clear_entire_database():
        print("❌ Failed to clear database. Aborting.")
        return
    
    print("✅ Database cleared successfully\n")
    
    # Step 2: Re-ingest all files
    print("📁 Re-ingesting all documentation files...")
    
    txt_dir = Path("docs/txt")
    files = sorted([f for f in txt_dir.glob("*.txt") if f.is_file()])
    
    if not files:
        print("❌ No .txt files found in docs/txt/")
        return
    
    print(f"Found {len(files)} files to ingest\n")
    
    total_chunks = 0
    for i, fpath in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Processing: {fpath.name}")
        try:
            chunks = ingest_file(fpath, source_label="admissions_docs", year=2025)
            total_chunks += chunks
            print(f"    ✅ Success: {chunks} chunks\n")
        except Exception as e:
            print(f"    ❌ Error: {e}\n")
            continue
    
    print(f"🎉 COMPLETED: Fresh database with {total_chunks} total chunks from {len(files)} files\n")

if __name__ == "__main__":
    main()