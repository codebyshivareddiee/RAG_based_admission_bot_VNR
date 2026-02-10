from app.data.init_db import get_db, COLLECTION

db = get_db()
docs_2024 = list(db.collection(COLLECTION).where('year', '==', 2024).stream())

print(f'\nTotal 2024 records: {len(docs_2024)}')

# Count by quota
quotas = {}
for d in docs_2024:
    q = d.to_dict().get('quota', 'Convenor')
    quotas[q] = quotas.get(q, 0) + 1

print(f'\n2024 breakdown by quota:')
for q, count in sorted(quotas.items()):
    print(f'  {q}: {count}')

# Show some sample SPORTS/CAP/NCC/OTHERS records if they exist
special_quotas = [d.to_dict() for d in docs_2024 if d.to_dict().get('quota') in ['SPORTS', 'CAP', 'NCC', 'OTHERS']]
if special_quotas:
    print(f'\nSpecial quota samples (first 5):')
    for rec in special_quotas[:5]:
        print(f"  {rec.get('branch')} | {rec.get('quota')} | {rec.get('caste')} | {rec.get('gender')}")
else:
    print(f'\n⚠️ No special quota records found for 2024!')
