import unittest
import sys
import os
from unittest.mock import MagicMock

# Mock selenium modules BEFORE importing scrape_card_prices
sys.modules['selenium'] = MagicMock()
sys.modules['selenium.webdriver'] = MagicMock()
sys.modules['selenium.webdriver.chrome.options'] = MagicMock()
sys.modules['selenium.webdriver.common.by'] = MagicMock()
sys.modules['selenium.webdriver.support.ui'] = MagicMock()
sys.modules['selenium.webdriver.support'] = MagicMock()
sys.modules['selenium.webdriver.support.expected_conditions'] = MagicMock()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_card_prices import calculate_fair_price

class TestCalculateFairPrice(unittest.TestCase):
    """Tests for the calculate_fair_price function in scrape_card_prices.py."""

    def test_empty_sales(self):
        """Test with an empty list of sales."""
        fair_price, stats = calculate_fair_price([])
        self.assertIsNone(fair_price)
        self.assertEqual(stats, {})

    def test_single_sale(self):
        """Test with a single sale."""
        sales = [{'price_val': 100.0, 'days_ago': 5, 'title': 'Test Card', 'sold_date': '2023-01-01'}]
        fair_price, stats = calculate_fair_price(sales)
        self.assertEqual(fair_price, 100.0)
        self.assertEqual(stats['trend'], 'insufficient data')
        self.assertEqual(stats['num_sales'], 1)
        self.assertEqual(len(stats['top_3_prices']), 1)

    def test_two_sales_stable(self):
        """Test with two sales showing stable trend."""
        sales = [
            {'price_val': 100.0, 'days_ago': 1, 'title': 'Recent', 'sold_date': '2023-01-02'},
            {'price_val': 100.0, 'days_ago': 5, 'title': 'Older', 'sold_date': '2023-01-01'}
        ]
        # With < 4 sales, stable logic: older * 0.9 <= recent <= older * 1.1
        # 100 is exactly equal, so stable.
        fair_price, stats = calculate_fair_price(sales)
        self.assertEqual(stats['trend'], 'stable')
        # Stable trend picks middle value of top 3. Top 3 sorted by price: [100, 100]. Middle index 1.
        # Wait, sorted by price: [100, 100]. len=2. 2//2 = 1. index 1 is 100.
        self.assertEqual(fair_price, 100.0)

    def test_two_sales_up(self):
        """Test with two sales showing upward trend."""
        sales = [
            {'price_val': 150.0, 'days_ago': 1, 'title': 'Recent', 'sold_date': '2023-01-02'},
            {'price_val': 100.0, 'days_ago': 5, 'title': 'Older', 'sold_date': '2023-01-01'}
        ]
        # 150 > 100 * 1.1 (110) -> Up trend
        fair_price, stats = calculate_fair_price(sales)
        self.assertEqual(stats['trend'], 'up')
        # Up trend picks highest of top 3.
        self.assertEqual(fair_price, 150.0)

    def test_two_sales_down(self):
        """Test with two sales showing downward trend."""
        sales = [
            {'price_val': 50.0, 'days_ago': 1, 'title': 'Recent', 'sold_date': '2023-01-02'},
            {'price_val': 100.0, 'days_ago': 5, 'title': 'Older', 'sold_date': '2023-01-01'}
        ]
        # 50 < 100 * 0.9 (90) -> Down trend
        fair_price, stats = calculate_fair_price(sales)
        self.assertEqual(stats['trend'], 'down')
        # Down trend picks lowest of top 3.
        self.assertEqual(fair_price, 50.0)

    def test_three_sales_stable(self):
        """Test with three sales showing stable trend."""
        sales = [
            {'price_val': 105.0, 'days_ago': 1, 'title': 'Recent', 'sold_date': '2023-01-03'},
            {'price_val': 100.0, 'days_ago': 2, 'title': 'Middle', 'sold_date': '2023-01-02'},
            {'price_val': 95.0, 'days_ago': 3, 'title': 'Oldest', 'sold_date': '2023-01-01'}
        ]
        # < 4 sales logic: compare recent (105) vs oldest (95)
        # 105 vs 95 * 1.1 (104.5) -> 105 > 104.5 -> Up?
        # Wait, let's check logic:
        # sorted_sales[0] is most recent (105). sorted_sales[-1] is oldest (95).
        # if 105 > 95 * 1.1 (104.5): trend = 'up'
        fair_price, stats = calculate_fair_price(sales)
        self.assertEqual(stats['trend'], 'up')
        # Up trend picks highest of top 3: 105.
        self.assertEqual(fair_price, 105.0)

    def test_three_sales_truly_stable(self):
        """Test with three sales truly stable."""
        sales = [
            {'price_val': 100.0, 'days_ago': 1, 'title': 'Recent', 'sold_date': '2023-01-03'},
            {'price_val': 100.0, 'days_ago': 2, 'title': 'Middle', 'sold_date': '2023-01-02'},
            {'price_val': 100.0, 'days_ago': 3, 'title': 'Oldest', 'sold_date': '2023-01-01'}
        ]
        fair_price, stats = calculate_fair_price(sales)
        self.assertEqual(stats['trend'], 'stable')
        self.assertEqual(fair_price, 100.0)

    def test_four_sales_trend_up(self):
        """Test with four sales showing upward trend (uses average logic)."""
        # >= 4 sales uses split average logic.
        sales = [
            {'price_val': 200.0, 'days_ago': 1, 'title': '1', 'sold_date': '2023-01-04'},
            {'price_val': 200.0, 'days_ago': 2, 'title': '2', 'sold_date': '2023-01-03'},
            {'price_val': 100.0, 'days_ago': 3, 'title': '3', 'sold_date': '2023-01-02'},
            {'price_val': 100.0, 'days_ago': 4, 'title': '4', 'sold_date': '2023-01-01'}
        ]
        # Split: Recent half [200, 200] (avg 200). Older half [100, 100] (avg 100).
        # pct_change = (200 - 100) / 100 * 100 = 100% > 10% -> Up.
        fair_price, stats = calculate_fair_price(sales)
        self.assertEqual(stats['trend'], 'up')
        # Top 3 are most recent 3: 200, 200, 100.
        # Up trend picks highest of top 3: 200.
        self.assertEqual(fair_price, 200.0)

    def test_four_sales_trend_down(self):
        """Test with four sales showing downward trend."""
        sales = [
            {'price_val': 100.0, 'days_ago': 1, 'title': '1', 'sold_date': '2023-01-04'},
            {'price_val': 100.0, 'days_ago': 2, 'title': '2', 'sold_date': '2023-01-03'},
            {'price_val': 200.0, 'days_ago': 3, 'title': '3', 'sold_date': '2023-01-02'},
            {'price_val': 200.0, 'days_ago': 4, 'title': '4', 'sold_date': '2023-01-01'}
        ]
        # Recent avg 100, Older avg 200. Change -50% < -10% -> Down.
        fair_price, stats = calculate_fair_price(sales)
        self.assertEqual(stats['trend'], 'down')
        # Top 3 most recent: 100, 100, 200.
        # Down trend picks lowest of top 3: 100.
        self.assertEqual(fair_price, 100.0)

    def test_outlier_removal(self):
        """Test that extreme outliers are removed."""
        sales = [
            {'price_val': 100.0, 'days_ago': 1, 'title': 'Normal', 'sold_date': '2023-01-03'},
            {'price_val': 100.0, 'days_ago': 2, 'title': 'Normal', 'sold_date': '2023-01-02'},
            {'price_val': 100.0, 'days_ago': 3, 'title': 'Normal', 'sold_date': '2023-01-01'},
            {'price_val': 1000.0, 'days_ago': 0, 'title': 'Outlier', 'sold_date': '2023-01-04'}
        ]
        # Median is ~100. 1000 > 300 (3x median). Should be removed.
        fair_price, stats = calculate_fair_price(sales)
        self.assertEqual(stats['outliers_removed'], 1)
        self.assertEqual(fair_price, 100.0)
        self.assertEqual(stats['num_sales'], 3)

    def test_undated_sales(self):
        """Test handling of sales with no date."""
        sales = [
            {'price_val': 100.0, 'days_ago': None, 'title': 'Undated', 'sold_date': None},
            {'price_val': 200.0, 'days_ago': 1, 'title': 'Dated', 'sold_date': '2023-01-01'}
        ]
        # Undated sales are appended after dated sales in sorted_sales.
        # So order: Dated (200), Undated (100).
        # Top 3: [200, 100].
        # < 4 sales logic:
        # Recent (200) vs Oldest (100). 200 > 100 * 1.1 -> Up.
        fair_price, stats = calculate_fair_price(sales)
        self.assertEqual(stats['trend'], 'up')
        # Up picks highest of top 3: 200.
        self.assertEqual(fair_price, 200.0)

if __name__ == '__main__':
    unittest.main()
