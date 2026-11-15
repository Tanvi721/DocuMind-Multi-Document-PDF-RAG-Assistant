"""Create two small, fictional business PDFs for an immediate local demo."""
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from pathlib import Path

OUT = Path("data/sample_pdfs")
OUT.mkdir(parents=True, exist_ok=True)

reports = {
    "Northstar_Annual_Report_2024.pdf": [
        ("Northstar Technologies — Annual Report 2024",
         "Fictional sample document for testing the RAG assignment."),
        ("Business Overview",
         "Northstar Technologies provides cloud software and data services to small and medium businesses. "
         "In fiscal year 2024, the company served 18,400 active customers across 12 countries."),
        ("Financial Highlights",
         "Revenue for 2024 was INR ₹ 248 crore, compared with INR 210 crore in 2023. "
         "Operating expenses were INR 176 crore. Net profit was INR 32 crore. "
         "The company invested INR 24 crore in research and development."),
        ("People and Operations",
         "The company had 1,250 employees at year end. Customer support operated from Pune, Bengaluru and Singapore. "
         "The annual customer retention rate was 91 percent.")
    ],
    "GreenField_Operations_Report_2024.pdf": [
        ("GreenField Foods — Operations Report 2024",
         "Fictional sample document for testing multi-document retrieval."),
        ("Production",
         "GreenField Foods operates three processing facilities in Maharashtra. "
         "Total packaged output in 2024 was 46,000 metric tonnes."),
        ("Sustainability",
         "The company reduced water use per tonne by 14 percent compared with 2023. "
         "Renewable electricity supplied 38 percent of total electricity consumption."),
        ("Distribution and Risk",
         "Products were distributed through 620 retail partners. The main operational risks were seasonal raw material "
         "shortages, cold-chain interruptions and changes in transport costs.")
    ]
}
for filename, sections in reports.items():
    path = OUT / filename
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    for title, body in sections:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(55, height - 75, title)
        c.setFont("Helvetica", 11)
        y = height - 115
        words = body.split()
        line = ""
        for word in words:
            if len(line + " " + word) > 88:
                c.drawString(55, y, line)
                y -= 18
                line = word
            else:
                line = (line + " " + word).strip()
        if line:
            c.drawString(55, y, line)
        c.showPage()
    c.save()
print("Created demo PDFs in data/sample_pdfs/")
