"""
Diagnostic: check ALL Firestore docs for CSE-CSM / CSE-CSO and simulate get_cutoff().
"""
from app.data.init_db import get_db, COLLECTION
from google.cloud.firestore_v1.base_query import FieldFilter
from app.logic.cutoff_engine import get_cutoff

db = get_db()

# ── PART 1: raw Firestore dump (all quotas/rounds) ──
print("=" * 65)
print("PART 1 – All Firestore records  (BC-D / 2023, all quotas)")
print("=" * 65)
for branch in ["CSE-CSM", "CSE-CSO"]:
    q = (
        db.collection(COLLECTION)
        .where(filter=FieldFilter("branch", "==", branch))
        .where(filter=FieldFilter("year",   "==", 2023))
        .where(filter=FieldFilter("category", "==", "BC-D"))
    )
    docs = list(q.stream())
    print(f"\n{branch}  ({len(docs)} docs)")
    for doc in docs:
        d = doc.to_dict()
        print(
            f"  gender={str(d.get('gender')):<6}  "
            f"quota={str(d.get('quota')):<10}  "
            f"round={d.get('round')}  "
            f"first={d.get('first_rank')}  "
            f"last={d.get('last_rank')}  "
            f"cutoff={d.get('cutoff_rank')}"
        )

# ── PART 2: simulate get_cutoff() ──────────────────
print()
print("=" * 65)
print("PART 2 – get_cutoff() result for BC-D / Boys / 2023")
print("=" * 65)
for branch in ["CSE-CSM", "CSE-CSO"]:
    r = get_cutoff(branch, "BC-D", year=2023, gender="Boys")
    print(f"\n{branch}:")
    print(f"  found={r.found}  first_rank={r.first_rank}  last_rank={r.last_rank}")
    print(f"  message (first 150 chars):\n    {r.message[:150]}")
