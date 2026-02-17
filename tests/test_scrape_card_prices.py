import unittest
import sys
import os
from datetime import datetime

# Add root directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_card_prices import (
    clean_card_name_for_search,
    get_grade_info,
    title_matches_grade,
    build_simplified_query,
    calculate_fair_price
)

class TestScrapeCardPrices(unittest.TestCase):

    def test_get_grade_info(self):
        self.assertEqual(get_grade_info("Connor McDavid [PSA 10]"), ("PSA 10", 10))
        self.assertEqual(get_grade_info("Connor McDavid [PSA 9]"), ("PSA 9", 9))
        self.assertEqual(get_grade_info("Connor McDavid"), (None, None))
        self.assertEqual(get_grade_info("Connor McDavid [BGS 9.5]"), (None, None)) # Only PSA supported currently

    def test_clean_card_name_for_search(self):
        # Basic test
        name = "2015-16 Upper Deck Series 1 #201 - Connor McDavid"
        query = clean_card_name_for_search(name)
        self.assertIn("Connor McDavid", query)
        self.assertIn("#201", query)
        self.assertIn("2015-16", query)
        self.assertIn("-PSA -BGS -SGC -graded", query)

        # Graded card
        name_graded = "2015-16 Upper Deck Series 1 #201 - Connor McDavid [PSA 10]"
        query_graded = clean_card_name_for_search(name_graded)
        self.assertIn("PSA 10", query_graded)
        self.assertIn('-"PSA 9 "', query_graded) # Should exclude other grades (note extra space in code)

        # Variant
        name_variant = "2020-21 Upper Deck Series 1 #201 - Alexis Lafreniere - Red Prism"
        query_variant = clean_card_name_for_search(name_variant)
        self.assertIn("Red Prism", query_variant)

    def test_title_matches_grade(self):
        # PSA 10 - Standard cases
        self.assertTrue(title_matches_grade("2015 Connor McDavid PSA 10 Gem Mint", "PSA 10", 10))
        self.assertFalse(title_matches_grade("2015 Connor McDavid PSA 9 Mint", "PSA 10", 10))
        self.assertFalse(title_matches_grade("2015 Connor McDavid Raw", "PSA 10", 10))

        # PSA 10 - Edge cases
        self.assertFalse(title_matches_grade("2015 Connor McDavid PSA 100 Gem Mint", "PSA 10", 10)) # Partial match inside larger number
        self.assertFalse(title_matches_grade("2015 Connor McDavid PSA 10? No PSA 9", "PSA 10", 10)) # Conflicting grades present
        self.assertTrue(title_matches_grade("2015 Connor McDavid psa 10 Gem Mint", "PSA 10", 10)) # Case insensitive
        self.assertTrue(title_matches_grade("2015 Connor McDavid PSA10 Gem Mint", "PSA 10", 10)) # No space
        self.assertTrue(title_matches_grade("2015 Connor McDavid PSA  10 Gem Mint", "PSA 10", 10)) # Extra space

        # Raw - Standard cases
        self.assertTrue(title_matches_grade("2015 Connor McDavid Young Guns", None, None))
        self.assertFalse(title_matches_grade("2015 Connor McDavid PSA 10", None, None))
        self.assertFalse(title_matches_grade("2015 Connor McDavid BGS 9.5", None, None))

        # Raw - Edge cases
        self.assertFalse(title_matches_grade("2015 Connor McDavid SGC 10", None, None)) # SGC check
        self.assertFalse(title_matches_grade("2015 Connor McDavid GRADED", None, None)) # GRADED keyword
        self.assertTrue(title_matches_grade("2015 Connor McDavid UNGRADED", None, None)) # UNGRADED should be safe

    def test_build_simplified_query(self):
        # 1. Standard raw card
        name = "2015-16 Upper Deck Series 1 #201 - Connor McDavid"
        query = build_simplified_query(name)
        # Expected: Connor McDavid #201 2015-16 -PSA -BGS -SGC -graded
        self.assertIn("Connor McDavid", query)
        self.assertIn("#201", query)
        self.assertIn("2015-16", query)
        self.assertIn("-PSA -BGS -SGC -graded", query)

        # 2. Graded card
        name_graded = "2015-16 Upper Deck Series 1 #201 - Connor McDavid [PSA 10]"
        query_graded = build_simplified_query(name_graded)
        # Expected: Connor McDavid #201 2015-16 "PSA 10"
        self.assertIn("Connor McDavid", query_graded)
        self.assertIn("#201", query_graded)
        self.assertIn("2015-16", query_graded)
        self.assertIn('"PSA 10"', query_graded)
        self.assertNotIn("-PSA", query_graded)

        # 3. Serial numbered card
        name_serial = "2023-24 O-Pee-Chee Platinum - [Base] - Red Prism #201 - Marquee Rookies - Connor Bedard [PSA 9 MINT] #70/199"
        query_serial = build_simplified_query(name_serial)
        # Expected: Connor Bedard #201 2023-24 "PSA 9"
        self.assertIn("Connor Bedard", query_serial)
        self.assertNotIn("#70/199", query_serial) # Serial should be stripped from name part
        self.assertIn("#201", query_serial)
        self.assertIn("2023-24", query_serial)
        self.assertIn('"PSA 9"', query_serial)

        # 4. Multi-part names (Variant handling)
        # Test a case where the player IS the last part, even with many parts.
        name_multipart = "2023-24 Upper Deck Series 1 - [Base] #228 - Young Guns - Simon Edvinsson"
        query_multipart = build_simplified_query(name_multipart)
        self.assertIn("Simon Edvinsson", query_multipart)
        self.assertIn("#228", query_multipart)
        self.assertIn("2023-24", query_multipart)

        # 5. Edge cases
        # No year
        name_noyear = "Upper Deck Series 1 #201 - Connor McDavid"
        query_noyear = build_simplified_query(name_noyear)
        self.assertIn("Connor McDavid", query_noyear)
        self.assertIn("#201", query_noyear)

        # No card number
        name_nonum = "2015-16 Upper Deck Series 1 - Connor McDavid"
        query_nonum = build_simplified_query(name_nonum)
        self.assertIn("Connor McDavid", query_nonum)
        self.assertIn("2015-16", query_nonum)

        # Only player
        name_onlyplayer = "Connor McDavid"
        query_onlyplayer = build_simplified_query(name_onlyplayer)
        self.assertIn("Connor McDavid", query_onlyplayer)

    def test_calculate_fair_price(self):
        # Test basic calculation (stable)
        sales = [
            {'price_val': 100.0, 'days_ago': 1, 'title': 'Card 1', 'sold_date': '2023-10-01'},
            {'price_val': 105.0, 'days_ago': 2, 'title': 'Card 2', 'sold_date': '2023-09-30'},
            {'price_val': 95.0, 'days_ago': 3, 'title': 'Card 3', 'sold_date': '2023-09-29'},
        ]
        fair_price, stats = calculate_fair_price(sales)
        # Median of 95, 100, 105 is 100. Top 3 are all of them.
        # Stable trend => median of top 3 => 100.
        self.assertAlmostEqual(fair_price, 100.0)
        self.assertEqual(stats['trend'], 'stable') # 3 sales falls into the else block which checks simple trend

        # Test outlier removal
        sales_outlier = sales + [{'price_val': 1000.0, 'days_ago': 0, 'title': 'Outlier', 'sold_date': '2023-10-02'}]
        # The 1000 should be removed as > 3x median (median approx 100)
        fair_price_o, stats_o = calculate_fair_price(sales_outlier)
        self.assertAlmostEqual(fair_price_o, 100.0)
        self.assertEqual(stats_o['outliers_removed'], 1)

        # Test Trend Up
        # Need >= 4 sales for trend logic
        sales_trend = [
            {'price_val': 200.0, 'days_ago': 1, 'title': 'T1'},
            {'price_val': 190.0, 'days_ago': 2, 'title': 'T2'}, # Recent avg ~195
            {'price_val': 100.0, 'days_ago': 10, 'title': 'T3'},
            {'price_val': 110.0, 'days_ago': 11, 'title': 'T4'}, # Older avg ~105
        ]
        # pct_change > 10% -> Up
        fair_price_t, stats_t = calculate_fair_price(sales_trend)
        self.assertEqual(stats_t['trend'], 'up')
        # Up -> pick highest of top 3 (200, 190, 110/100 depending on sorting)
        # Top 3 recent: 200, 190, 100 (if sorted by days_ago)
        # Sorted by price: 100, 190, 200. Highest is 200.
        self.assertEqual(fair_price_t, 200.0)

if __name__ == '__main__':
    unittest.main()
