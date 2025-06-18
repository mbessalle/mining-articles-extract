import os
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from tqdm import tqdm

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = SCRIPT_DIR / "projects"

def extract_text_and_tables(pdf_path):
    final_text = ""

    # Use pdfplumber for text + tables
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            tables = page.extract_tables()

            # If there's text, add it
            if page_text.strip():
                final_text += page_text.strip() + "\n\n"

            # If there are tables, format them
            for table in tables:
                final_text += "TABLE:\n"
                for row in table:
                    row_text = " | ".join(cell.strip() if cell else "" for cell in row)
                    final_text += row_text + "\n"
                final_text += "\n"

            # Fallback: if no text and no tables
            if not page_text.strip() and not tables:
                image = convert_from_path(pdf_path, first_page=i+1, last_page=i+1)[0]
                ocr_text = pytesseract.image_to_string(image)
                final_text += "[OCR]\n" + ocr_text.strip() + "\n\n"

    return final_text

pdf_paths: list[Path] = list(PROJECTS_DIR.rglob("*.pdf"))

for pdf_path in tqdm(pdf_paths, desc="Parsing PDFs"):
    try:
        text = extract_text_and_tables(str(pdf_path))
        txt_path = pdf_path.with_name(pdf_path.stem + "_pdf.txt")
        txt_path.write_text(text, encoding="utf-8")
    except Exception as e:
        print(f"Failed to process {pdf_path}: {e}")
