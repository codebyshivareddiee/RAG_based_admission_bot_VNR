"""
Custom extractor for VNRVJIET EAPCET cutoff PDF.

Page 1 table format (Convenor quota, regular categories):
  Branch | OC Boys(First/Last) | OC Girls(First/Last) | BC-A Boys(F/L) | ...

Page 2 table format:
  Branch | BC-D Boys(F/L) | BC-D Girls(F/L) | ... | ST Boys(F/L) | ST Girls(F/L)

Pages 3-4 table format (special categories: SPORTS, CAP, NCC, OTHERS):
  Each cell combines rank + caste + optional PH code, e.g. "122215-OC_PHO_GEN"
  PH codes: PHV (Visual), PHH (Hearing), PHO (Orthopedic), PHM (Mental), PHA (Autism)
  Page 3 has 17 cols (First/Last split, Last always empty)
  Page 4 has 9 cols (no First/Last split), no header rows

Page 5 table format:
  Branch | EWS Boys(First/Last) | EWS Girls(First/Last)

Usage:
    python -m app.data.ingest_eapcet --pdf "docs/2025-TGEAPCET-Cutoff-Ranks.pdf" --dry-run
    python -m app.data.ingest_eapcet --pdf "docs/2025-TGEAPCET-Cutoff-Ranks.pdf" --clear
    python -m app.data.ingest_eapcet --pdf "docs/2025-TGEAPCET-Cutoff-Ranks.pdf" --page 3 --dry-run
    python -m app.data.ingest_eapcet --pdf "docs/2025-TGEAPCET-Cutoff-Ranks.pdf" --page all --clear
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from app.data.init_db import get_db, COLLECTION


# Column layout for page 1 (0-indexed):
PAGE1_COLUMN_MAP = [
    (2,  "OC",   "Boys"),
    (4,  "OC",   "Girls"),
    (6,  "BC-A", "Boys"),
    (8,  "BC-A", "Girls"),
    (10, "BC-B", "Boys"),
    (12, "BC-B", "Girls"),
    (14, "BC-C", "Boys"),
    (16, "BC-C", "Girls"),
]

# Column layout for page 2 (0-indexed):
# Branch | BC-D Boys(F/L) | BC-D Girls(F/L) | BC-E Boys(F/L) | BC-E Girls(F/L)
#        | SC-I Boys(F/L) | SC-I Girls(F/L) | SC-II Boys(F/L) | SC-II Girls(F/L)
#        | SC-III Boys(F/L) | SC-III Girls(F/L) | ST Boys(F/L) | ST Girls(F/L)
PAGE2_COLUMN_MAP = [
    (2,  "BC-D",   "Boys"),
    (4,  "BC-D",   "Girls"),
    (6,  "BC-E",   "Boys"),
    (8,  "BC-E",   "Girls"),
    (10, "SC-I",   "Boys"),
    (12, "SC-I",   "Girls"),
    (14, "SC-II",  "Boys"),
    (16, "SC-II",  "Girls"),
    (18, "SC-III", "Boys"),
    (20, "SC-III", "Girls"),
    (22, "ST",     "Boys"),
    (24, "ST",     "Girls"),
]

# Column layout for page 5 (0-indexed):
# Branch | EWS Boys(First/Last) | EWS Girls(First/Last)
PAGE5_COLUMN_MAP = [
    (2,  "EWS", "Boys"),
    (4,  "EWS", "Girls"),
]

# Map 0-indexed page numbers to their column maps (regular pages)
PAGE_COLUMN_MAPS = {
    0: PAGE1_COLUMN_MAP,
    1: PAGE2_COLUMN_MAP,
    4: PAGE5_COLUMN_MAP,
}

# ── Pages 3-4: Special-category quota columns ──
# PH (Physically Handicapped) disability codes in EAPCET data
PH_CODES = {"PHV", "PHH", "PHO", "PHM", "PHA"}
PH_LABELS = {
    "PHV": "Visually Impaired",
    "PHH": "Hearing Impaired",
    "PHO": "Orthopedically Handicapped",
    "PHM": "Mental Disability",
    "PHA": "Autism",
}

# Page 3: 17 cols = Branch + 4 quotas × 2 genders × 2 (First/Last)
#   Data is in the "First" columns (odd indices); "Last" is always empty.
PAGE3_SPECIAL_MAP = [
    (1,  "SPORTS", "Boys"),
    (3,  "SPORTS", "Girls"),
    (5,  "CAP",    "Boys"),
    (7,  "CAP",    "Girls"),
    (9,  "NCC",    "Boys"),
    (11, "NCC",    "Girls"),
    (13, "OTHERS", "Boys"),
    (15, "OTHERS", "Girls"),
]

# Page 4: 9 cols = Branch + 4 quotas × 2 genders (no First/Last split)
PAGE4_SPECIAL_MAP = [
    (1, "SPORTS", "Boys"),
    (2, "SPORTS", "Girls"),
    (3, "CAP",    "Boys"),
    (4, "CAP",    "Girls"),
    (5, "NCC",    "Boys"),
    (6, "NCC",    "Girls"),
    (7, "OTHERS", "Boys"),
    (8, "OTHERS", "Girls"),
]


def _parse_rank(value: str) -> int | None:
    """Extract integer rank. Returns None for '-', '--', empty."""
    if not value:
        return None
    v = str(value).strip()
    if v in ("-", "--", "—", ""):
        return None
    cleaned = re.sub(r"[,\s]", "", v)
    cleaned = re.sub(r"\.0+$", "", cleaned)
    match = re.search(r"\d+", cleaned)
    return int(match.group()) if match else None


def _parse_cell_entry(cell_value: str) -> dict | None:
    """
    Parse a combined rank-category cell from pages 3-4.

    Examples:
      "145789-SC-III"        → rank=145789, category="SC-III", ph_type=None
      "122215-OC_PHO_GEN"   → rank=122215, category="OC",     ph_type="PHO"
      "3329-BC_A_PHH"       → rank=3329,   category="BC-A",   ph_type="PHH"
      "37456 BC-B"           → rank=37456,  category="BC-B",   ph_type=None
      "9171 - BC-B"          → rank=9171,   category="BC-B",   ph_type=None

    Returns dict with keys: rank, category, ph_type (or None).
    """
    text = str(cell_value).strip()
    if not text:
        return None

    # Extract leading digits as rank, rest is category info
    match = re.match(r"(\d+)[\s\-]+(.+)", text)
    if not match:
        return None

    rank = int(match.group(1))
    rest = match.group(2).strip()

    # Remove trailing _GEN qualifier (general PH quota marker)
    rest = re.sub(r"_GEN$", "", rest)

    # Extract PH code if present  (_PHO, _PHV, _PHH, _PHM, _PHA)
    ph_type = None
    for ph in PH_CODES:
        pattern = f"_{ph}"
        if pattern in rest:
            ph_type = ph
            rest = rest.replace(pattern, "")
            break

    # Normalise category: BC_A → BC-A, SC_III → SC-III, SC_II → SC-II
    rest = rest.strip().strip("-").strip("_").strip()
    rest = re.sub(r"^(BC|SC)_", r"\1-", rest)

    if not rest:
        return None

    return {"rank": rank, "category": rest, "ph_type": ph_type}


def extract_special_pages(
    pdf_path: str | Path, year: int = 2025
) -> list[dict]:
    """
    Extract cutoff records from pages 3-4 (special categories).

    These pages cover SPORTS, CAP, NCC, OTHERS quotas.
    Each cell contains combined "rank-category" strings.
    Multiple entries per branch are spread across continuation rows.
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
        # ── Page 3 (0-indexed: 2) ──
        if len(pdf.pages) > 2:
            page3 = pdf.pages[2]
            t3 = page3.extract_tables()
            if t3:
                table = t3[0]
                print(f"  Page 3: {len(table)} rows × {len(table[0])} cols")
                records.extend(
                    _extract_special_table(table, PAGE3_SPECIAL_MAP, year, skip_header=3)
                )

        # ── Page 4 (0-indexed: 3) ──
        if len(pdf.pages) > 3:
            page4 = pdf.pages[3]
            t4 = page4.extract_tables()
            if t4:
                table = t4[0]
                print(f"  Page 4: {len(table)} rows × {len(table[0])} cols")
                records.extend(
                    _extract_special_table(table, PAGE4_SPECIAL_MAP, year, skip_header=0)
                )

    return records


def _extract_special_table(
    table: list[list],
    col_map: list[tuple],
    year: int,
    skip_header: int = 0,
) -> list[dict]:
    """
    Walk rows of a special-category table, grouping continuation rows
    (where branch column is None) with their parent branch row.
    """
    records: list[dict] = []
    current_branch: str | None = None

    for row in table[skip_header:]:
        cells = [str(c).strip() if c else "" for c in row]

        # Determine the branch for this row
        branch_cell = cells[0].strip() if cells[0] else ""
        if branch_cell:
            # New branch row
            current_branch = branch_cell.replace("\n", "").replace("\r", "").strip()
        # else: continuation row — keep current_branch

        if not current_branch:
            continue

        # Process each mapped column
        for col_idx, quota, gender in col_map:
            if col_idx >= len(cells):
                continue
            cell_val = cells[col_idx]
            if not cell_val:
                continue

            parsed = _parse_cell_entry(cell_val)
            if parsed is None:
                continue

            records.append({
                "branch": current_branch,
                "category": parsed["category"],
                "gender": gender,
                "cutoff_rank": parsed["rank"],
                "year": year,
                "round": 1,
                "quota": quota,
                "ph_type": parsed["ph_type"],  # None or PHV/PHH/PHO/PHM/PHA
            })

    return records


def extract_page(pdf_path: str | Path, page_num: int = 0, year: int = 2025) -> list[dict]:
    """Extract cutoff records from a page of the EAPCET cutoff PDF.
    
    page_num: 0 for page 1, 1 for page 2 (0-indexed).
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("Install pdfplumber:  pip install pdfplumber")

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    column_map = PAGE_COLUMN_MAPS.get(page_num)
    if column_map is None:
        print(f"\u274c  No column map defined for page {page_num + 1}")
        return []
    page_label = page_num + 1

    records: list[dict] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        if page_num >= len(pdf.pages):
            print(f"❌  PDF has only {len(pdf.pages)} page(s), cannot read page {page_label}")
            return []

        page = pdf.pages[page_num]
        tables = page.extract_tables()

        if not tables:
            print(f"❌  No tables found on page {page_label}")
            return []

        table = tables[0]  # Main table
        print(f"  Page {page_label}: Table has {len(table)} rows × {len(table[0])} columns")

        # Skip header rows (first 3 rows typically: title, category, gender, First/Last)
        # Find the first data row by looking for a branch name
        data_start = 0
        for i, row in enumerate(table):
            cell0 = str(row[0]).strip() if row[0] else ""
            # Data rows have branch names like AID, CSE, ECE, etc.
            if cell0 and cell0 not in ("Branch", "branch", "") and not cell0.startswith("First"):
                # Check if it looks like a branch (not a header word)
                if any(c.isalpha() for c in cell0) and cell0.upper() not in ("BOYS", "GIRLS", "FIRST", "LAST", "OC", "BC-A", "BC-B", "BC-C", "BC-D", "BC-E", "SC-I", "SC-II", "SC-III", "SC", "ST"):
                    data_start = i
                    break

        print(f"  Data starts at row {data_start}")

        for row in table[data_start:]:
            cells = [str(c).strip() if c else "" for c in row]

            branch = cells[0].strip() if cells[0] else ""
            if not branch or branch.lower() in ("branch", ""):
                continue

            # Normalize branch names with line breaks (e.g., "CSE-\nCSC" → "CSE-CSC")
            branch = branch.replace("\n", "").replace("\r", "").strip()

            for last_col, category, gender in column_map:
                if last_col >= len(cells):
                    continue

                rank = _parse_rank(cells[last_col])
                # If Last rank is "--" / "-", fall back to First rank
                # (means only one student admitted, so First = Last)
                if rank is None:
                    first_col = last_col - 1
                    if first_col >= 0:
                        rank = _parse_rank(cells[first_col])
                if rank is None:
                    continue

                records.append({
                    "branch": branch,
                    "category": category,
                    "gender": gender,
                    "cutoff_rank": rank,
                    "year": year,
                    "round": 1,
                    "quota": "Convenor",
                })

    return records


def _doc_id(row: dict) -> str:
    base = (
        f"{row['branch']}_{row['category']}_{row['year']}_"
        f"R{row['round']}_{row['gender']}_{row['quota']}"
    )
    if row.get("ph_type"):
        base += f"_{row['ph_type']}"
    return base.replace(" ", "-").replace("(", "").replace(")", "")


def upload_to_firestore(records: list[dict], clear_existing: bool = False) -> int:
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
    parser = argparse.ArgumentParser(description="Ingest EAPCET cutoff data into Firestore")
    parser.add_argument("--pdf", type=str, required=True, help="Path to the cutoff PDF")
    parser.add_argument("--year", type=int, default=2025, help="Admission year")
    parser.add_argument("--page", type=str, default="all",
                        help="'1','2','3','4','5','special' (3+4), or 'all' (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--clear", action="store_true", help="Clear existing records first")
    args = parser.parse_args()

    all_records = []

    # Determine which pages to extract
    page_arg = args.page.lower().strip()

    # Regular pages (1, 2, 5) - use existing extract_page()
    regular_pages = []
    do_special = False

    if page_arg in ("1", "page1"):
        regular_pages = [0]
    elif page_arg in ("2", "page2"):
        regular_pages = [1]
    elif page_arg in ("5", "page5"):
        regular_pages = [4]
    elif page_arg in ("3", "page3", "4", "page4", "special"):
        do_special = True
    elif page_arg in ("all", "both"):
        regular_pages = [0, 1, 4]
        do_special = True
    else:
        regular_pages = [0, 1, 4]
        do_special = True

    for pg in regular_pages:
        print(f"\n📄  Reading page {pg + 1} of: {args.pdf}")
        records = extract_page(args.pdf, page_num=pg, year=args.year)
        all_records.extend(records)

    if do_special:
        print(f"\n📄  Reading pages 3-4 (special categories) of: {args.pdf}")
        records = extract_special_pages(args.pdf, year=args.year)
        all_records.extend(records)

    if not all_records:
        print("\n❌  No records extracted.")
        return

    print(f"\n📊  Extracted {len(all_records)} records total. Sample:")
    for r in all_records[:8]:
        ph = f" PH:{r['ph_type']}" if r.get("ph_type") else ""
        print(
            f"  {r['branch']:12s} | {r['category']:6s} | {r['gender']:5s} "
            f"| Rank: {r['cutoff_rank']:>6d} | {r['quota']}{ph}"
        )
    if len(all_records) > 8:
        print(f"  ... and {len(all_records) - 8} more")

    if args.dry_run:
        print("\n🔍  Dry run — all extracted records:")
        for i, r in enumerate(all_records, 1):
            ph = f" PH:{r['ph_type']}" if r.get("ph_type") else ""
            print(
                f"  {i:3d}. {r['branch']:12s} | {r['category']:6s} | {r['gender']:5s} "
                f"| Rank: {r['cutoff_rank']:>6d} | {r['quota']}{ph}"
            )
        return

    upload_to_firestore(all_records, clear_existing=args.clear)


if __name__ == "__main__":
    main()
