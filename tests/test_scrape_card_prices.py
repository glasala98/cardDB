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

    def create_sales(self, prices):
        """Helper to create sales data with minimal required fields."""
        sales = []
        for i, p in enumerate(prices):
            sales.append({
                'price_val': float(p),
                'days_ago': i, # Different days to allow sorting/trending logic to work if needed
                'title': f'Sale {i}',
                'sold_date': '2023-01-01'
            })
        return sales

    def test_calculate_fair_price_low_outlier(self):
        # Median of [10, 100, 100, 100] is 100.
        # Cutoffs: 33.33 to 300.
        # 10 is < 33.33, should be removed.
        prices = [10, 100, 100, 100]
        sales = self.create_sales(prices)
        fair_price, stats = calculate_fair_price(sales)

        self.assertEqual(stats['outliers_removed'], 1)
        self.assertEqual(stats['num_sales'], 3)
        self.assertEqual(stats['median_all'], 100.0)
        # Remaining: 100, 100, 100. Fair price should be 100.
        self.assertEqual(fair_price, 100.0)

    def test_calculate_fair_price_high_outlier(self):
        # Median of [100, 100, 100, 1000] is 100.
        # Cutoffs: 33.33 to 300.
        # 1000 is > 300, should be removed.
        prices = [100, 100, 100, 1000]
        sales = self.create_sales(prices)
        fair_price, stats = calculate_fair_price(sales)

        self.assertEqual(stats['outliers_removed'], 1)
        self.assertEqual(stats['num_sales'], 3)
        # Remaining: 100, 100, 100.
        self.assertEqual(fair_price, 100.0)

    def test_calculate_fair_price_mixed_outliers(self):
        # Median of [10, 100, 100, 1000] is 100.
        # Cutoffs: 33.33 to 300.
        # 10 and 1000 should be removed.
        prices = [10, 100, 100, 1000]
        sales = self.create_sales(prices)
        fair_price, stats = calculate_fair_price(sales)

        self.assertEqual(stats['outliers_removed'], 2)
        self.assertEqual(stats['num_sales'], 2)
        # Remaining: 100, 100.
        self.assertEqual(fair_price, 100.0)

    def test_calculate_fair_price_small_sample(self):
        # Less than 3 sales -> No outlier removal
        # Even if one is huge
        prices = [10, 1000]
        sales = self.create_sales(prices)
        fair_price, stats = calculate_fair_price(sales)

        self.assertEqual(stats['outliers_removed'], 0)
        self.assertEqual(stats['num_sales'], 2)

    def test_calculate_fair_price_zero_median(self):
        # Median is 0 -> No outlier removal (avoids division by zero or weird logic)
        prices = [0, 0, 0, 100]
        sales = self.create_sales(prices)
        # Median of [0, 0, 0, 100] is 0.
        fair_price, stats = calculate_fair_price(sales)

        self.assertEqual(stats['outliers_removed'], 0)
        self.assertEqual(stats['num_sales'], 4)

if __name__ == '__main__':
    unittest.main()
