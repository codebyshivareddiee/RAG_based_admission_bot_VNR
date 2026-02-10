import sys
import subprocess
from app.data.init_db import get_db, COLLECTION

print("="*60)
print("INGESTING 2024 PAGES 3-4 (SPECIAL CATEGORIES)")
print("="*60)

# Run the ingestion
result = subprocess.run([
    sys.executable, "-m", "app.data.ingest_eapcet",
    "--pdf", "docs/EAPCET_First-and-Last-Ranks-2024.pdf",
    "--year", "2024", 
    "--page", "special"
], capture_output=True, text=True)

print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

print("\n" + "="*60)
print("VERIFYING 2024 DATA IN FIRESTORE")
print("="*60)

# Verify what's in Firestore
db = get_db()
docs_2024 = list(db.collection(COLLECTION).where('year', '==', 2024).stream())
docs_2025 = list(db.collection(COLLECTION).where('year', '==', 2025).stream())

print(f'\nTotal 2024 records: {len(docs_2024)}')
print(f'Total 2025 records: {len(docs_2025)}')

# Count by quota for 2024
quotas = {}
for d in docs_2024:
    q = d.to_dict().get('quota', 'Convenor')
    quotas[q] = quotas.get(q, 0) + 1

print(f'\n2024 Breakdown by Quota:')
for q, count in sorted(quotas.items()):
    print(f'  {q}: {count} records')

# Show sample special quota records
special_quotas = [d.to_dict() for d in docs_2024 if d.to_dict().get('quota') in ['SPORTS', 'CAP', 'NCC', 'OTHERS']]
if special_quotas:
    print(f'\n✅ Found {len(special_quotas)} special quota records for 2024')
    print(f'\nSample records (first 10):')
    for rec in special_quotas[:10]:
        branch = rec.get('branch', 'N/A')
        quota = rec.get('quota', 'N/A')
        caste = rec.get('caste', 'N/A')
        gender = rec.get('gender', 'N/A')
        rank = rec.get('first_rank', 'N/A')
        ph = rec.get('ph_type', '')
        ph_str = f" | PH:{ph}" if ph else ""
        print(f"  {branch:12} | {quota:7} | {caste:8} | {gender:5} | Rank:{rank:6}{ph_str}")
else:
    print(f'\n⚠️  NO special quota records found - ingestion may have failed!')

print("\n" + "="*60)
