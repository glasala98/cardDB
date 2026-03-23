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
# MIGRATION RULES: Only fast DDL here (ALTER TABLE ADD COLUMN, CREATE TABLE IF NOT EXISTS,
# CREATE INDEX on small tables). NEVER: UPDATE/DELETE on large tables, CREATE INDEX on
# market_raw_sales or market_prices — those block deploys for minutes. Run those via GH Actions.
#
# Removed from deploy (table-scan operations — run via GH Actions instead):
#   migrate_add_graded_data       — UPDATE market_prices with ILIKE across millions of rows
#   migrate_fix_raw_sales_constraint — UPDATE market_raw_sales full table scan + ADD CONSTRAINT
#   migrate_clean_raw_sales_titles   — UPDATE market_raw_sales LIKE scan
#   migrate_clean_boilerplate_titles — DELETE market_raw_sales ILIKE scan
CMD ["sh", "-c", "python migrations/migrate_add_perf_indexes.py && python migrations/migrate_add_sealed_products.py && python migrations/migrate_add_scrape_error_log.py && python migrations/migrate_add_cards_processed.py && python migrations/migrate_add_market_prices_status.py && python migrations/migrate_add_market_raw_sales.py && python migrations/migrate_fix_market_raw_sales.py && python migrations/migrate_add_raw_sales_indexes.py && python migrations/migrate_add_auction_source.py && python migrations/migrate_add_auction_unmatched.py && python migrations/migrate_normalize_raw_sales.py && python migrations/migrate_add_search_indexes.py && python migrations/migrate_add_search_log.py && python migrations/migrate_add_market_prices_sport.py && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
