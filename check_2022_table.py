import pdfplumber

pdf = pdfplumber.open('docs/First-and-Last-Ranks-2022.pdf')
page1 = pdf.pages[0]

print("PAGE 1 TABLE EXTRACTION:")
table = page1.extract_table()
print(f"Table: {len(table) if table else 0} rows × {len(table[0]) if table and table else 0} columns\n")

if table:
    for i, row in enumerate(table[:15]):
        print(f"Row {i}: {row}")
else:
    print("No table extracted!")
    
print("\n" + "="*70)
print("Trying with different table settings...")
table2 = page1.extract_table({
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
})
if table2:
    print(f"Table2: {len(table2)} rows × {len(table2[0]) if table2 else 0} columns\n")
    for i, row in enumerate(table2[:15]):
        print(f"Row {i}: {row}")
