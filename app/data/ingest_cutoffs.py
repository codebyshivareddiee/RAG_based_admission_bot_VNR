"""
Ingest cutoff data from a PDF (with tables) into Firebase Firestore.

The script:
  1. Extracts all tables from the PDF using pdfplumber
  2. Auto-maps column headers to Firestore fields
  3. Inserts structured records into the 'cutoffs' collection

Usage:
    python -m app.data.ingest_cutoffs --pdf "docs/cutoffs.pdf" --year 2025

    Optional flags:
      --year       Default year if not in the table (default: 2025)
      --round      Default round if not in the table (default: 1)
      --quota      Default quota if not in the table (default: Convenor)
      --gender     Default gender if not in the table (default: Any)
      --dry-run    Preview extracted records without writing to Firestore
      --clear      Clear existing cutoff records before inserting
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from app.data.init_db import get_db, COLLECTION


# ── Column header mapping ────────────────────────────────────
# Maps common PDF column header variations → our Firestore field name.
# Case-insensitive matching.
HEADER_MAP: dict[str, list[str]] = {
    "branch": [
        "branch", "branch name", "programme", "program", "course",
        "department", "dept", "branch/course", "branch / course",
        "specialization", "discipline",
    ],
    "category": [
        "category", "caste", "reservation", "reservation category",
        "cat", "caste category", "social category",
    ],
    "cutoff_rank": [
        "cutoff rank", "cutoff_rank", "rank", "closing rank",
        "last rank", "eamcet rank", "final rank", "closing",
        "cut off rank", "cut-off rank", "cutoff", "cut off",
        "last rank allotted", "closing rank allotted",
    ],
    "year": [
        "year", "admission year", "academic year", "session",
    ],
    "round": [
        "round", "phase", "round no", "counselling round",
        "round number", "allotment round",
    ],
    "gender": [
        "gender", "sex", "male/female", "gender category",
    ],
    "quota": [
        "quota", "seat type", "seat quota", "type",
        "convenor/management", "seat category",
    ],
}


def _normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).strip().lower())


def _map_header(header: str) -> str | None:
    """Map a PDF column header to a Firestore field name."""
    h = _normalize(header)
    for field, variants in HEADER_MAP.items():
        for v in variants:
            if h == v or h.startswith(v) or v in h:
                return field
    return None


def _clean_rank(value: str) -> int | None:
    """Extract integer rank from a cell value like '3,500' or '3500.0'."""
    if not value:
        return None
    # Remove commas, spaces, trailing .0
    cleaned = re.sub(r"[,\s]", "", str(value).strip())
    cleaned = re.sub(r"\.0+$", "", cleaned)
    # Extract first integer
    match = re.search(r"\d+", cleaned)
    return int(match.group()) if match else None


def _clean_round(value: str) -> int:
    """Extract round number."""
    match = re.search(r"\d+", str(value).strip())
    return int(match.group()) if match else 1


def _clean_year(value: str) -> int | None:
    """Extract 4-digit year."""
    match = re.search(r"20\d{2}", str(value).strip())
    return int(match.group()) if match else None


def _clean_branch(value: str) -> str:
    """Normalize branch name."""
    v = str(value).strip()
    # Common normalizations
    mapping = {
        "computer science and engineering": "CSE",
        "computer science & engineering": "CSE",
        "electronics and communication engineering": "ECE",
        "electronics & communication engineering": "ECE",
        "electrical and electronics engineering": "EEE",
        "electrical & electronics engineering": "EEE",
        "information technology": "IT",
        "mechanical engineering": "MECH",
        "civil engineering": "CIVIL",
    }
    lower = v.lower()
    for full, short in mapping.items():
        if full in lower:
            return short

    return v


def extract_cutoffs_from_pdf(
    pdf_path: str | Path,
    default_year: int = 2025,
    default_round: int = 1,
    default_quota: str = "Convenor",
    default_gender: str = "Any",
) -> list[dict]:
    """
    Extract cutoff records from a PDF with tables.

    Returns a list of dicts with keys:
        branch, category, cutoff_rank, year, round, gender, quota
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("Install pdfplumber:  pip install pdfplumber")

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    records: list[dict] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            if not tables:
                print(f"  Page {page_num}: no tables found")
                continue

            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue

                # Map headers
                raw_headers = [str(c).strip() if c else "" for c in table[0]]
                field_map: dict[int, str] = {}  # col_index → field_name

                print(f"\n  Page {page_num}, Table {table_idx + 1}")
                print(f"  Detected columns: {raw_headers}")

                for col_idx, header in enumerate(raw_headers):
                    field = _map_header(header)
                    if field:
                        field_map[col_idx] = field
                        print(f"    '{header}' → {field}")
                    else:
                        print(f"    '{header}' → (skipped)")

                if "cutoff_rank" not in field_map.values():
                    print(f"  ⚠️  No cutoff_rank column found, skipping table")
                    continue

                # Parse rows
                for row_idx, row in enumerate(table[1:], 2):
                    cells = [str(c).strip() if c else "" for c in row]

                    # Skip empty rows
                    if not any(cells):
                        continue

                    record: dict = {
                        "year": default_year,
                        "round": default_round,
                        "quota": default_quota,
                        "gender": default_gender,
                    }

                    for col_idx, field in field_map.items():
                        if col_idx >= len(cells):
                            continue
                        val = cells[col_idx]
                        if not val or val.lower() in ("none", "nan", "-", ""):
                            continue

                        if field == "cutoff_rank":
                            rank = _clean_rank(val)
                            if rank:
                                record["cutoff_rank"] = rank
                        elif field == "branch":
                            record["branch"] = _clean_branch(val)
                        elif field == "category":
                            record["category"] = val.upper().strip()
                        elif field == "year":
                            y = _clean_year(val)
                            if y:
                                record["year"] = y
                        elif field == "round":
                            record["round"] = _clean_round(val)
                        elif field == "gender":
                            record["gender"] = val.strip()
                        elif field == "quota":
                            record["quota"] = val.strip()

                    # Only include if we have at least branch + cutoff_rank
                    if "branch" in record and "cutoff_rank" in record:
                        records.append(record)

    return records


def _doc_id(row: dict) -> str:
    """Generate a deterministic document ID for deduplication."""
    return (
        f"{row.get('branch', 'UNK')}_{row.get('category', 'UNK')}_"
        f"{row.get('year', 0)}_R{row.get('round', 1)}_"
        f"{row.get('gender', 'Any')}_{row.get('quota', 'Convenor')}"
    ).replace(" ", "-").replace("(", "").replace(")", "")


def upload_to_firestore(records: list[dict], clear_existing: bool = False) -> int:
    """Upload cutoff records to Firestore. Returns count uploaded."""
    db = get_db()

    if clear_existing:
        print("\n🗑️  Clearing existing cutoff records...")
        docs = db.collection(COLLECTION).stream()
        batch = db.batch()
        del_count = 0
        for doc in docs:
            batch.delete(doc.reference)
            del_count += 1
            if del_count % 450 == 0:
                batch.commit()
                batch = db.batch()
        batch.commit()
        print(f"  Deleted {del_count} existing records")

    print(f"\n📤  Uploading {len(records)} records to Firestore...")
    batch = db.batch()
    count = 0

    for row in records:
        doc_ref = db.collection(COLLECTION).document(_doc_id(row))
        batch.set(doc_ref, row, merge=True)
        count += 1

        if count % 450 == 0:
            batch.commit()
            batch = db.batch()

    batch.commit()
    print(f"✅  Uploaded {count} cutoff records to '{COLLECTION}' collection")
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Ingest cutoff data from a PDF into Firebase Firestore"
    )
    parser.add_argument("--pdf", type=str, required=True, help="Path to the cutoff PDF")
    parser.add_argument("--year", type=int, default=2025, help="Default year (if not in table)")
    parser.add_argument("--round", type=int, default=1, help="Default round (if not in table)")
    parser.add_argument("--quota", type=str, default="Convenor", help="Default quota")
    parser.add_argument("--gender", type=str, default="Any", help="Default gender")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Firestore")
    parser.add_argument("--clear", action="store_true", help="Clear existing records before inserting")
    args = parser.parse_args()

    print(f"📄  Reading PDF: {args.pdf}")
    records = extract_cutoffs_from_pdf(
        pdf_path=args.pdf,
        default_year=args.year,
        default_round=args.round,
        default_quota=args.quota,
        default_gender=args.gender,
    )

    if not records:
        print("\n❌  No cutoff records extracted. Check that the PDF has tables with 'Branch' and 'Rank' columns.")
        return

    print(f"\n📊  Extracted {len(records)} records. Sample:")
    for r in records[:5]:
        print(f"  {r}")
    if len(records) > 5:
        print(f"  ... and {len(records) - 5} more")

    if args.dry_run:
        print("\n🔍  Dry run — no data written to Firestore.")
        print("\nAll extracted records:")
        for i, r in enumerate(records, 1):
            print(f"  {i}. {r}")
        return

    upload_to_firestore(records, clear_existing=args.clear)


if __name__ == "__main__":
    main()
