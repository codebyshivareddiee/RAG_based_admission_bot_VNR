import pdfplumber

pdf = pdfplumber.open('docs/EAPCET_First-and-Last-Ranks-2024.pdf')
print(f'Total pages: {len(pdf.pages)}')

# Check page 3 (index 2)
page3 = pdf.pages[2]
print(f'\n=== PAGE 3 TEXT (first 1500 chars) ===')
print(page3.extract_text()[:1500])

# Check page 4 if it exists
if len(pdf.pages) > 3:
    page4 = pdf.pages[3]
    print(f'\n=== PAGE 4 TEXT (first 1500 chars) ===')
    print(page4.extract_text()[:1500])
