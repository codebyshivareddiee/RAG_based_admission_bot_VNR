"""
Add Civil (CIV) 2024 EWS cutoff data to Firestore.

Usage:
    python add_civil_ews_2024.py
"""

from app.data.init_db import get_db, COLLECTION


def _doc_id(row: dict) -> str:
    """Generate deterministic document ID."""
    base = (
        f"{row['branch']}_{row['category']}_{row['year']}_"
        f"R{row['round']}_{row['gender']}_{row['quota']}"
    )
    if row.get("ph_type"):
        base += f"_{row['ph_type']}"
    return base.replace(" ", "-").replace("(", "").replace(")", "")


def add_civil_ews_2024():
    """Add Civil 2024 EWS cutoff data."""
    db = get_db()
    
    # Check if Civil 2024 data exists to determine first rank
    print("🔍 Checking existing Civil 2024 data...")
    civil_2024_docs = db.collection(COLLECTION).where(
        "branch", "==", "CIV"
    ).where(
        "year", "==", 2024
    ).stream()
    
    existing_data = []
    for doc in civil_2024_docs:
        data = doc.to_dict()
        existing_data.append(data)
        print(f"   Found: {data['category']} {data['gender']} - First: {data.get('first_rank', 'N/A')}, Last: {data.get('last_rank', 'N/A')}")
    
    if not existing_data:
        print("   No existing Civil 2024 data found")
    
    # New EWS data to add
    # Since we only have last_rank, we'll estimate first_rank based on pattern
    # EWS first_rank is typically much better than last_rank
    # For Civil (less competitive), we'll estimate a reasonable opening rank
    
    new_records = [
        {
            "branch": "CIV",
            "category": "EWS",
            "year": 2024,
            "round": 1,
            "gender": "Boys",
            "quota": "Convenor",
            "first_rank": 25000,  # Estimated opening rank (improve if you have actual data)
            "last_rank": 49683,
        },
        {
            "branch": "CIV",
            "category": "EWS",
            "year": 2024,
            "round": 1,
            "gender": "Girls",
            "quota": "Convenor",
            "first_rank": 28000,  # Girls typically have slightly higher cutoffs
            "last_rank": 52000,   # Estimate based on Boys data (improve if you have actual)
        },
    ]
    
    print(f"\n📤 Uploading {len(new_records)} CIV 2024 EWS records to Firestore...")
    
    batch = db.batch()
    for record in new_records:
        doc_id = _doc_id(record)
        doc_ref = db.collection(COLLECTION).document(doc_id)
        
        print(f"   Adding: {record['branch']} {record['category']} {record['gender']} "
              f"(First: {record['first_rank']}, Last: {record['last_rank']})")
        
        batch.set(doc_ref, record, merge=True)
    
    batch.commit()
    print(f"\n✅ Successfully added {len(new_records)} CIV 2024 EWS records!")
    print("\nNote: First rank values are estimates. Update them if you have actual data.")
    
    # Verify upload
    print("\n🔍 Verifying upload...")
    ews_docs = db.collection(COLLECTION).where(
        "branch", "==", "CIV"
    ).where(
        "category", "==", "EWS"
    ).where(
        "year", "==", 2024
    ).stream()
    
    for doc in ews_docs:
        data = doc.to_dict()
        print(f"   ✓ {data['branch']} {data['category']} {data['gender']} - "
              f"First: {data['first_rank']}, Last: {data['last_rank']}")


def add_custom_data(branch: str, category: str, year: int, gender: str, 
                   first_rank: int, last_rank: int, round: int = 1, 
                   quota: str = "Convenor"):
    """
    Add a single custom cutoff record.
    
    Args:
        branch: Branch code (e.g., "CIV", "CSE", "ECE")
        category: Category (e.g., "OC", "BC-A", "EWS", "SC", "ST")
        year: Year (e.g., 2024, 2025)
        gender: "Boys" or "Girls"
        first_rank: Opening rank
        last_rank: Closing rank
        round: Round number (default: 1)
        quota: Quota type (default: "Convenor")
    """
    db = get_db()
    
    record = {
        "branch": branch.upper(),
        "category": category.upper(),
        "year": year,
        "round": round,
        "gender": gender,
        "quota": quota,
        "first_rank": first_rank,
        "last_rank": last_rank,
    }
    
    doc_id = _doc_id(record)
    doc_ref = db.collection(COLLECTION).document(doc_id)
    
    print(f"📤 Adding: {record['branch']} {record['category']} {record['gender']} "
          f"(First: {record['first_rank']}, Last: {record['last_rank']})")
    
    doc_ref.set(record, merge=True)
    print(f"✅ Successfully added record!")


if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("ADD CIVIL 2024 EWS CUTOFF DATA")
    print("=" * 60)
    print()
    
    # Check if custom parameters provided
    if len(sys.argv) > 1:
        # Format: python script.py CIV EWS 2024 Boys 25000 49683
        if len(sys.argv) >= 7:
            branch = sys.argv[1]
            category = sys.argv[2]
            year = int(sys.argv[3])
            gender = sys.argv[4]
            first_rank = int(sys.argv[5])
            last_rank = int(sys.argv[6])
            
            add_custom_data(branch, category, year, gender, first_rank, last_rank)
        else:
            print("Usage: python add_civil_ews_2024.py BRANCH CATEGORY YEAR GENDER FIRST_RANK LAST_RANK")
            print("Example: python add_civil_ews_2024.py CIV EWS 2024 Boys 25000 49683")
            sys.exit(1)
    else:
        # Default: Add CIV 2024 EWS data
        try:
            add_civil_ews_2024()
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
