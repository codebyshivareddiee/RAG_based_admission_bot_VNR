"""Extract EWS data from 2022/2023 PDF page 4"""
import sys
import pdfplumber
from app.data.init_db import get_db, COLLECTION

# Get year from command line (default 2023)
year = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
pdf_file = f'docs/First-and-Last-Ranks-{year}.pdf' if year == 2022 else f'docs/First-and-Last-Ranks-{year}-Eamcet.pdf'

print(f"Processing {pdf_file} for year {year}...")

# Column layout for page 4 (0-indexed):
# Branch | EWS OC Boys(First/Last) | EWS OC Girls(First/Last)
# Column indices: 0=Branch, 3=Boys First, 8=Boys Last, 9=Girls First, 15=Girls Last
EWS_COL_BOYS_FIRST = 3
EWS_COL_BOYS_LAST = 8
EWS_COL_GIRLS_FIRST = 9
EWS_COL_GIRLS_LAST = 15

BRANCH_NORMALIZE_MAP = {
    "CSE- CSC": "CSE-CSC",
    "CSE -CSC": "CSE-CSC",
    "CSE- CSD": "CSE-CSD",
    "CSE -CSD": "CSE-CSD",
    "CSE- CSM": "CSE-CSM",
    "CSE -CSM": "CSE-CSM",
    "CSE- CSO": "CSE-CSO",
    "CSE -CSO": "CSE-CSO",
    "CIVIL": "CIV",
    "MECH": "ME",
}

def normalize_branch(branch: str) -> str:
    """Normalize branch name."""
    if not branch:
        return branch
    branch = branch.strip()
    return BRANCH_NORMALIZE_MAP.get(branch, branch)

def clean_rank(row, col_start, col_end):
    """Extract rank from columns, handling split digits."""
    cells = row[col_start:col_end+1]
    # Concatenate non-None values
    rank_str = ''.join(str(cell).strip() if cell and str(cell).strip() else '' for cell in cells)
    if rank_str and rank_str != '--' and rank_str.isdigit():
        return int(rank_str)
    return None

pdf = pdfplumber.open(pdf_file)
page = pdf.pages[3]  # Page 4 (0-indexed)

print("Extracting EWS data from page 4...")
tables = page.extract_tables()
# Find largest table (handles PDFs with header tables)
table = max(tables, key=lambda t: len(t) if t else 0)
print(f"Table has {len(table)} rows × {len(table[0]) if table else 0} columns")

records = []
for i, row in enumerate(table[3:], start=3):  # Skip 3 header rows
    branch = row[0]
    if not branch or branch.strip() == "":
        continue
    branch = normalize_branch(branch)
    
    # Extract Boys data
    boys_first = clean_rank(row, EWS_COL_BOYS_FIRST, EWS_COL_BOYS_LAST - 1)
    boys_last = clean_rank(row, EWS_COL_BOYS_LAST, EWS_COL_GIRLS_FIRST - 1)
    
    if boys_first:
        records.append({
            "branch": branch,
            "caste": "EWS",
            "gender": "Boys",
            "first_rank": boys_first,
            "last_rank": boys_last if boys_last else boys_first,
            "quota": "Convenor",
            "year": year,
        })
    
    # Extract Girls data  
    girls_first = clean_rank(row, EWS_COL_GIRLS_FIRST, EWS_COL_GIRLS_LAST - 1)
    girls_last = clean_rank(row, EWS_COL_GIRLS_LAST, len(row))
    
    if girls_first:
        records.append({
            "branch": branch,
            "caste": "EWS",
            "gender": "Girls",
            "first_rank": girls_first,
            "last_rank": girls_last if girls_last else girls_first,
            "quota": "Convenor",
            "year": year,
        })

print(f"\nExtracted {len(records)} EWS records")
print(f"\nSample records (first 10):")
for rec in records[:10]:
    print(f"  {rec['branch']:12} | {rec['caste']:8} | {rec['gender']:5} | Rank: {rec['first_rank']:6}")

# Upload to Firestore
print(f"\nUploading {len(records)} records to Firestore...")
db = get_db()
batch = db.batch()

for rec in records:
    doc_id = f"{rec['year']}_{rec['branch']}_{rec['caste']}_{rec['gender']}_{rec['quota']}"
    doc_ref = db.collection(COLLECTION).document(doc_id)
    batch.set(doc_ref, rec, merge=True)

batch.commit()
print(f"✅ Uploaded {len(records)} EWS records to 'cutoffs' collection")
