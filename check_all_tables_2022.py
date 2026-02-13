import pdfplumber

pdf = pdfplumber.open('docs/First-and-Last-Ranks-2022.pdf')
page1 = pdf.pages[0]

print("ALL TABLES ON PAGE 1:")
tables = page1.extract_tables()
print(f"Found {len(tables)} table(s)\n")

for i, table in enumerate(tables):
    print(f"TABLE {i}: {len(table)} rows × {len(table[0]) if table else 0} columns")
    if table:
        print(f"First 3 rows:")
        for j, row in enumerate(table[:3]):
            print(f"  Row {j}: {row}")
    print()
