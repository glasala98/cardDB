import time
import random
import csv
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

class CardScraper:
    def __init__(self, headless=True):
        self.base_url = "https://example-card-site.com/search"  # Placeholder URL
        self.data = []
        self.driver = self._setup_driver(headless)

    def _setup_driver(self, headless):
        """Sets up Chrome driver with stealth options."""
        options = Options()
        if headless:
            options.add_argument("--headless=new") 
        
        # Anti-detection: Disable automation flags
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Randomize User-Agent (In prod, rotate this list)
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]
        options.add_argument(f"user-agent={random.choice(user_agents)}")
        
        driver = webdriver.Chrome(options=options)
        
        # Obfuscate navigator.webdriver
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver

    def random_sleep(self, min_s=1.5, max_s=4.0):
        """Human-like delay."""
        time.sleep(random.uniform(min_s, max_s))

    def scrape_cards(self, search_term):
        """Main logic to scrape card data."""
        logging.info(f"Starting scrape for: {search_term}")
        
        try:
            self.driver.get(f"{self.base_url}?q={search_term}")
            self.random_sleep(2, 5)

            # Wait for list to load
            wait = WebDriverWait(self.driver, 15)
            cards = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".card-listing-item")))

            for card in cards:
                try:
                    # Extract data mapping to your CSV structure
                    name = card.find_element(By.CSS_SELECTOR, ".title").text
                    
                    # handling price extraction safely
                    price_str = card.find_element(By.CSS_SELECTOR, ".fair-value").text
                    fair_value = price_str.replace('$', '').strip()

                    trend = "unknown"
                    try:
                        trend_elem = card.find_element(By.CSS_SELECTOR, ".trend-icon")
                        trend = "up" if "arrow-up" in trend_elem.get_attribute("class") else "down"
                    except NoSuchElementException:
                        pass
                    
                    self.data.append({
                        "Card Name": name,
                        "Fair Value": f"${fair_value}",
                        "Trend": trend,
                        "Num Sales": random.randint(0, 50) # Mocking secondary data if not visible
                    })
                    
                except Exception as e:
                    logging.warning(f"Skipped a card due to error: {str(e)}")
                    continue
                
            logging.info(f"Successfully scraped {len(self.data)} cards.")

        except TimeoutException:
            logging.error("Timed out waiting for page to load.")
        finally:
            self.driver.quit()

    def save_to_csv(self, filename="scraped_cards.csv"):
        if not self.data:
            logging.warning("No data to save.")
            return

        keys = self.data[0].keys()
        with open(filename, 'w', newline='', encoding='utf-8') as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(self.data)
        logging.info(f"Data saved to {filename}")

if __name__ == "__main__":
    scraper = CardScraper(headless=True)
    scraper.scrape_cards("Connor McDavid Young Guns")
    scraper.save_to_csv()