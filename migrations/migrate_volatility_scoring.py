#!/usr/bin/env python3 -u
"""
Migration: Volatility scoring system

Creates:
  - players table           — player tiers (S/A/B/C) manageable from admin UI
  - player_score column     — score from player tier lookup
  - attr_score column       — score from card attributes (variant/print_run/is_rookie)
  - set_score column        — score from set/brand prestige
  - volatility_score column — sum of above three; drives scrape_tier assignment
  - fn_score_card()         — Postgres function that computes all scores for one card
  - trg_score_on_insert     — BEFORE INSERT OR UPDATE trigger on card_catalog
  - trg_rescore_on_player   — AFTER INSERT OR UPDATE trigger on players table

How new cards get tiered:
  Any INSERT into card_catalog fires trg_score_on_insert, which sets all four
  score columns and scrape_tier before the row is committed.  No batch job needed
  for new cards — they arrive correctly tiered from the first moment.

When a player's tier changes in the players table, trg_rescore_on_player
fires and UPDATE-rescores every card that player appears on, then reassigns
their scrape_tier.  Promotes/demotes propagate within a single transaction.

Idempotent: safe to run multiple times.
"""

import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass
from db import get_db


MIGRATION_SQL = """
-- ── 1. players table ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS players (
    id          BIGSERIAL   PRIMARY KEY,
    player_name TEXT        NOT NULL,
    sport       TEXT        NOT NULL DEFAULT 'ALL',  -- NHL/NBA/NFL/MLB/ALL
    player_tier CHAR(1)     NOT NULL DEFAULT 'C'     -- S/A/B/C
        CHECK (player_tier IN ('S','A','B','C')),
    notes       TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (player_name, sport)
);

-- ── 2. Scoring columns on card_catalog ───────────────────────────────────────
ALTER TABLE card_catalog
    ADD COLUMN IF NOT EXISTS player_score     SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS attr_score       SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS set_score        SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS volatility_score SMALLINT NOT NULL DEFAULT 0;

-- ── 3. Core scoring function ──────────────────────────────────────────────────
-- Computes player_score, attr_score, set_score, volatility_score and
-- scrape_tier for a single card and writes them in one UPDATE.
-- Called by both triggers and by assign_catalog_tiers.py --all.
CREATE OR REPLACE FUNCTION fn_score_card(p_id BIGINT) RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
    c           card_catalog%ROWTYPE;
    p_score     SMALLINT := 0;
    a_score     SMALLINT := 0;
    s_score     SMALLINT := 0;
    v_score     SMALLINT;
    v_tier      TEXT;
BEGIN
    SELECT * INTO c FROM card_catalog WHERE id = p_id;
    IF NOT FOUND THEN RETURN; END IF;

    -- ── Player score ──────────────────────────────────────────────────────────
    -- Match by exact name + sport, or name + ALL (for cross-sport players like
    -- Bo Jackson, Deion Sanders, or Tiger Woods in multi-sport sets).
    SELECT COALESCE(
        CASE player_tier
            WHEN 'S' THEN 50
            WHEN 'A' THEN 30
            WHEN 'B' THEN 10
            ELSE 0
        END, 0)
    INTO p_score
    FROM players
    WHERE player_name = c.player_name
      AND (sport = c.sport OR sport = 'ALL')
    ORDER BY player_tier  -- S < A < B < C alphabetically, but S wins because 50>30
    LIMIT 1;
    IF p_score IS NULL THEN p_score := 0; END IF;

    -- ── Attribute score ───────────────────────────────────────────────────────
    -- Apex +50: true 1/1, logoman, rookie patch auto
    IF c.print_run = 1 THEN
        a_score := 50;
    ELSIF c.variant ILIKE '%logoman%' THEN
        a_score := 50;
    ELSIF c.is_rookie
          AND (c.variant ILIKE '%auto%' OR c.variant ILIKE '%rpa%')
          AND c.variant ILIKE '%patch%' THEN
        a_score := 50;
    -- Scarce +30: numbered ≤99, standalone auto/patch/relic
    ELSIF c.print_run IS NOT NULL AND c.print_run <= 99 THEN
        a_score := 30;
    ELSIF c.variant ILIKE '%auto%'
       OR c.variant ILIKE '%autograph%'
       OR c.variant ILIKE '%rpa%'
       OR c.variant ILIKE '%patch%'
       OR c.variant ILIKE '%relic%'
       OR c.variant ILIKE '%jersey%'
       OR c.variant ILIKE '%signature%'
       OR c.variant ILIKE '%signed%'
       OR c.variant ILIKE '%booklet%' THEN
        a_score := 30;
    -- Notable +10: numbered 100-499, rookie cards, unnumbered parallels
    ELSIF c.print_run IS NOT NULL AND c.print_run <= 499 THEN
        a_score := 10;
    ELSIF c.is_rookie THEN
        a_score := 10;
    ELSIF c.is_parallel THEN
        a_score := 10;
    ELSE
        a_score := 0;
    END IF;

    -- ── Set score ─────────────────────────────────────────────────────────────
    -- Flagship +20
    IF c.set_name ILIKE '%National Treasures%'
    OR c.set_name ILIKE '%Flawless%'
    OR c.set_name ILIKE '%Prizm%'
    OR c.set_name ILIKE '%Topps Chrome%'
    OR c.set_name ILIKE '%Bowman Chrome%'
    OR c.set_name ILIKE '%Topps Chrome Black%'
    OR c.variant  ILIKE '%Young Guns%'
    OR c.set_name ILIKE '%The Cup%'
    OR c.set_name ILIKE '%Ultimate Collection%'
    OR c.set_name ILIKE '%Immaculate%'
    OR c.set_name ILIKE '%SP Authentic%' THEN
        s_score := 20;
    -- Mid-tier +10
    ELSIF c.set_name ILIKE '%Select%'
       OR c.set_name ILIKE '%Mosaic%'
       OR c.set_name ILIKE '%Optic%'
       OR c.set_name ILIKE '%Contenders%'
       OR c.set_name ILIKE '%Bowman Draft%'
       OR c.set_name ILIKE '%Bowman 1st%'
       OR c.set_name ILIKE '%Bowman%'
       OR c.set_name ILIKE '%Topps Update%'
       OR c.set_name ILIKE '%Topps Series%'
       OR c.set_name ILIKE '%Topps Finest%'
       OR c.set_name ILIKE '%Stadium Club%'
       OR c.set_name ILIKE '%Heritage%'
       OR c.set_name ILIKE '%Donruss Optic%' THEN
        s_score := 10;
    ELSE
        s_score := 0;
    END IF;

    -- ── Combine and map to tier ───────────────────────────────────────────────
    v_score := p_score + a_score + s_score;

    v_tier := CASE
        WHEN v_score >= 100 THEN 'elite'    -- every 6h
        WHEN v_score >= 70  THEN 'staple'   -- daily
        WHEN v_score >= 40  THEN 'premium'  -- weekly
        WHEN v_score >= 10  THEN 'stars'    -- monthly
        ELSE                     'base'     -- on-demand
    END;

    UPDATE card_catalog
    SET player_score     = p_score,
        attr_score       = a_score,
        set_score        = s_score,
        volatility_score = v_score,
        scrape_tier      = v_tier
    WHERE id = p_id;
END;
$$;

-- ── 4. Trigger: score every new/updated card immediately ──────────────────────
CREATE OR REPLACE FUNCTION fn_trg_score_card() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    -- Compute inline (can't call fn_score_card here — it does a separate
    -- UPDATE which is not allowed in a BEFORE trigger on the same row).
    -- We replicate the logic so NEW is mutated before the row is written.

    -- Player score
    SELECT COALESCE(CASE player_tier WHEN 'S' THEN 50 WHEN 'A' THEN 30 WHEN 'B' THEN 10 ELSE 0 END, 0)
    INTO NEW.player_score
    FROM players
    WHERE player_name = NEW.player_name
      AND (sport = NEW.sport OR sport = 'ALL')
    LIMIT 1;
    IF NEW.player_score IS NULL THEN NEW.player_score := 0; END IF;

    -- Attr score
    NEW.attr_score := CASE
        WHEN NEW.print_run = 1 THEN 50
        WHEN NEW.variant ILIKE '%logoman%' THEN 50
        WHEN NEW.is_rookie
             AND (NEW.variant ILIKE '%auto%' OR NEW.variant ILIKE '%rpa%')
             AND NEW.variant ILIKE '%patch%' THEN 50
        WHEN NEW.print_run IS NOT NULL AND NEW.print_run <= 99 THEN 30
        WHEN NEW.variant ILIKE '%auto%'
          OR NEW.variant ILIKE '%autograph%'
          OR NEW.variant ILIKE '%rpa%'
          OR NEW.variant ILIKE '%patch%'
          OR NEW.variant ILIKE '%relic%'
          OR NEW.variant ILIKE '%jersey%'
          OR NEW.variant ILIKE '%signature%'
          OR NEW.variant ILIKE '%signed%'
          OR NEW.variant ILIKE '%booklet%' THEN 30
        WHEN NEW.print_run IS NOT NULL AND NEW.print_run <= 499 THEN 10
        WHEN NEW.is_rookie  THEN 10
        WHEN NEW.is_parallel THEN 10
        ELSE 0
    END;

    -- Set score
    NEW.set_score := CASE
        WHEN NEW.set_name ILIKE '%National Treasures%'
          OR NEW.set_name ILIKE '%Flawless%'
          OR NEW.set_name ILIKE '%Prizm%'
          OR NEW.set_name ILIKE '%Topps Chrome%'
          OR NEW.set_name ILIKE '%Bowman Chrome%'
          OR NEW.set_name ILIKE '%Topps Chrome Black%'
          OR NEW.variant  ILIKE '%Young Guns%'
          OR NEW.set_name ILIKE '%The Cup%'
          OR NEW.set_name ILIKE '%Ultimate Collection%'
          OR NEW.set_name ILIKE '%Immaculate%'
          OR NEW.set_name ILIKE '%SP Authentic%' THEN 20
        WHEN NEW.set_name ILIKE '%Select%'
          OR NEW.set_name ILIKE '%Mosaic%'
          OR NEW.set_name ILIKE '%Optic%'
          OR NEW.set_name ILIKE '%Contenders%'
          OR NEW.set_name ILIKE '%Bowman Draft%'
          OR NEW.set_name ILIKE '%Bowman 1st%'
          OR NEW.set_name ILIKE '%Bowman%'
          OR NEW.set_name ILIKE '%Topps Update%'
          OR NEW.set_name ILIKE '%Topps Series%'
          OR NEW.set_name ILIKE '%Topps Finest%'
          OR NEW.set_name ILIKE '%Stadium Club%'
          OR NEW.set_name ILIKE '%Heritage%'
          OR NEW.set_name ILIKE '%Donruss Optic%' THEN 10
        ELSE 0
    END;

    NEW.volatility_score := NEW.player_score + NEW.attr_score + NEW.set_score;

    NEW.scrape_tier := CASE
        WHEN NEW.volatility_score >= 100 THEN 'elite'
        WHEN NEW.volatility_score >= 70  THEN 'staple'
        WHEN NEW.volatility_score >= 40  THEN 'premium'
        WHEN NEW.volatility_score >= 10  THEN 'stars'
        ELSE                                  'base'
    END;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_score_on_insert ON card_catalog;
CREATE TRIGGER trg_score_on_insert
BEFORE INSERT OR UPDATE OF player_name, variant, print_run, is_rookie, is_parallel, set_name
ON card_catalog
FOR EACH ROW EXECUTE FUNCTION fn_trg_score_card();

-- ── 5. Trigger: when a player's tier changes, rescore all their cards ─────────
CREATE OR REPLACE FUNCTION fn_trg_rescore_player() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    -- Only fire if the tier actually changed (or it's a new player row)
    IF TG_OP = 'UPDATE' AND NEW.player_tier = OLD.player_tier THEN
        RETURN NEW;
    END IF;

    PERFORM fn_score_card(id)
    FROM card_catalog
    WHERE player_name = NEW.player_name
      AND (sport = NEW.sport OR NEW.sport = 'ALL');

    RETURN NEW;
END;
$$;

-- ── 5b. Replace fn_trg_rescore_player with a batch UPDATE version ─────────────
-- The original called fn_score_card(id) per card — for a player with 50k cards
-- (LeBron, Jordan) that means 50k individual function calls in one transaction.
-- This version does a single UPDATE for all of a player's cards.
CREATE OR REPLACE FUNCTION fn_trg_rescore_player() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    p_score SMALLINT;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.player_tier = OLD.player_tier THEN
        RETURN NEW;
    END IF;

    p_score := CASE NEW.player_tier
        WHEN 'S' THEN 50 WHEN 'A' THEN 30 WHEN 'B' THEN 10 ELSE 0
    END;

    UPDATE card_catalog
    SET player_score     = p_score,
        volatility_score = p_score + attr_score + set_score,
        scrape_tier = CASE
            WHEN (p_score + attr_score + set_score) >= 100 THEN 'elite'
            WHEN (p_score + attr_score + set_score) >= 70  THEN 'staple'
            WHEN (p_score + attr_score + set_score) >= 40  THEN 'premium'
            WHEN (p_score + attr_score + set_score) >= 10  THEN 'stars'
            ELSE 'base'
        END
    WHERE player_name = NEW.player_name
      AND (sport = NEW.sport OR NEW.sport = 'ALL');

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_rescore_on_player ON players;
CREATE TRIGGER trg_rescore_on_player
AFTER INSERT OR UPDATE OF player_tier ON players
FOR EACH ROW EXECUTE FUNCTION fn_trg_rescore_player();

-- ── 6. Index for player name lookups ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_card_catalog_player_name
    ON card_catalog (player_name);

CREATE INDEX IF NOT EXISTS idx_players_name_sport
    ON players (player_name, sport);
"""


def run():
    print("Running migration: volatility scoring system...")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_SQL)
        conn.commit()
    print("  ✓ players table created")
    print("  ✓ scoring columns added to card_catalog")
    print("  ✓ fn_score_card() function created")
    print("  ✓ trg_score_on_insert trigger created")
    print("  ✓ trg_rescore_on_player trigger created")
    print("  ✓ indexes created")
    print()
    print("Next steps:")
    print("  1. Run scripts/seed_player_tiers.py to populate S/A tier players")
    print("  2. Run scripts/assign_catalog_tiers.py --all to score existing cards")
    print("  3. Create .github/workflows/catalog_tier_elite.yml for 6h elite scraping")


if __name__ == '__main__':
    run()
