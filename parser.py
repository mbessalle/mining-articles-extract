import os
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from tqdm import tqdm

root_dir = "/home/laptop/projects/celis/australia/projects"

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

pdf_paths = []
for dirpath, _, filenames in os.walk(root_dir):
    for filename in filenames:
        if filename.lower().endswith(".pdf"):
            pdf_paths.append(os.path.join(dirpath, filename))

for pdf_path in tqdm(pdf_paths, desc="Processing PDFs"):
    try:
        text = extract_text_and_tables(pdf_path)
        txt_filename = os.path.splitext(os.path.basename(pdf_path))[0] + ".txt"
        txt_path = os.path.join(os.path.dirname(pdf_path), txt_filename)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        print(f"Failed to process {pdf_path}: {e}")
