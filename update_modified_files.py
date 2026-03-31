"""
Update modified files in Pinecone by deleting old vectors and re-ingesting.
Specify which files have been modified to avoid full re-ingestion.
"""
from pathlib import Path
from app.rag.ingest import ingest_file, _get_index
from app.config import get_settings

def delete_file_vectors(filename):
    """Delete all vectors for a specific filename from Pinecone."""
    index = _get_index()
    
    # Query vectors for this filename
    result = index.query(
        vector=[0.0] * 1536,
        top_k=10000,
        filter={"filename": filename},
        include_metadata=True
    )
    
    if result.matches:
        # Extract IDs to delete
        ids_to_delete = [match.id for match in result.matches]
        
        # Delete in batches (Pinecone limit)
        batch_size = 1000
        for i in range(0, len(ids_to_delete), batch_size):
            batch = ids_to_delete[i:i + batch_size]
            index.delete(ids=batch)
        
        print(f"🗑️  Deleted {len(ids_to_delete)} old vectors for {filename}")
        return len(ids_to_delete)
    else:
        print(f"ℹ️  No existing vectors found for {filename}")
        return 0

def update_file(filepath):
    """Delete old vectors and re-ingest a modified file."""
    path = Path(filepath)
    
    if not path.exists():
        print(f"❌ File not found: {filepath}")
        return 0
    
    # Step 1: Delete old vectors
    deleted_count = delete_file_vectors(path.name)
    
    # Step 2: Re-ingest the file
    try:
        chunks = ingest_file(path, source_label="admissions_docs", year=2025)
        print(f"✅ Re-ingested {chunks} chunks for {path.name}")
        return chunks
    except Exception as e:
        print(f"❌ Error re-ingesting {path.name}: {e}")
        return 0

def main():
    """Update specific modified files."""
    
    # LIST YOUR MODIFIED FILES HERE
    modified_files = [
        "docs/txt/vnrvjiet_admissions-4.txt",           # Example: if you modified this
        "docs/txt/Departments.txt",                     # Example: if you modified this  
        "docs/txt/Seats_intake_branchwise.txt",         # Example: if you modified this
        # Add more files that you've modified...
    ]
    
    print("🔄 Updating modified files in vector database...\n")
    
    total_chunks = 0
    for i, filepath in enumerate(modified_files, 1):
        print(f"[{i}/{len(modified_files)}] Updating: {Path(filepath).name}")
        chunks = update_file(filepath)
        total_chunks += chunks
        print()
    
    print(f"🎉 Updated {len(modified_files)} files with {total_chunks} total chunks\n")
    
    # Also ingest any completely new files
    print("📝 Now ingesting any new files...")
    import subprocess
    subprocess.run(["python", "ingest_new_files.py"])

if __name__ == "__main__":
    main()