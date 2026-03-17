"""Shared catalog matcher for auction house sale titles.

Given a raw listing title from any auction source, finds the best matching
card_catalog row using a 3-tier cascade:

  Tier 1 — Exact SQL (player_name + year)       fastest, most accurate
  Tier 2 — Trigram similarity on player_name    handles typos/abbreviations
  Tier 3 — tsvector full-text search            handles word-order variation

Matched sales are saved to market_raw_sales.
Unmatched sales are saved to auction_unmatched for admin review.

Usage:
    from auction_match import CatalogMatcher
    matcher = CatalogMatcher(conn)
    matcher.process_sale({
        "title":             "2019-20 Panini Prizm LeBron James Silver PSA 10",
        "price_val":         210.00,
        "sold_date":         "2024-11-15",
        "source":            "goldin",
        "lot_url":           "https://goldinauctions.com/lot/12345",
        "lot_id":            "12345",
        "is_auction":        True,
        "hammer_price":      180.00,
        "buyer_premium_pct": 16.67,
        "raw_metadata":      {"auction_id": "abc123"},
    })
    matcher.flush()
"""

import re
import logging
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras

from auction_title_parser import parse_title

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_YEAR_RE = re.compile(r'\b(19|20)\d{2}(?:-\d{2,4})?\b')

_STRIP_TOKENS = re.compile(
    r'\b(RC|SP|SSP|AU|Auto|Autograph|Rookie|Refractor|Prizm|Chrome|Topps|Panini|'
    r'Upper|Deck|Optic|Select|Mosaic|Bowman|Donruss|Fleer|Score|Skybox|Ultra|'
    r'PSA|BGS|SGC|CGC|HGA|CSG|GEM|Mint|Graded|Numbered|Patch|Relic|Jersey|'
    r'Card|Cards|Trading|Sports|Baseball|Basketball|Football|Hockey|Soccer|'
    r'1st|Edition|Series|Base|Silver|Gold|Blue|Red|Green|Orange|Purple|Black|'
    r'White|Rainbow|Holo|Foil|Parallel|Insert|Short|Print|Run|Lot)\b',
    re.IGNORECASE,
)
_CARD_NUM_RE = re.compile(r'#\d+(/\d+)?')
_GRADE_RE    = re.compile(r'\b(PSA|BGS|SGC|CGC|HGA|CSG)\s*\d+(\.\d+)?\b', re.IGNORECASE)
_SERIAL_RE   = re.compile(r'/\d+')


def _extract_year(title: str) -> Optional[str]:
    m = _YEAR_RE.search(title)
    return m.group(0) if m else None


def _extract_player_name(title: str) -> str:
    t = _CARD_NUM_RE.sub(' ', title)
    t = _GRADE_RE.sub(' ', t)
    t = _YEAR_RE.sub(' ', t)
    t = _SERIAL_RE.sub(' ', t)
    t = _STRIP_TOKENS.sub(' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    words = [w for w in t.split() if w and w[0].isupper() and len(w) > 1]
    return ' '.join(words[:3])


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class CatalogMatcher:
    MATCH_BATCH   = 200
    UNMATCH_BATCH = 200

    def __init__(self, conn, min_similarity: float = 0.25, dry_run: bool = False):
        self.conn           = conn
        self.min_similarity = min_similarity
        self.dry_run        = dry_run
        self._matched:   list = []
        self._unmatched: list = []
        self.stats = {"matched": 0, "unmatched": 0, "skipped": 0}

    def process_sale(self, sale: dict) -> Optional[int]:
        title = (sale.get('title') or '').strip()
        if not title:
            self.stats["skipped"] += 1
            return None

        catalog_id = self._find_match(title)

        if catalog_id:
            self.stats["matched"] += 1
            self._matched.append((catalog_id, sale))
        else:
            self.stats["unmatched"] += 1
            self._unmatched.append(sale)

        if len(self._matched) >= self.MATCH_BATCH:
            self._flush_matched()
        if len(self._unmatched) >= self.UNMATCH_BATCH:
            self._flush_unmatched()

        return catalog_id

    def flush(self):
        self._flush_matched()
        self._flush_unmatched()

    def print_stats(self):
        total = self.stats['matched'] + self.stats['unmatched']
        rate  = round(self.stats['matched'] / total * 100, 1) if total else 0
        print(f"  Matched:   {self.stats['matched']:,} ({rate}%)")
        print(f"  Unmatched: {self.stats['unmatched']:,}")
        print(f"  Skipped:   {self.stats['skipped']:,}")

    # ------------------------------------------------------------------
    # 3-tier cascade
    # ------------------------------------------------------------------

    def _find_match(self, title: str) -> Optional[int]:
        player = _extract_player_name(title)
        year   = _extract_year(title)
        if not player:
            return None
        return (self._tier1(player, year, title)
                or self._tier2(player, year)
                or self._tier3(title))

    def _tier1(self, player: str, year: Optional[str], title: str) -> Optional[int]:
        with self.conn.cursor() as cur:
            params = [f'%{player}%']
            sql = """
                SELECT cc.id, mp.num_sales
                FROM card_catalog cc
                LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
                WHERE cc.player_name ILIKE %s
            """
            if year:
                sql += " AND cc.year LIKE %s"
                params.append(f'{year[:4]}%')
            sql += " ORDER BY mp.num_sales DESC NULLS LAST LIMIT 10"
            cur.execute(sql, params)
            rows = cur.fetchall()

        if len(rows) == 1:
            return rows[0][0]
        if len(rows) > 1:
            return self._score_candidates([r[0] for r in rows], title)
        return None

    def _tier2(self, player: str, year: Optional[str]) -> Optional[int]:
        with self.conn.cursor() as cur:
            params = [player, player]
            sql = """
                SELECT cc.id, similarity(cc.player_name, %s) AS sim
                FROM card_catalog cc
                WHERE cc.player_name %% %s
            """
            if year:
                sql += " AND cc.year LIKE %s"
                params.append(f'{year[:4]}%')
            sql += " ORDER BY sim DESC LIMIT 10"
            cur.execute(sql, params)
            rows = cur.fetchall()

        if not rows or rows[0][1] < self.min_similarity:
            return None
        if len(rows) == 1 or (rows[0][1] - rows[1][1] > 0.15):
            return rows[0][0]
        return None

    def _tier3(self, title: str) -> Optional[int]:
        words = [w for w in title.split() if len(w) > 3 and w.isalpha()]
        if not words:
            return None
        query = ' & '.join(words[:6])
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT id, ts_rank(search_vector, to_tsquery('english', %s)) AS rank
                    FROM card_catalog
                    WHERE search_vector @@ to_tsquery('english', %s)
                    ORDER BY rank DESC LIMIT 5
                """, [query, query])
                rows = cur.fetchall()
        except Exception:
            return None

        if not rows:
            return None
        if len(rows) == 1 or (rows[0][1] - rows[1][1] > 0.1):
            return rows[0][0]
        return None

    def _score_candidates(self, catalog_ids: list, title: str) -> Optional[int]:
        if not catalog_ids:
            return None
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT id, set_name, brand, variant, scrape_tier
                FROM card_catalog WHERE id = ANY(%s)
            """, [catalog_ids])
            candidates = cur.fetchall()

        title_lower = title.lower()
        best_id = best_score = None
        tier_bonus = {'staple': 2, 'premium': 1, 'stars': 0, 'base': -1}

        for c in candidates:
            tokens = ' '.join(filter(None, [c['brand'], c['set_name'], c['variant']])).lower().split()
            score  = sum(1 for t in tokens if t in title_lower)
            score += tier_bonus.get(c['scrape_tier'], 0)
            if best_score is None or score > best_score:
                best_score, best_id = score, c['id']

        return best_id if best_score and best_score > 0 else None

    # ------------------------------------------------------------------
    # Batch writes
    # ------------------------------------------------------------------

    def _flush_matched(self):
        if not self._matched:
            return
        if self.dry_run:
            for cid, sale in self._matched:
                log.info(f"[DRY RUN] matched -> catalog_id={cid}: {sale.get('title','')[:60]}")
            self._matched = []
            return

        from db import save_raw_sales
        for catalog_id, sale in self._matched:
            try:
                save_raw_sales(catalog_id, [sale], conn=self.conn,
                               source=sale.get('source', 'unknown'))
            except Exception as e:
                log.warning(f"save_raw_sales error: {e}")
        try:
            self.conn.commit()
        except Exception:
            self.conn.rollback()
        self._matched = []

    def _flush_unmatched(self):
        if not self._unmatched:
            return
        if self.dry_run:
            for sale in self._unmatched:
                log.info(f"[DRY RUN] unmatched: {sale.get('title','')[:60]}")
            self._unmatched = []
            return

        rows = [(
            sale.get('source', 'unknown'),
            (sale.get('title') or '')[:500],
            float(sale.get('price_val') or 0),
            sale.get('sold_date'),
            (sale.get('lot_url') or '')[:2000],
            'no_match',
        ) for sale in self._unmatched]

        try:
            with self.conn.cursor() as cur:
                psycopg2.extras.execute_values(cur, """
                    INSERT INTO auction_unmatched
                        (source, title, price_val, sold_date, raw_url, reason)
                    VALUES %s
                """, rows)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            log.warning(f"flush_unmatched error: {e}")
        self._unmatched = []
