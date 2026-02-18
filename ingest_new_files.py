"""
Ingest only NEW text files that are not already in Pinecone database.
Checks existing files in DB to avoid re-ingesting and wasting API calls.
"""
from pathlib import Path
from app.rag.ingest import ingest_file, _get_index
from app.config import get_settings

def get_ingested_filenames():
    """Query Pinecone to get list of already ingested filenames."""
    try:
        index = _get_index()
        settings = get_settings()
        
        # Query with a dummy vector to get stats
        stats = index.describe_index_stats()
        
        # If index is empty, return empty set
        if stats.total_vector_count == 0:
            return set()
        
        # Query to get sample vectors and extract filenames
        # We'll use scroll/pagination to get unique filenames
        result = index.query(
            vector=[0.0] * 1536,  # Dummy vector
            top_k=10000,
            include_metadata=True
        )
        
        filenames = set()
        for match in result.matches:
            if 'filename' in match.metadata:
                filenames.add(match.metadata['filename'])
        
        return filenames
    except Exception as e:
        print(f"⚠️  Could not check existing files: {e}")
        print("    Proceeding with ingestion...\n")
        return set()

def main():
    print("\n🔍 Checking which files are already in database...\n")
    
    # Get list of already ingested files
    existing_files = get_ingested_filenames()
    
    if existing_files:
        print(f"📊 Found {len(existing_files)} files already in database:")
        for fname in sorted(existing_files):
            print(f"   • {fname}")
        print()
    else:
        print("📊 No files found in database (empty or first ingestion)\n")
    
    # List all txt files in docs/txt/
    txt_dir = Path("docs/txt")
    all_files = sorted([f for f in txt_dir.glob("*.txt") if f.is_file()])
    
    # Filter out already ingested files
    files_to_ingest = [f for f in all_files if f.name not in existing_files]
    
    if not files_to_ingest:
        print("✅ All files are already ingested. Nothing new to add!\n")
        return
    
    print(f"📁 Found {len(files_to_ingest)} NEW files to ingest:\n")
    for f in files_to_ingest:
        print(f"   • {f.name}")
    print()
    
    total_chunks = 0
    for i, fpath in enumerate(files_to_ingest, 1):
        print(f"[{i}/{len(files_to_ingest)}] Processing: {fpath.name}")
        try:
            chunks = ingest_file(fpath, source_label="admissions_docs", year=2025)
            total_chunks += chunks
            print(f"    ✅ Success: {chunks} chunks\n")
        except Exception as e:
            print(f"    ❌ Error: {e}\n")
            continue
    
    print(f"🎉 COMPLETED: {total_chunks} total chunks ingested from {len(files_to_ingest)} NEW files\n")

if __name__ == "__main__":
    main()
