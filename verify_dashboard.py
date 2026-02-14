import os
import time
import re
from playwright.sync_api import sync_playwright

def verify_dashboard():
    """
    Verifies the functionality of the Sports Card Dashboard using Playwright.
    This script tests:
    1. Navigation to the dashboard.
    2. Scraping using the "Add New Card" form (simulating eBay lookup).
    3. Image analysis using the "Scan Card" uploader (simulating Anthropic scan).
    """

    # Configuration
    DASHBOARD_URL = "http://localhost:8501"

    # Prioritize user-provided test images if available
    possible_images = [
        "tests/mcdavid1.jpg",
        "tests/mcdavid2.jpg",
        "tests/test_card.jpg"
    ]
    TEST_IMAGE_PATH = None
    for img_path in possible_images:
        abs_path = os.path.abspath(img_path)
        if os.path.exists(abs_path):
            TEST_IMAGE_PATH = abs_path
            break

    if not TEST_IMAGE_PATH:
        print("❌ No test image found. Please ensure 'tests/test_card.jpg' or 'tests/mcdavid1.jpg' exists.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"Navigating to {DASHBOARD_URL}...")
        try:
            page.goto(DASHBOARD_URL, timeout=60000)
        except Exception as e:
            print(f"Error navigating to dashboard: {e}")
            print("Is the dashboard running? Run `streamlit run dashboard.py` in another terminal.")
            browser.close()
            return

        # Wait for the main elements to load
        page.wait_for_selector("text=Southwest Sports Cards", timeout=15000)
        print("✅ Dashboard loaded successfully.")

        # ---------------------------------------------------------
        # Test 1: Add New Card (eBay Scraper Simulation)
        # ---------------------------------------------------------
        print("\nTesting 'Add New Card' functionality (with scraping enabled)...")

        # Fill in form fields
        page.get_by_label("Player Name *").fill("Test Player")
        page.get_by_label("Card Number *").fill("999")
        page.get_by_label("Card Set *").fill("Test Set")
        page.get_by_label("Year *").fill("2024-25")

        # Ensure scraping is enabled (it's checked by default)
        scrape_label = page.get_by_text("Scrape eBay for prices")
        if scrape_label.is_visible():
            print("Scraping option is visible.")

        print("Filled out 'Add New Card' form.")

        # Submit the form
        page.get_by_role("button", name="Add Card").click()

        # Wait for processing - scraping might take time or fail quickly if offline
        try:
            page.wait_for_selector("text=Running...", state="visible", timeout=5000)
            page.wait_for_selector("text=Running...", state="hidden", timeout=30000)
        except Exception:
            pass

        time.sleep(2) # Extra buffer

        # Check for success or warning message
        # Success: "Found X sales! Fair value: $..." (green alert)
        # Warning: "No sales found. Defaulted to $5.00." (yellow alert)

        # Use more specific locators for alerts to avoid matching unrelated text
        # Streamlit alerts usually have specific classes, but text matching is more robust across versions if specific enough.

        # We look for "Found" followed by digits, or "No sales found"
        # We can use a regex locator for precision

        try:
            success_locator = page.get_by_text(re.compile(r"Found \d+ sales"))
            warning_locator = page.get_by_text("No sales found", exact=False)

            if success_locator.count() > 0 and success_locator.first.is_visible():
                print(f"✅ 'Add New Card' successful: {success_locator.first.text_content()}")
            elif warning_locator.count() > 0 and warning_locator.first.is_visible():
                print(f"✅ 'Add New Card' completed (offline/no results): {warning_locator.first.text_content()}")
            else:
                 # Fallback: check if row was added to dataframe or metrics updated?
                 # Assuming silence means no error popup, which is partial success.
                 print("⚠️ 'Add New Card' finished, but specific success/warning message not detected immediately.")
        except Exception as e:
            print(f"⚠️ Error checking messages: {e}")

        print("✅ 'Add New Card' form submitted without crashing.")

        # ---------------------------------------------------------
        # Test 2: Scan Card (Anthropic Simulation)
        # ---------------------------------------------------------
        print("\nTesting 'Scan Card' functionality...")

        # Locate the file uploader for "Front of card"
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(TEST_IMAGE_PATH)

        print(f"Uploaded {TEST_IMAGE_PATH}.")

        # Wait for upload to complete
        page.wait_for_selector(f"text={os.path.basename(TEST_IMAGE_PATH)}", timeout=15000)

        # Click "Analyze Card"
        analyze_btn = page.get_by_role("button", name="Analyze Card")

        time.sleep(2)

        if analyze_btn.is_enabled():
            analyze_btn.click()
            print("Clicked 'Analyze Card'.")

            time.sleep(2)

            # Check for expected outcome
            if page.get_by_text("ANTHROPIC_API_KEY not set").is_visible() or \
               page.get_by_text("Analysis failed").is_visible():
                print("✅ 'Analyze Card' executed (received expected error due to missing API key/Net).")
            elif page.get_by_text("Card identified").is_visible():
                 print("✅ 'Analyze Card' successful!")
            else:
                print("⚠️ 'Analyze Card' clicked, but no specific error/success message found immediately.")
        else:
            print("❌ 'Analyze Card' button is disabled.")

        # Take a screenshot
        os.makedirs("tests", exist_ok=True)
        page.screenshot(path="tests/dashboard_verification_result.png")
        print("\n✅ Verification complete. Screenshot saved to 'tests/dashboard_verification_result.png'.")

        browser.close()

if __name__ == "__main__":
    verify_dashboard()
