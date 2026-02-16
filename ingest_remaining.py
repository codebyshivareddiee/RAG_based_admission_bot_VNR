"""
Ingest only remaining documents (starting from TGEAPCET24REVISED.pdf).
"""
from pathlib import Path
from app.rag.ingest import ingest_file

def main():
    docs_dir = Path("docs")
    
    # Only process these remaining files
    remaining_files = [
        "vnrvjiet_admissions.txt",
        "vnrvjiet_branches_intake.txt",
    ]
    
    files = [docs_dir / fname for fname in remaining_files if (docs_dir / fname).exists()]
    
    print(f"\n📁 Processing {len(files)} remaining documents\n")
    
    total_chunks = 0
    for i, fpath in enumerate(files, 8):  # Start counting from 8
        print(f"\n[{i}/11] Processing: {fpath.name}")
        try:
            chunks = ingest_file(fpath, source_label="admissions_docs", year=2025)
            total_chunks += chunks
            print(f"    ✅ Success: {chunks} chunks")
        except Exception as e:
            print(f"    ❌ Error: {str(e)[:200]}")
            continue
    
    print(f"\n🎉 COMPLETED: {total_chunks} chunks ingested from {len(files)} remaining files\n")

if __name__ == "__main__":
    main()
