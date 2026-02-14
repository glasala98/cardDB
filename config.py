import os

# Scraper Settings

# Default price to use when no sales data is found
DEFAULT_PRICE = float(os.getenv('CARD_SCRAPER_DEFAULT_PRICE', 5.00))

# Number of parallel Chrome instances for scraping
NUM_WORKERS = int(os.getenv('CARD_SCRAPER_NUM_WORKERS', 10))

# Maximum number of results to fetch from eBay
EBAY_MAX_RESULTS = int(os.getenv('CARD_SCRAPER_EBAY_MAX_RESULTS', 50))
