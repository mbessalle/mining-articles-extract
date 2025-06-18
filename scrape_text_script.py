#!/usr/bin/env python3
"""scraper_script_text_only.py

A highly robust script to scrape article pages. It waits for all dynamic
content (article text and financial data) and then surgically extracts the
financial table to ensure clean, readable output for an LLM.

Usage (after installing dependencies):
    python3 scraper_script_text_only.py

One-time Installation:
    pip install playwright html2text
    playwright install chromium
"""

import asyncio
import re
from pathlib import Path
import json
from typing import Optional, Dict

import html2text
from playwright.async_api import async_playwright, Page, Error

# ------------- Configuration ------------- #
ROOT_DIR = Path("/home/laptop/projects/celis/usa")
TEXT_OUTPUT_DIR = ROOT_DIR / "scraped_text"
TEXT_OUTPUT_DIR.mkdir(exist_ok=True)

SOURCE_JSON_PATH = ROOT_DIR / "USA-projects.json"

MAX_ARTICLES = None  # Set to None for all, or a number for testing
MAX_RETRIES = 3

# ----------------------------------------- #

ARTICLE_ID_RE = re.compile(r"/article/(\d+)")


def extract_article_id(url: str) -> Optional[str]:
    """Return the numeric article ID from a URL."""
    m = ARTICLE_ID_RE.search(url)
    return m.group(1) if m else None


def convert_html_to_text(html_content: str) -> str:
    """Converts a block of HTML content to clean text."""
    h = html2text.HTML2Text()
    h.ignore_images = True
    h.body_width = 0
    h.ignore_emphasis = False
    # Remove the financial data widget from the main text to avoid duplication
    h.hide_tags = ['div[data-qmod-tool="detailedquotetab"]']
    return h.handle(html_content).strip()


async def scrape_main_content(page: Page) -> Optional[str]:
    """Waits for the main article text and scrapes its wrapper."""
    try:
        await page.wait_for_selector(".news-item", timeout=15000)
        container = await page.query_selector("#news-article-wrapper")
        if container:
            return await container.inner_html()
        return None
    except Error as e:
        print(f"  ✖ Error waiting for or scraping main content: {e}")
        return None


async def scrape_financial_data(page: Page) -> Optional[Dict[str, str]]:
    """
    Surgically extracts each label and value from the 'Detailed Quote' table.
    Returns a clean dictionary.
    """
    financial_data = {}
    print("  → Looking for financial data table...")

    try:
        # Wait for a specific, reliable row inside the table to ensure it's populated.
        # 'Market Cap' is a good candidate. We look for a div that contains this text.
        await page.wait_for_selector("div.qmod-label:has-text('Market Cap')", timeout=15000)
        print("  ✔ Financial data appears to be loaded.")

        # Find all the rows in the table
        rows = await page.query_selector_all("div.qmod-quotegrid div.qmod-line-sep")
        if not rows:
            print("  (Info) Financial table container found, but no data rows inside.")
            return None

        for row in rows:
            label_el = await row.query_selector("div.qmod-label")
            value_el = await row.query_selector("div.qmod-data-point")
            
            if label_el and value_el:
                label = (await label_el.text_content() or "").strip()
                # The value can be complex, so we get all text inside it
                value = (await value_el.inner_text() or "").strip().replace('\n', ' ')
                if label and value:
                    financial_data[label] = value
        
        print(f"  ✔ Extracted {len(financial_data)} key-value pairs from financial table.")
        return financial_data
    except Error:
        print("  (Info) Financial data table did not load or was not found.")
        return None


def format_financial_data(data: Dict[str, str]) -> str:
    """Formats the extracted financial dictionary into a clean, two-column string."""
    if not data:
        return ""

    header = "--- Detailed Quote ---\n"
    lines = [header]
    
    # Get all keys to process them in order
    labels = list(data.keys())
    
    # Process in pairs for two-column layout
    i = 0
    # Determine the max label length for nice padding in the first column
    # We only consider every other label for the first column's width
    max_len = max(len(labels[j]) for j in range(0, len(labels), 2)) if labels else 0

    while i < len(labels):
        # Left column
        left_label = labels[i]
        left_value = data[left_label]
        
        # Right column (if it exists)
        if i + 1 < len(labels):
            right_label = labels[i+1]
            right_value = data[right_label]
            padding = " " * (max_len - len(left_label) + 4)
            lines.append(f"{left_label}: {left_value}{padding}{right_label}: {right_value}")
        else:
            # If there's an odd one out
            lines.append(f"{left_label}: {left_value}")
        
        i += 2

    return "\n".join(lines)


async def process_url(playwright_instance, article_url: str):
    """Visits a URL, scrapes content, and saves it as a text file."""
    article_id = extract_article_id(article_url)
    if not article_id: return
        
    output_txt_path = TEXT_OUTPUT_DIR / f"{article_id}.txt"
    if output_txt_path.exists():
        print(f"  ↺ File already exists, skipping: {output_txt_path.name}")
        return

    for attempt in range(MAX_RETRIES):
        browser = None
        try:
            browser = await playwright_instance.chromium.launch(headless=True)
            page = await browser.new_page()
            print(f"  → Visiting {article_url} (attempt {attempt+1}/{MAX_RETRIES})")
            await page.goto(article_url, timeout=45_000, wait_until="domcontentloaded")

            # Scrape the main content HTML
            main_html = await scrape_main_content(page)
            # Surgically scrape the financial data separately
            financial_dict = await scrape_financial_data(page)

            if main_html:
                # Convert the main HTML block to text, hiding the messy financial part
                clean_main_text = convert_html_to_text(main_html)
                
                # Format the surgically scraped financial data
                formatted_financial_text = format_financial_data(financial_dict)

                # Combine them for the final output
                final_text = f"{clean_main_text}\n\n{formatted_financial_text}".strip()
                
                output_txt_path.write_text(final_text, encoding="utf-8")
                print(f"  ✔ Saved clean, combined content to: {output_txt_path.name}")
            else:
                raise ValueError("Main content container not found, scrape failed.")

            break # Success
        except Exception as e:
            print(f"  ✖ Playwright error on page {article_url}: {e}")
            if attempt + 1 >= MAX_RETRIES:
                error_message = f"Failed to scrape content from {article_url} after {MAX_RETRIES} retries."
                output_txt_path.write_text(error_message, encoding="utf-8")
                print(f"  ✖ Wrote error placeholder to: {output_txt_path.name}")
            else:
                print("  ↻ Retrying...")
        finally:
            if browser:
                await browser.close()


async def main():
    if not SOURCE_JSON_PATH.exists():
        print(f"ERROR: Source URL file not found at {SOURCE_JSON_PATH}")
        return

    with open(SOURCE_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    unique_urls = sorted(list({item["Article Link"] for item in data.get("Exported Data", []) if "Article Link" in item}))
    articles_to_process = unique_urls[:MAX_ARTICLES] if MAX_ARTICLES is not None else unique_urls
    total_to_process = len(articles_to_process)
    print(f"Found {total_to_process} articles to process.")

    async with async_playwright() as pw:
        for idx, url in enumerate(articles_to_process, 1):
            print(f"\n--- Processing article {idx}/{total_to_process}: {url} ---")
            await process_url(pw, url)

if __name__ == "__main__":
    asyncio.run(main())