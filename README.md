# Sports Card Analytics Dashboard

A full-stack toolkit for tracking sports card collection value. Scrapes eBay sold listings to estimate fair market value, visualizes trends over time, and manages your portfolio — all through an interactive Streamlit dashboard deployed at **https://southwestsportscards.ca/**.

## Features

- **eBay Price Scraping** — Scrapes sold listings from eBay using Selenium to calculate fair market value, median, min/max, and trend direction for each card.
- **Interactive Dashboard** — Three-page Streamlit app with Charts, Card Ledger, and Card Inspect views, powered by Plotly.
- **AI Card Scanner** — Upload a photo of a card and Claude 3.5 Sonnet extracts player, set, year, card number, and grade automatically.
- **Card Inspect** — Drill into any card to see fair value tracking over time, eBay sales scatter chart, and individual sale details.
- **Daily Automated Scraping** — Cron job rescrapes all cards daily, appending price deltas to a historical log.
- **Archive & Restore** — Remove cards from your collection with a confirmation step. Archived cards can be restored at any time.
- **Structured Card Data** — Parses card names into Player, Year, Set, Subset (e.g. Young Guns), Card #, Serial (e.g. /99), and Grade.

## Prerequisites

- **Python 3.9+**
- **Google Chrome** — The scraper uses Selenium with ChromeDriver.
- **Anthropic API Key** — Required for the AI card scanner feature.

## Installation

```bash
git clone https://github.com/glasala98/cardDB.git
cd cardDB
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Set your Anthropic API key as an environment variable:

```bash
export ANTHROPIC_API_KEY="your_api_key_here"
```

## Usage

### Running the Dashboard

```bash
streamlit run dashboard_prod.py
```

Opens at `http://localhost:8501` with three pages:

- **Charts** — Collection value distribution, price trends, top cards by value, grade breakdown (bar, pie, scatter charts).
- **Card Ledger** — Full collection table with View and Remove checkboxes per row. Add new cards manually or via AI photo scan. Search and filter your collection.
- **Card Inspect** — Select a card to see:
  - Card details (Player, Set, Subset, Card #, Serial, Grade, Fair Value, Trend)
  - **Fair Value Tracking** — Line chart of scraped fair value over time
  - **eBay Sales History** — Scatter chart of individual eBay sales, last 5 sales shown with expander for full history
  - **Rescrape** button to update prices on demand

### Scraping Card Prices

Bulk scrape all cards in `hockey_cards.csv`:

```bash
python scrape_card_prices.py
```

Outputs:
- `card_prices_results.json` — Detailed results with raw eBay sales per card
- `card_prices_summary.csv` — Summary with fair value, trend, min/max, num sales

### Daily Automated Scraping

`daily_scrape.py` rescrapes all cards in the database and appends fair value deltas to `price_history.json`.

```bash
python daily_scrape.py              # default 3 workers
python daily_scrape.py --workers 5  # more parallel browsers
```

Set up as a cron job on the server:

```bash
0 6 * * * cd /opt/card-dashboard && /usr/bin/python3 daily_scrape.py --workers 3 >> /var/log/daily_scrape.log 2>&1
```

## Data Files

| File | Description |
|------|-------------|
| `card_prices_summary.csv` | Main database — one row per card with fair value, trend, stats |
| `card_prices_results.json` | Detailed scrape results with raw eBay sales arrays per card |
| `price_history.json` | Append-only log of fair value snapshots over time per card |
| `card_archive.csv` | Archived (removed) cards with timestamps for restore |
| `hockey_cards.csv` | Original input list of cards to scrape |

## Project Structure

| File | Purpose |
|------|---------|
| `dashboard_prod.py` | Production Streamlit dashboard (Charts, Ledger, Inspect) |
| `dashboard_utils.py` | Shared utilities: data loading, parsing, scraping, archiving |
| `scrape_card_prices.py` | Bulk eBay scraper with fair value calculation |
| `card_scraper.py` | Selenium helper class for eBay scraping |
| `daily_scrape.py` | Daily cron job for automated rescraping |
| `deploy/` | Deployment configs (setup.sh, nginx.conf, systemd service) |
| `tests/` | Unit tests |
| `run_tests.py` | Test runner |

## Deployment

For detailed deployment instructions and documentation of the configuration files, see [deploy/README.md](deploy/README.md).

The dashboard is currently deployed to a DigitalOcean VPS running Ubuntu, served via Nginx with SSL.

### Initial Setup

1. Clone the repo on the server:
   ```bash
   ssh root@104.236.65.233
   cd /root && git clone https://github.com/glasala98/cardDB.git
   ```

2. Run the setup script:
   ```bash
   cd /root/cardDB
   sudo bash deploy/setup.sh southwestsportscards.ca
   ```

   This installs Python, Chrome, Nginx, obtains an SSL certificate, and starts the dashboard as a systemd service.

3. Edit the API key:
   ```bash
   sudo nano /opt/card-dashboard/.env
   ```

### Updating (Deploy New Changes)

```bash
# On the server:
cd /root/cardDB && git pull

# Copy updated files to the app directory:
sudo cp dashboard_prod.py dashboard_utils.py scrape_card_prices.py daily_scrape.py card_prices_summary.csv /opt/card-dashboard/
sudo cp -f card_prices_results.json price_history.json /opt/card-dashboard/ 2>/dev/null; true
sudo chown -R cardapp:cardapp /opt/card-dashboard/
sudo systemctl restart card-dashboard
```

### Useful Commands

```bash
sudo systemctl status card-dashboard      # Check status
sudo systemctl restart card-dashboard     # Restart
sudo journalctl -u card-dashboard -f      # View logs
tail -f /var/log/daily_scrape.log         # Daily scrape logs
```

## Running Tests

```bash
python run_tests.py
```

See [tests/README.md](tests/README.md) for detailed information on the test suite, coverage, and adding new tests.
