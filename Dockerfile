FROM python:3.11-slim

# Install Node.js 20
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install and build frontend
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install

COPY . .
RUN cd frontend && npm run build

EXPOSE 8000
# Run DB migrations on every deploy (all scripts use IF NOT EXISTS — safe to re-run)
CMD ["sh", "-c", "python migrate_add_graded_data.py && python migrate_add_perf_indexes.py && python migrate_add_sealed_products.py && python migrate_add_scrape_error_log.py && python migrate_add_cards_processed.py && python migrate_add_market_prices_status.py && python migrate_add_market_raw_sales.py && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
