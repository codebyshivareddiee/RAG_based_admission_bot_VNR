import pdfplumber

pdf = pdfplumber.open('docs/First-and-Last-Ranks-2023-Eamcet.pdf')
print(f'Total pages in 2023 PDF: {len(pdf.pages)}')

for i in range(min(4, len(pdf.pages))):
    print(f'\n{"="*70}')
    print(f'PAGE {i+1} (first 800 chars)')
    print(f'{"="*70}')
    print(pdf.pages[i].extract_text()[:800])
