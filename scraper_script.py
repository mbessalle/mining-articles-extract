#!/usr/bin/env python3
"""scraper_script.py

Utility to test scraping of the first three article URLs from `USA-projects.json`.
For each article it:
1. Downloads the article JSON from the `/api/article/{id}` endpoint.
2. Uses Playwright to open the article page and determines whether the page contains
   an iframe that embeds a PDF (identified by an `iframe` whose `src` contains
   either `.pdf` or `headline.aspx?id=`).
3. If a PDF embed is found, the PDF file is downloaded.
4. The JSON file (and PDF if present) are saved to
   `/home/laptop/projects/celis/usa/projects`.

The script is intentionally limited to the first three articles for testing
purposes, as requested by the user.

Usage (after Playwright and its browsers are installed):
    python3 scraper_script.py

Playwright installation helper (run once):
    pip install playwright requests
    playwright install chromium
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional

import requests
from playwright.async_api import async_playwright

# ------------- Configuration ------------- #
ROOT_DIR = Path("/home/laptop/projects/celis/usa")
PROJECTS_DIR = ROOT_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

JSON_PATH = ROOT_DIR / "USA-projects.json"
# Process all articles
MAX_ARTICLES = None

# ----------------------------------------- #

ARTICLE_ID_RE = re.compile(r"/article/(\d+)")

# Characters not allowed in filenames across common OSes
INVALID_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")

def safe_filename(name: str) -> str:
    """Return a filesystem-safe filename stem (no extension)."""
    cleaned = INVALID_FILENAME_CHARS.sub("_", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "unnamed"


def extract_article_id(url: str) -> Optional[str]:
    """Return the numeric article ID from an article URL or None if not found."""
    m = ARTICLE_ID_RE.search(url)
    return m.group(1) if m else None


async def page_has_pdf(page) -> bool:
    """Return True if the Article page has a PDF iframe embed."""
    # Wait for network to settle a bit
    await page.wait_for_load_state("networkidle", timeout=15_000)
    html = await page.content()
    # Quick heuristic checks
    if ".pdf" in html or "headline.aspx?id=" in html:
        # Do extra check for iframe element whose src contains PDF or headline.aspx
        iframes = await page.query_selector_all("iframe")
        for iframe in iframes:
            src = await iframe.get_attribute("src")
            if src and (src.endswith(".pdf") or "headline.aspx?id=" in src):
                return True
    return False


async def download_pdf(page, article_url: str, save_dir: Path, article_id: str) -> Optional[Path]:
    """If a PDF iframe is found, download the PDF and return local Path."""
    # Find iframe src
    iframe_el = await page.query_selector('iframe[src*=".pdf"], iframe[src*="headline.aspx?id="]')
    if not iframe_el:
        return None
    src = await iframe_el.get_attribute("src")
    if not src:
        return None
    # Handle relative path
    if src.startswith("/"):
        src = "https://app.mininghub.com" + src
    # Some headline.aspx endpoints render PDF inline; still download.
    # Derive a filename from article ID or from src
    filename = f"{article_id}.pdf"
    pdf_path = save_dir / filename
    try:
        print(f"  → Downloading PDF: {src}")
        r = requests.get(src, timeout=30)
        r.raise_for_status()
        with open(pdf_path, "wb") as f:
            f.write(r.content)
        print(f"  ✔ Saved PDF to {pdf_path}")
        return pdf_path
    except Exception as e:
        print(f"  ✖ Failed to download PDF {src}: {e}")
        return None


MAX_RETRIES = 3  # retries for page navigation/download


async def process_article(pw, article_url: str):
    """Process a single article: download JSON and optionally PDF."""
    article_id = extract_article_id(article_url)
    if not article_id:
        print(f"Skipping invalid article URL: {article_url}")
        return

    # 1. Download JSON
    api_url = article_url.replace("/article/", "/api/article/")
    try:
        print(f"  → Downloading JSON: {api_url}")
        r = requests.get(api_url, timeout=15)
        r.raise_for_status()
        data_json = r.json()
        project_name = (
            data_json.get("article", {}).get("project_name")
            or data_json.get("project_name")
            or f"article_{article_id}"
        )
        base_name = safe_filename(project_name)
        proj_dir = PROJECTS_DIR / base_name
        proj_dir.mkdir(exist_ok=True)
        json_path = proj_dir / f"{article_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data_json, f, ensure_ascii=False, indent=2)
        print(f"  ✔ Saved JSON to {json_path}")
    except Exception as e:
        print(f"  ✖ Failed to download JSON {api_url}: {e}")

    # 2. Use Playwright to check for PDF and download it if present with retries
    attempt = 0
    while attempt < MAX_RETRIES:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        print(f"  → Navigating to {article_url} (attempt {attempt+1}/{MAX_RETRIES})")
        try:
            await page.goto(article_url, timeout=30_000, wait_until="domcontentloaded")
            has_pdf = await page_has_pdf(page)
            if has_pdf:
                print("  ✔ PDF iframe detected")
                await download_pdf(page, article_url, proj_dir, article_id)
            else:
                print("  ↺ No PDF iframe detected – only JSON saved")
            await browser.close()
            break  # success
        except Exception as e:
            print(f"  ✖ Error processing article page {article_url}: {e}")
            attempt += 1
            await browser.close()
            if attempt >= MAX_RETRIES:
                print(f"  ✖ Failed after {MAX_RETRIES} attempts, moving on.")
            else:
                print("  ↻ Retrying...")


async def main():
    # Load JSON file
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    articles = [item["Article Link"] for item in data["Exported Data"]]
    if MAX_ARTICLES:
        articles = articles[:MAX_ARTICLES]

    async with async_playwright() as pw:
        for idx, url in enumerate(articles, 1):
            print(f"\nProcessing article {idx}/{len(articles)}: {url}")
            await process_article(pw, url)


if __name__ == "__main__":
    # Run the asyncio event loop
    asyncio.run(main())
