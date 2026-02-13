import pdfplumber

pdf = pdfplumber.open('docs/First-and-Last-Ranks-2023-Eamcet.pdf')
page = pdf.pages[3]  # Page 4 (0-indexed)

table = page.extract_table()
print(f"Page 4: {len(table)} rows × {len(table[0]) if table else 0} columns\n")

# Print first 10 rows to see structure
for i, row in enumerate(table[:10]):
    print(f"Row {i}: {row}")

# Check if there are EWS headers
print("\n" + "="*70)
print("Looking for header structure...")
for i, row in enumerate(table[:5]):
    non_empty = [cell for cell in row if cell and cell.strip()]
    if non_empty:
        print(f"Row {i}: {' | '.join(non_empty)}")
