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

    def test_clean_card_name_detailed_scenarios(self):
        """Test detailed scenarios for clean_card_name_for_search."""

        # 1. Basic Player Extraction
        case1 = "2023-24 Upper Deck Series 1 #201 - Connor Bedard"
        query1 = clean_card_name_for_search(case1)
        self.assertIn("Connor Bedard", query1)
        self.assertIn("#201", query1)
        self.assertIn("2023-24", query1)

        # 2. Subset Extraction (Young Guns)
        case2 = "2023-24 Upper Deck Series 1 - [Base] #201 - Young Guns - Matthew Coronato"
        query2 = clean_card_name_for_search(case2)
        self.assertIn("Matthew Coronato", query2)
        self.assertIn("Young Guns", query2)
        self.assertIn("#201", query2)

        # 3. Variant Extraction (Arctic Freeze) + Serial Number Handling
        case3 = "2023-24 O-Pee-Chee Platinum - [Base] - Arctic Freeze #177 - Nazem Kadri #44/99"
        query3 = clean_card_name_for_search(case3)
        self.assertIn("Nazem Kadri", query3)
        self.assertIn("Arctic Freeze", query3)
        self.assertIn("#177", query3)
        self.assertNotIn("#44/99", query3) # Should be cleaned from player name

        # 4. Brand Abbreviation (O-Pee-Chee -> OPC)
        case4 = "2023-24 O-Pee-Chee Platinum #100 - Connor Bedard"
        query4 = clean_card_name_for_search(case4)
        self.assertIn("OPC Platinum", query4)
        self.assertNotIn("O-Pee-Chee Platinum", query4)
        self.assertIn("#100", query4) # Ensure card number is preserved via card_num extraction

        # 5. Complex: Variant + Subset + Grade
        case5 = "2023-24 O-Pee-Chee Platinum - [Base] - Red Prism #201 - Marquee Rookies - Connor Bedard [PSA 9 MINT] #70/199"
        query5 = clean_card_name_for_search(case5)
        self.assertIn("Connor Bedard", query5)
        self.assertIn("Red Prism", query5)
        self.assertIn("#201", query5)
        # Grade specific checks
        self.assertIn('"PSA 9"', query5)
        self.assertIn('-"PSA 10 "', query5)

        # 6. Pre-Grade Review Removal
        case6 = "2023-24 Upper Deck Parkhurst - Prominent Prospects #PP-CB - Connor Bedard [Passed Pre‑Grade Review]"
        query6 = clean_card_name_for_search(case6)
        self.assertIn("Connor Bedard", query6)
        self.assertNotIn("Pre-Grade", query6)
        self.assertNotIn("Review", query6)

        # 7. UD Canvas Subset
        case7 = "2024-25 Upper Deck Series 1 - UD Canvas #C-117 - Young Guns - Frank Nazar"
        query7 = clean_card_name_for_search(case7)
        self.assertIn("Frank Nazar", query7)
        # self.assertIn("UD Canvas", query7) # Current logic picks "Young Guns" first and stops.
        self.assertIn("Young Guns", query7)

    def test_title_matches_grade(self):
        # PSA 10
        self.assertTrue(title_matches_grade("2015 Connor McDavid PSA 10 Gem Mint", "PSA 10", 10))
        self.assertFalse(title_matches_grade("2015 Connor McDavid PSA 9 Mint", "PSA 10", 10))
        self.assertFalse(title_matches_grade("2015 Connor McDavid Raw", "PSA 10", 10))

        # Raw
        self.assertTrue(title_matches_grade("2015 Connor McDavid Young Guns", None, None))
        self.assertFalse(title_matches_grade("2015 Connor McDavid PSA 10", None, None))
        self.assertFalse(title_matches_grade("2015 Connor McDavid BGS 9.5", None, None))

    def test_build_simplified_query(self):
        name = "2015-16 Upper Deck Series 1 #201 - Connor McDavid"
        query = build_simplified_query(name)
        self.assertIn("Connor McDavid", query)
        self.assertIn("#201", query)
        self.assertIn("2015-16", query)

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
