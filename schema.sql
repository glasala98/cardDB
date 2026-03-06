-- CardDB PostgreSQL Schema
-- Run once against your local PostgreSQL database:
--   psql -U carddb -d carddb -f schema.sql
-- Tables are designed for hard-cutover from CSV/JSON file storage.
-- All market/rookie tables include a `sport` column (default 'NHL') so
-- the same schema supports Young Guns, NBA Prizm, NFL Topps Chrome, etc.

-- ─────────────────────────────────────────────────────────────────────────────
-- USER CARD COLLECTION  (sport-agnostic — personal collection)
-- ─────────────────────────────────────────────────────────────────────────────

-- Active + archived card collection (replaces card_prices_summary.csv +
-- card_archive.csv). Archived cards stay in this table with archived=TRUE.
CREATE TABLE cards (
    id            BIGSERIAL     PRIMARY KEY,
    user_id       TEXT          NOT NULL,
    card_name     TEXT          NOT NULL,
    fair_value    NUMERIC       DEFAULT 0,
    trend         TEXT          DEFAULT 'no data',
    top_3_prices  TEXT          DEFAULT '',
    median_all    NUMERIC       DEFAULT 0,
    min_price     NUMERIC       DEFAULT 0,
    max_price     NUMERIC       DEFAULT 0,
    num_sales     INT           DEFAULT 0,
    tags          TEXT          DEFAULT '',
    cost_basis    NUMERIC       DEFAULT 0,
    purchase_date TEXT          DEFAULT '',   -- stored as YYYY-MM-DD string
    archived      BOOLEAN       NOT NULL DEFAULT FALSE,
    archived_date TIMESTAMPTZ,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, card_name)
);

-- Raw eBay sales + scrape metadata (replaces card_prices_results.json)
CREATE TABLE card_results (
    id              BIGSERIAL     PRIMARY KEY,
    user_id         TEXT          NOT NULL,
    card_name       TEXT          NOT NULL,
    raw_sales       JSONB         NOT NULL DEFAULT '[]',
    scraped_at      TIMESTAMPTZ,
    confidence      TEXT          DEFAULT '',
    image_url       TEXT          DEFAULT '',
    image_hash      TEXT          DEFAULT '',
    image_url_back  TEXT          DEFAULT '',
    search_url      TEXT          DEFAULT '',
    is_estimated    BOOLEAN       DEFAULT FALSE,
    price_source    TEXT          DEFAULT 'direct',
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, card_name)
);

-- Per-card fair-value snapshots over time (replaces price_history.json)
CREATE TABLE card_price_history (
    id        BIGSERIAL   PRIMARY KEY,
    user_id   TEXT        NOT NULL,
    card_name TEXT        NOT NULL,
    date      DATE        NOT NULL,
    price     NUMERIC     NOT NULL,
    num_sales INT         DEFAULT 0,
    UNIQUE (user_id, card_name, date)
);

-- Daily portfolio value snapshots (replaces portfolio_history.json)
CREATE TABLE portfolio_history (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    date        DATE        NOT NULL,
    total_value NUMERIC     NOT NULL,
    total_cards INT         DEFAULT 0,
    avg_value   NUMERIC     DEFAULT 0,
    UNIQUE (user_id, date)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- ROOKIE CARD MARKET DB  (multi-sport)
-- sport column: 'NHL', 'NBA', 'NFL', 'MLB', etc.
-- card_set lives inside row_data (Young Guns, Prizm, Topps Chrome, etc.)
-- ─────────────────────────────────────────────────────────────────────────────

-- Rookie card market database (replaces young_guns.csv).
-- row_data JSONB stores all CSV columns so schema never drifts when scrapers
-- add new columns (e.g. PSA10_Value, BGS95_Value, etc.)
CREATE TABLE rookie_cards (
    id         BIGSERIAL   PRIMARY KEY,
    sport      TEXT        NOT NULL DEFAULT 'NHL',
    player     TEXT        NOT NULL,
    season     TEXT        NOT NULL,
    card_name  TEXT,
    row_data   JSONB       NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (sport, player, season)
);

-- Per-rookie-card price snapshots (replaces yg_price_history.json).
-- graded_data stores nested grade results: {"PSA 10": {fair_value, num_sales}, ...}
CREATE TABLE rookie_price_history (
    id           BIGSERIAL   PRIMARY KEY,
    sport        TEXT        NOT NULL DEFAULT 'NHL',
    player       TEXT        NOT NULL,
    season       TEXT        NOT NULL,
    date         DATE        NOT NULL,
    fair_value   NUMERIC     DEFAULT 0,
    num_sales    INT         DEFAULT 0,
    graded_data  JSONB       DEFAULT '{}',
    UNIQUE (sport, player, season, date)
);

-- Daily rookie market portfolio snapshots (replaces yg_portfolio_history.json)
CREATE TABLE rookie_portfolio_history (
    id            BIGSERIAL   PRIMARY KEY,
    sport         TEXT        NOT NULL DEFAULT 'NHL',
    date          DATE        NOT NULL,
    total_value   NUMERIC     NOT NULL,
    total_cards   INT         DEFAULT 0,
    avg_value     NUMERIC     DEFAULT 0,
    cards_scraped INT         DEFAULT 0,
    UNIQUE (sport, date)
);

-- Raw eBay sales per rookie card (replaces yg_raw_sales.json)
CREATE TABLE rookie_raw_sales (
    id         BIGSERIAL   PRIMARY KEY,
    sport      TEXT        NOT NULL DEFAULT 'NHL',
    player     TEXT        NOT NULL,
    season     TEXT        NOT NULL,
    sold_date  DATE,
    price_val  NUMERIC,
    title      TEXT        DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_rookie_raw_sales ON rookie_raw_sales (sport, player, season);

-- ─────────────────────────────────────────────────────────────────────────────
-- PLAYER STATS  (multi-sport)
-- ─────────────────────────────────────────────────────────────────────────────

-- Player stats per sport (replaces nhl_player_stats.json → players key)
-- data JSONB: {type, position, current_team, nhl_id, current_season, history, bio}
CREATE TABLE player_stats (
    id         BIGSERIAL   PRIMARY KEY,
    sport      TEXT        NOT NULL DEFAULT 'NHL',
    player     TEXT        NOT NULL,
    data       JSONB       NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (sport, player)
);

-- Team standings per sport (replaces nhl_player_stats.json → standings key)
CREATE TABLE standings (
    id         BIGSERIAL   PRIMARY KEY,
    sport      TEXT        NOT NULL DEFAULT 'NHL',
    team       TEXT        NOT NULL,
    data       JSONB       NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (sport, team)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- ANALYTICS  (multi-sport)
-- ─────────────────────────────────────────────────────────────────────────────

-- Price-vs-performance correlation history (replaces yg_correlation_history.json)
CREATE TABLE rookie_correlation_history (
    id    BIGSERIAL PRIMARY KEY,
    sport TEXT      NOT NULL DEFAULT 'NHL',
    date  DATE      NOT NULL,
    data  JSONB     NOT NULL DEFAULT '{}',
    UNIQUE (sport, date)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- GLOBAL CARD CATALOG  (all sports, all sets — foundation for market-wide pricing)
-- Populated by scrape_beckett_catalog.py; grows over time.
-- ─────────────────────────────────────────────────────────────────────────────

-- Master index of every card ever produced across all sports.
-- One row per unique card (sport + year + set + card_number + player + variant).
CREATE TABLE card_catalog (
    id           BIGSERIAL    PRIMARY KEY,
    sport        TEXT         NOT NULL DEFAULT 'NHL',  -- 'NHL','NBA','NFL','MLB'
    year         TEXT         NOT NULL,                -- '2023-24' or '2024'
    brand        TEXT         NOT NULL DEFAULT '',     -- 'Upper Deck','Topps','Panini'
    set_name     TEXT         NOT NULL,                -- 'Series 1','Young Guns','Prizm'
    card_number  TEXT         NOT NULL DEFAULT '',     -- '#531','RC-12'
    player_name  TEXT         NOT NULL,
    team         TEXT         NOT NULL DEFAULT '',
    variant      TEXT         NOT NULL DEFAULT 'Base', -- 'Base','Young Guns','Silver /99'
    print_run    INT,                                  -- NULL=unlimited, 99=/99 parallel
    is_rookie    BOOLEAN      NOT NULL DEFAULT FALSE,
    is_parallel  BOOLEAN      NOT NULL DEFAULT FALSE,
    source       TEXT         NOT NULL DEFAULT 'manual', -- 'beckett','ebay_discovery','manual'
    source_id    TEXT         NOT NULL DEFAULT '',     -- Beckett card ID or external ref
    search_query TEXT         NOT NULL DEFAULT '',     -- pre-built eBay search string
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (sport, year, set_name, card_number, player_name, variant)
);

-- Current market price per card — one row per card, updated on each scrape.
-- prev_value is carried forward from the previous scrape for trend calculation.
CREATE TABLE market_prices (
    id              BIGSERIAL    PRIMARY KEY,
    card_catalog_id BIGINT       NOT NULL REFERENCES card_catalog(id) ON DELETE CASCADE,
    fair_value      NUMERIC      NOT NULL DEFAULT 0,
    prev_value      NUMERIC      NOT NULL DEFAULT 0,
    trend           TEXT         NOT NULL DEFAULT 'no data',
    confidence      TEXT         NOT NULL DEFAULT '',
    num_sales       INT          NOT NULL DEFAULT 0,
    scraped_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (card_catalog_id)
);

-- Append-only price history — one row per card per day scraped.
-- This is the core historic dataset: never update, only INSERT.
CREATE TABLE market_price_history (
    id              BIGSERIAL    PRIMARY KEY,
    card_catalog_id BIGINT       NOT NULL REFERENCES card_catalog(id) ON DELETE CASCADE,
    scraped_at      DATE         NOT NULL DEFAULT CURRENT_DATE,
    fair_value      NUMERIC      NOT NULL DEFAULT 0,
    confidence      TEXT         NOT NULL DEFAULT '',
    num_sales       INT          NOT NULL DEFAULT 0,
    top_3_prices    TEXT         NOT NULL DEFAULT '',
    min_price       NUMERIC      NOT NULL DEFAULT 0,
    max_price       NUMERIC      NOT NULL DEFAULT 0,
    source          TEXT         NOT NULL DEFAULT 'ebay',
    UNIQUE (card_catalog_id, scraped_at)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- PERSONAL COLLECTION  (ownership layer — links users to card_catalog entries)
-- ─────────────────────────────────────────────────────────────────────────────

-- One row per owned card+grade combination per user.
-- Allows the same card to be tracked at multiple grades (e.g. Raw + PSA 10).
-- card_catalog_id is the foreign key so all card metadata stays in card_catalog.
CREATE TABLE collection (
    id              BIGSERIAL    PRIMARY KEY,
    user_id         TEXT         NOT NULL,
    card_catalog_id BIGINT       NOT NULL REFERENCES card_catalog(id) ON DELETE CASCADE,
    grade           TEXT         NOT NULL DEFAULT 'Raw',
    quantity        INT          NOT NULL DEFAULT 1,
    cost_basis      NUMERIC      DEFAULT NULL,
    purchase_date   DATE         DEFAULT NULL,
    notes           TEXT         NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, card_catalog_id, grade)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- INDEXES
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX idx_cards_user_id              ON cards (user_id);
CREATE INDEX idx_cards_archived             ON cards (user_id, archived);
CREATE INDEX idx_card_results_user_id       ON card_results (user_id);
CREATE INDEX idx_card_price_history_user    ON card_price_history (user_id, card_name);
CREATE INDEX idx_portfolio_history_user     ON portfolio_history (user_id, date);
CREATE INDEX idx_rookie_cards_sport         ON rookie_cards (sport, player, season);
CREATE INDEX idx_rookie_price_history       ON rookie_price_history (sport, player, season);
CREATE INDEX idx_rookie_portfolio_history   ON rookie_portfolio_history (sport, date);
CREATE INDEX idx_player_stats_sport         ON player_stats (sport, player);
CREATE INDEX idx_standings_sport            ON standings (sport, team);
CREATE INDEX idx_rookie_correlation_history ON rookie_correlation_history (sport, date);

-- Card catalog indexes
CREATE INDEX idx_card_catalog_sport_year    ON card_catalog (sport, year);
CREATE INDEX idx_card_catalog_player        ON card_catalog (sport, player_name);
CREATE INDEX idx_card_catalog_set           ON card_catalog (sport, year, set_name);
CREATE INDEX idx_card_catalog_rookie        ON card_catalog (sport, is_rookie) WHERE is_rookie = TRUE;
CREATE INDEX idx_market_prices_catalog      ON market_prices (card_catalog_id);
CREATE INDEX idx_market_price_history_card  ON market_price_history (card_catalog_id, scraped_at);
CREATE INDEX idx_market_price_history_date  ON market_price_history (scraped_at);
CREATE INDEX idx_collection_user            ON collection (user_id);
CREATE INDEX idx_collection_catalog        ON collection (user_id, card_catalog_id);
