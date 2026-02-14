# Sports Card Analytics Dashboard

This project is a comprehensive toolkit for scraping sports card prices from eBay, storing them, and visualizing the data in an interactive dashboard. It includes features for analyzing card photos using Anthropic's Claude AI to extract details and validate images.

## Features

-   **eBay Scraper**: Scrapes sold listings from eBay to estimate fair market value for cards.
-   **Analytics Dashboard**: Visualizes collection value, market trends, and top cards using Streamlit and Plotly.
-   **AI Card Analysis**: Uses Claude 3.5 Sonnet to analyze photos of cards, extract details (player, set, year, grade), and validate if the image is a sports card.
-   **Collection Management**: Add new cards, track their value over time, and manage your portfolio.

## Prerequisites

-   **Python 3.9+**: Ensure you have Python installed.
-   **Google Chrome**: The scraper uses Selenium with a Chrome driver, so Google Chrome must be installed.
-   **Anthropic API Key**: Required for the AI card analysis feature.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd <repository_name>
    ```

2.  **Create and activate a virtual environment** (recommended):
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Set up your Anthropic API key as an environment variable.

-   **Linux/macOS**:
    ```bash
    export ANTHROPIC_API_KEY="your_api_key_here"
    ```
-   **Windows (PowerShell)**:
    ```powershell
    $env:ANTHROPIC_API_KEY="your_api_key_here"
    ```

## Usage

### 1. Scraping Card Prices

To scrape prices for a list of cards defined in `hockey_cards.csv`:

```bash
python scrape_card_prices.py
```

This will:
-   Read card names from `hockey_cards.csv`.
-   Scrape eBay for sold listings.
-   Save detailed results to `card_prices_results.json`.
-   Save a summary to `card_prices_summary.csv`.

### 2. Running the Dashboard

To launch the interactive dashboard:

```bash
streamlit run dashboard.py
```

This will open the dashboard in your default web browser (usually at `http://localhost:8501`).

**Dashboard Features:**
-   **Analytics Tab**: View value distribution, trends, and charts.
-   **Card Ledger Tab**: View and edit your card collection, add new cards, and update prices.
-   **Scan Card**: Upload a photo of a card to automatically extract details using AI.

## Project Structure

-   `scrape_card_prices.py`: Main script for scraping eBay data.
-   `dashboard.py`: Streamlit application for the dashboard.
-   `card_scraper.py`: Helper class for Selenium scraping (used by `scrape_card_prices.py`).
-   `hockey_cards.csv`: Input file containing the list of cards to scrape.
-   `card_prices_summary.csv`: The "database" file storing scraped prices and collection data.

## Running Tests

To run the unit tests for the project:

```bash
python run_tests.py
```

This will execute all tests located in the `tests/` directory.

### Frontend Verification

For frontend changes, we use Playwright to verify the UI.

1.  **Install Playwright**:
    ```bash
    pip install playwright
    playwright install
    ```

2.  **Start the Dashboard**:
    ```bash
    streamlit run dashboard.py
    ```

3.  **Run Verification Script**:
    Create a script (e.g., `verify_dashboard.py`) to test your changes. Example:

    ```python
    from playwright.sync_api import sync_playwright

    def run(playwright):
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://localhost:8501")
        page.screenshot(path="dashboard_verification.png")
        browser.close()

    with sync_playwright() as playwright:
        run(playwright)
    ```

    Run it with `python verify_dashboard.py` and check the screenshot.

## Deployment to Production

To host this project at **https://southwestsportscards.ca/** (IP: `104.236.65.233`), follow these steps.

### 1. Copy Files to the Server

From your local machine (where this repository is located), run the following command to copy the necessary files to the server:

```bash
scp -r dashboard_prod.py card_prices_summary.csv requirements.txt deploy/ root@104.236.65.233:/root/
```

### 2. Run the Setup Script

SSH into the server and run the automated setup script. This will install Python, Nginx, configure the firewall, and set up the SSL certificate.

```bash
ssh root@104.236.65.233
cd /root
sudo bash deploy/setup.sh southwestsportscards.ca
```

### 3. Updating Data

To update the card prices on the server after running the scraper locally:

```bash
scp card_prices_summary.csv root@104.236.65.233:/opt/card-dashboard/
ssh root@104.236.65.233 "chown cardapp:cardapp /opt/card-dashboard/card_prices_summary.csv && sudo systemctl restart card-dashboard"
```
