#!/usr/bin/env python3
"""Test script to inspect eBay sold listing HTML structure and URLs.
Run on the server where Chrome/Selenium is installed:
    python3 test_ebay_urls.py
"""

import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def create_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    return webdriver.Chrome(options=options)


def inspect_sold_listings():
    driver = create_driver()
    search = "jalen hurts mosaic stained glass psa 9"
    url = f"https://www.ebay.com/sch/i.html?_nkw={search.replace(' ', '+')}&_sacat=0&LH_Complete=1&LH_Sold=1&_sop=13&_ipg=240"

    print(f"Fetching: {url}\n")
    driver.get(url)
    time.sleep(3)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.s-card'))
        )
    except Exception as e:
        print(f"Timeout waiting for .s-card: {e}")
        # Try alternate selector
        print("\nTrying alternate selectors...")
        for sel in ['.srp-results', '.s-item', '[data-view]', '.s-card__title']:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            print(f"  {sel}: {len(elems)} found")

    items = driver.find_elements(By.CSS_SELECTOR, '.s-card')
    print(f"Found {len(items)} .s-card elements\n")

    for i, item in enumerate(items[:5]):
        print(f"{'='*80}")
        print(f"CARD #{i+1}")
        print(f"{'='*80}")

        # Get title
        try:
            title_elem = item.find_element(By.CSS_SELECTOR, '.s-card__title')
            title = title_elem.text.strip()
            print(f"Title: {title[:80]}")
            print(f"Title tag: <{title_elem.tag_name}>")
            print(f"Title classes: {title_elem.get_attribute('class')}")
        except Exception as e:
            print(f"No .s-card__title found: {e}")
            title_elem = None

        # Find ALL anchor tags in this card
        anchors = item.find_elements(By.CSS_SELECTOR, 'a')
        print(f"\nAll <a> tags in this card ({len(anchors)}):")
        for j, a in enumerate(anchors):
            href = a.get_attribute('href') or '(none)'
            text = a.text.strip()[:50] if a.text.strip() else '(no text)'
            print(f"  [{j}] href: {href[:120]}")
            print(f"       text: {text}")

        # Specifically look for /itm/ links
        itm_links = item.find_elements(By.CSS_SELECTOR, 'a[href*="/itm/"]')
        print(f"\n/itm/ links: {len(itm_links)}")
        for a in itm_links:
            print(f"  {a.get_attribute('href')[:120]}")

        # Look for /p/ links (product pages)
        p_links = item.find_elements(By.CSS_SELECTOR, 'a[href*="/p/"]')
        print(f"\n/p/ links: {len(p_links)}")
        for a in p_links:
            print(f"  {a.get_attribute('href')[:120]}")

        # Check title's parent chain for anchors
        if title_elem:
            print(f"\nTitle parent chain:")
            try:
                parent = title_elem.find_element(By.XPATH, '..')
                for _ in range(5):
                    tag = parent.tag_name
                    href = parent.get_attribute('href') or ''
                    cls = parent.get_attribute('class') or ''
                    print(f"  <{tag}> class='{cls[:60]}' href='{href[:100]}'")
                    if tag == 'body':
                        break
                    parent = parent.find_element(By.XPATH, '..')
            except Exception:
                pass

        # Get outer HTML of the card (first 2000 chars)
        try:
            outer = item.get_attribute('outerHTML')
            # Extract just the anchor tags for clarity
            a_tags = re.findall(r'<a\s[^>]*>', outer)
            print(f"\nRaw <a> tags in HTML ({len(a_tags)}):")
            for tag in a_tags[:10]:
                print(f"  {tag[:200]}")
        except Exception:
            pass

        print()

    driver.quit()


if __name__ == '__main__':
    inspect_sold_listings()
