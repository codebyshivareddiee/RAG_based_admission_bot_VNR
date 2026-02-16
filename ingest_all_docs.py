"""
Simple script to ingest TXT documents into Pinecone with progress tracking.
Only processes .txt files from docs/txt/ directory.
"""
from pathlib import Path
from app.rag.ingest import ingest_file

def main():
    txt_dir = Path("docs/txt")
    
    if not txt_dir.exists():
        print(f"❌ Error: {txt_dir} directory not found!")
        return
    
    # Only process .txt files
    files = [f for f in sorted(txt_dir.iterdir()) if f.suffix.lower() == ".txt"]
    
    if not files:
        print(f"\n⚠️  No .txt files found in {txt_dir}\n")
        return
    
    print(f"\n📁 Found {len(files)} TXT documents to ingest from docs/txt/\n")
    
    total_chunks = 0
    for i, fpath in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] Processing: {fpath.name}")
        try:
            chunks = ingest_file(fpath, source_label="admissions_docs", year=2025)
            total_chunks += chunks
            print(f"    ✅ Success: {chunks} chunks")
        except Exception as e:
            print(f"    ❌ Error: {e}")
            continue
    
    print(f"\n🎉 COMPLETED: {total_chunks} total chunks ingested from {len(files)} TXT files\n")

if __name__ == "__main__":
    main()
