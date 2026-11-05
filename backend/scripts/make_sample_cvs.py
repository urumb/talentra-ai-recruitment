"""Generate synthetic sample CVs into ../sample_cvs (no real people; emails use example.com, phones are 90000001xx)."""
import io
from pathlib import Path
import fitz
from docx import Document
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[2] / 'sample_cvs'; OUT.mkdir(exist_ok=True)


def docx_plain(name, lines):
    d = Document(); [d.add_paragraph(x) for x in lines]; d.save(OUT / name)


def docx_table(name, title, rows):
    d = Document(); d.add_heading(title, 1); t = d.add_table(rows=0, cols=2)
    for k, v in rows:
        c = t.add_row().cells; c[0].text, c[1].text = k, v
    d.save(OUT / name)


def pdf_text(name, lines):
    doc = fitz.open(); page = doc.new_page(); page.insert_text((60, 70), '\n'.join(lines), fontsize=11); doc.save(OUT / name, deflate=True, garbage=4)


def pdf_scan(name, lines):
    """Image-only PDF (no text layer): exercises the OCR path."""
    try: font = ImageFont.load_default(size=26)
    except TypeError: font = ImageFont.load_default()
    img = Image.new('L', (1240, 900), 255); dr = ImageDraw.Draw(img)
    for i, l in enumerate(lines): dr.text((60, 60 + i * 44), l, fill='black', font=font)
    buf = io.BytesIO(); img.save(buf, 'PNG', optimize=True); doc = fitz.open(); page = doc.new_page(width=620, height=450); page.insert_image(page.rect, stream=buf.getvalue()); doc.save(OUT / name, deflate=True, garbage=4)


docx_plain('ritika_bansal_duplicate.docx', ['Ritika Bansal', 'ritika.bansal@example.com', 'Senior Java Developer. 6.5 years of experience. Java, Spring Boot, microservices.'])  # same email as the seeded candidate -> duplicate review
docx_table('vikram_sethi_table_cv.docx', 'Vikram Sethi', [('Email', 'vikram.sethi@example.com'), ('Phone', '9000000104'), ('Experience', '7 years of experience in Java backend development'), ('Skills', 'Java, Spring Boot, Microservices, AWS, Docker'), ('Location', 'Noida'), ('Expected CTC', '27 LPA'), ('Notice period', '30 days')])
pdf_text('neha_kapoor.pdf', ['Neha Kapoor', 'neha.kapoor@example.com  |  +91 9000000105', 'Java Developer - Gurugram', '5 years of experience designing Spring Boot services', 'Skills: Java, Spring Boot, REST APIs, Hibernate', 'Expected CTC: 20 LPA', 'Notice period: 45 days'])
pdf_text('karan_malhotra.pdf', ['Karan Malhotra', 'karan.m@example.com', 'Frontend engineer. 4 years of experience with React and TypeScript.', 'Skills: React, TypeScript, JavaScript', 'Immediate joiner'])  # not a Java fit: stays visible, scores low
pdf_text('sana_iqbal_kyc.pdf', ['Sana Iqbal', 'sana.iqbal@example.com | 9000000106', 'KYC Analyst, 2.5 years of experience', 'Skills: KYC, AML checks, Excel, Reporting', 'Notice period: 15 days'])
pdf_scan('scanned_amit_verma.pdf', ['Amit Verma', 'amit.verma@example.com  9000000107', 'Senior Java Developer', '8 years of experience', 'Skills: Java, Spring Boot, Microservices', 'Expected CTC: 30 LPA', 'Notice period: 30 days'])
(OUT / 'corrupt_example.pdf').write_bytes(b'%PDF-1.4 this file is intentionally corrupt to show per-document failure handling')
(OUT / 'sample_jd.txt').write_text('Senior Java Developer, 5-8 years, Spring Boot, Noida, notice up to 60 days.\nMust have: Java, Spring Boot, microservices. Budget up to 28 LPA.\n', encoding='utf-8')
print(sorted(p.name for p in OUT.iterdir()))
