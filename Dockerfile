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
# Schema is fully applied — migrations skipped to unblock startup.
# Re-add new migrations here only when adding new columns/tables.
CMD ["sh", "-c", "python migrations/migrate_add_raw_sales_created_at.py && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
