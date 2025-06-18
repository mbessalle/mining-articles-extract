#!/usr/bin/env python3
import csv
import time
import random
import asyncio
from playwright.async_api import async_playwright
import pandas as pd
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def scrape_project_details():
    # Read the CSV file with project URLs
    df = pd.read_csv('data/raw/australia_cleaned.csv')
    
    # Create CSV file with headers
    with open('project_market_details.csv', 'w', newline='') as csvfile:
        fieldnames = ['project_name', 'url', 'ticker_exchange', 'share_price', 'shares_out']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        print("Created CSV file with headers")
    
    # Initialize Playwright
    async with async_playwright() as p:
        # Launch a browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Initialize a list to store project data and a counter
        project_data = []
        batch_counter = 0
        
        # Loop through each URL in the CSV
        for index, row in df.iterrows():
            try:
                url = row['Article Link']
                print(f"Processing URL: {url}")
                
                # Try multiple navigation methods with fallbacks
                navigation_success = False
                
                # Method 1: goto with domcontentloaded
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                    navigation_success = True
                    logging.info(f"Successfully navigated to {url} using method 1")
                except Exception as e:
                    logging.error(f"Method 1 navigation failed for {url}: {e}")
                
                # Method 2: goto with load state
                if not navigation_success:
                    try:
                        await page.goto(url, timeout=15000)
                        await page.wait_for_load_state('domcontentloaded', timeout=10000)
                        navigation_success = True
                        logging.info(f"Successfully navigated to {url} using method 2")
                    except Exception as e:
                        logging.error(f"Method 2 navigation failed for {url}: {e}")
                
                # Method 3: evaluate location.href
                if not navigation_success:
                    try:
                        await page.evaluate(f"window.location.href = '{url}';")
                        await page.wait_for_load_state('domcontentloaded', timeout=10000)
                        navigation_success = True
                        logging.info(f"Successfully navigated to {url} using method 3")
                    except Exception as e:
                        logging.error(f"Method 3 navigation failed for {url}: {e}")
                
                if not navigation_success:
                    logging.error(f"All navigation methods failed for {url}, skipping")
                    continue
                
                logging.info(f"Processing URL: {url}")
                # Wait a bit more to ensure all content is loaded
                await asyncio.sleep(2)
                
                # First check if stock information is directly available on the page
                # Look for the qmod-detailedquote div which contains stock information
                stock_info = {}
                qmod_div = await page.query_selector('div.qmod-detailedquote')
                
                if qmod_div:
                    logging.info("Found stock information directly on the page")
                    
                    # Extract ticker symbol
                    symbol_element = await page.query_selector('span[rv-html="data.symbolstring | whitespace"]')
                    if symbol_element:
                        ticker_exchange = await symbol_element.inner_text()
                        # Extract primary ticker (before the colon if present)
                        if ':' in ticker_exchange:
                            ticker_exchange = ticker_exchange.split(':')[0] + ':' + ticker_exchange.split(':')[1].split(' ')[0]
                        stock_info['ticker_exchange'] = ticker_exchange
                        logging.info(f"Found ticker: {ticker_exchange}")
                    
                    # Extract share price
                    price_element = await page.query_selector('span.qmod-last')
                    if price_element:
                        share_price = await price_element.inner_text()
                        stock_info['share_price'] = share_price
                        logging.info(f"Found share price: {share_price}")
                    
                    # Extract shares outstanding
                    shares_element = await page.query_selector('div.qmod-quote-element-shareclasslevelsharesoutstanding .qmod-data-point')
                    if shares_element:
                        shares_out = await shares_element.inner_text()
                        stock_info['shares_out'] = shares_out
                        logging.info(f"Found shares out: {shares_out}")
                    
                    # If we have all the information, write it to the CSV
                    if 'ticker_exchange' in stock_info and 'share_price' in stock_info and 'shares_out' in stock_info:
                        # Get the project name from the page title or h1
                        project_name_element = await page.query_selector('h1.qmod-heading span.qmod-t-text')
                        if project_name_element:
                            project_name = await project_name_element.inner_text()
                            logging.info(f"Found project name: {project_name}")
                            
                            # Add the data to the project_data list
                            project_data.append({
                                'project_name': project_name,
                                'url': url,
                                'ticker_exchange': stock_info['ticker_exchange'],
                                'share_price': stock_info['share_price'],
                                'shares_out': stock_info['shares_out']
                            })
                            batch_counter += 1
                            
                            # Write to CSV file in batches of 5
                            if batch_counter >= 5:
                                try:
                                    with open('project_market_details.csv', 'a', newline='') as csvfile:
                                        fieldnames = ['project_name', 'url', 'ticker_exchange', 'share_price', 'shares_out']
                                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                                        for data in project_data[-5:]:
                                            writer.writerow(data)
                                        print(f"Wrote batch of {min(5, len(project_data[-5:]))} projects to CSV")
                                    # Reset the batch counter
                                    batch_counter = 0
                                except Exception as e:
                                    print(f"Error writing batch to CSV file: {e}")
                            continue  # Skip to next URL since we already have the information
                
                # If we didn't find stock information directly, look for project links
                project_links = []
                
                # Try multiple approaches to find project links
                # 1. Check if the current-project div exists
                current_project_div = await page.query_selector('#current-project')
                if current_project_div:
                    logging.info("Found current-project div")
                    # Dump the HTML of the current-project div for debugging
                    current_project_html = await page.evaluate('(element) => element.outerHTML', current_project_div)
                    logging.info(f"Current project div HTML: {current_project_html}")
                    
                    # Find project links within the current-project div
                    project_elements = await current_project_div.query_selector_all('div.project a[rel="canonical"]')
                    logging.info(f"Found {len(project_elements)} project elements with selector 'div.project a[rel=\"canonical\"]'")
                    
                    # If no elements found, try a more general selector
                    if not project_elements:
                        project_elements = await current_project_div.query_selector_all('a[rel="canonical"]')
                        logging.info(f"Found {len(project_elements)} project elements with selector 'a[rel=\"canonical\"]'")
                    
                    # Extract href and text from each project link
                    for project_element in project_elements:
                        href = await project_element.get_attribute('href')
                        text = await project_element.inner_text()
                        if href and text:
                            project_links.append((href, text))
                            logging.info(f"Added project link: {text} - {href}")
                
                logging.info(f"Found {len(project_links)} project links in current-project div")
                
                # Process each project link
                for href, project_name in project_links:
                    try:
                        print(f"Found project: {project_name}")
                        
                        # Navigate to the project page using the href
                        project_url = 'https://app.mininghub.com' + href if href.startswith('/') else href
                        logging.info(f"Navigating to: {project_url}")
                        
                        # Try multiple navigation methods with fallbacks for project page
                        project_navigation_success = False
                        
                        # Method 1: goto with domcontentloaded
                        try:
                            response = await page.goto(project_url, wait_until='domcontentloaded', timeout=15000)
                            if response.ok:
                                project_navigation_success = True
                                logging.info(f"Successfully navigated to project {project_url} using method 1")
                            else:
                                logging.error(f"Navigation to {project_url} failed with status {response.status}")
                        except Exception as e:
                            logging.error(f"Method 1 project navigation failed for {project_url}: {e}")
                        
                        # Method 2: goto with load state
                        if not project_navigation_success:
                            try:
                                await page.goto(project_url, timeout=15000)
                                await page.wait_for_load_state('domcontentloaded', timeout=10000)
                                project_navigation_success = True
                                logging.info(f"Successfully navigated to project {project_url} using method 2")
                            except Exception as e:
                                logging.error(f"Method 2 project navigation failed for {project_url}: {e}")
                        
                        # Method 3: evaluate location.href
                        if not project_navigation_success:
                            try:
                                await page.evaluate(f"window.location.href = '{project_url}';")
                                await page.wait_for_load_state('domcontentloaded', timeout=10000)
                                project_navigation_success = True
                                logging.info(f"Successfully navigated to project {project_url} using method 3")
                            except Exception as e:
                                logging.error(f"Method 3 project navigation failed for {project_url}: {e}")
                        
                        if not project_navigation_success:
                            logging.error(f"All navigation methods failed for project {project_url}, skipping")
                            # Try to navigate back to the original URL
                            try:
                                await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                            except Exception as e:
                                logging.error(f"Failed to navigate back to article page: {e}")
                            continue
                        
                        # Wait for the page to load (random time between 5-7 seconds)
                        wait_time = random.uniform(5, 7)
                        await asyncio.sleep(wait_time)
                        
                        # Extract ticker exchange
                        ticker_exchange = ""
                        ticker_row = await page.query_selector('tr:has-text("Ticker/Exchange")')
                        if ticker_row:
                            ticker_cell = await ticker_row.query_selector('td:nth-child(2)')
                            if ticker_cell:
                                full_ticker = await ticker_cell.inner_text()
                                # Extract only the primary ticker (first one listed)
                                if ',' in full_ticker:
                                    ticker_exchange = full_ticker.split(',')[0].strip()
                                else:
                                    ticker_exchange = full_ticker.strip()
                                print(f"Ticker/Exchange (primary only): {ticker_exchange}")
                        
                        # Extract share price
                        share_price = ""
                        price_element = await page.query_selector('.qmod-last')
                        if price_element:
                            share_price = await price_element.inner_text()
                            print(f"Share Price: {share_price}")
                        
                        # Extract shares out
                        shares_out = ""
                        shares_row = await page.query_selector('div.qmod-quote-element-shareclasslevelsharesoutstanding')
                        if shares_row:
                            shares_cell = await shares_row.query_selector('.qmod-data-point')
                            if shares_cell:
                                shares_out = await shares_cell.inner_text()
                                print(f"Shares Out: {shares_out}")
                        
                        # Add the data to the project_data list
                        project_data.append({
                            'project_name': project_name,
                            'url': url,
                            'ticker_exchange': ticker_exchange,
                            'share_price': share_price,
                            'shares_out': shares_out
                        })
                        batch_counter += 1
                        
                        # Write to CSV file in batches of 5
                        if batch_counter >= 5:
                            try:
                                with open('project_market_details.csv', 'a', newline='') as csvfile:
                                    fieldnames = ['project_name', 'url', 'ticker_exchange', 'share_price', 'shares_out']
                                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                                    for data in project_data[-5:]:
                                        writer.writerow(data)
                                    print(f"Wrote batch of {min(5, len(project_data[-5:]))} projects to CSV")
                                # Reset the batch counter
                                batch_counter = 0
                            except Exception as e:
                                print(f"Error writing batch to CSV file: {e}")
                        
                        # Try multiple navigation methods to go back to the article page
                        back_navigation_success = False
                        
                        # Method 1: goto with domcontentloaded
                        try:
                            logging.info("Navigating back to the article page using method 1")
                            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                            back_navigation_success = True
                            logging.info("Successfully navigated back using method 1")
                        except Exception as e:
                            logging.error(f"Method 1 back navigation failed: {e}")
                        
                        # Method 2: go_back() with wait_for_load_state
                        if not back_navigation_success:
                            try:
                                logging.info("Navigating back to the article page using method 2")
                                await page.go_back()
                                await page.wait_for_load_state('domcontentloaded', timeout=10000)
                                back_navigation_success = True
                                logging.info("Successfully navigated back using method 2")
                            except Exception as e:
                                logging.error(f"Method 2 back navigation failed: {e}")
                        
                        # Method 3: evaluate location.href
                        if not back_navigation_success:
                            try:
                                logging.info("Navigating back to the article page using method 3")
                                await page.evaluate(f"window.location.href = '{url}';")
                                await page.wait_for_load_state('domcontentloaded', timeout=10000)
                                back_navigation_success = True
                                logging.info("Successfully navigated back using method 3")
                            except Exception as e:
                                logging.error(f"Method 3 back navigation failed: {e}")
                        
                        # Method 4: Create a new page as a last resort
                        if not back_navigation_success:
                            try:
                                logging.info("Creating a new page as a last resort")
                                page = await browser.new_page()
                                await page.goto(url, timeout=15000, wait_until='domcontentloaded')
                                back_navigation_success = True
                                logging.info("Successfully created new page and navigated to article")
                            except Exception as e:
                                logging.error(f"Failed to create new page and navigate: {e}")
                        
                        # Wait a bit more to ensure all content is loaded if navigation was successful
                        if back_navigation_success:
                            await asyncio.sleep(2)
                        
                        # Wait a bit to avoid overloading the server
                        await asyncio.sleep(1)
                    except Exception as e:
                        print(f"Error processing project: {e}")
                        continue
                
            except Exception as e:
                print(f"Error processing URL {url}: {e}")
                continue
        
        # Write any remaining data to the CSV file
        if batch_counter > 0:
            try:
                with open('project_market_details.csv', 'a', newline='') as csvfile:
                    fieldnames = ['project_name', 'url', 'ticker_exchange', 'share_price', 'shares_out']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    for data in project_data[-batch_counter:]:
                        writer.writerow(data)
                    print(f"Wrote final batch of {batch_counter} projects to CSV")
            except Exception as e:
                print(f"Error writing final batch to CSV file: {e}")
        
        # Print a summary of the collected data
        if project_data:
            print(f"Successfully processed {len(project_data)} projects")
        else:
            print("No project data collected.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_project_details())
