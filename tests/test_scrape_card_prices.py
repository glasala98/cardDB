import unittest
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime

# Add root directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_card_prices import (
    clean_card_name_for_search,
    get_grade_info,
    title_matches_grade,
    build_simplified_query,
    calculate_fair_price,
    is_graded_card,
    search_ebay_sold,
    process_card,
    DEFAULT_PRICE
)

class TestScrapeCardPrices(unittest.TestCase):

    def test_is_graded_card(self):
        self.assertTrue(is_graded_card("Connor McDavid [PSA 10]"))
        self.assertTrue(is_graded_card("Connor McDavid [PSA 9]"))
        self.assertFalse(is_graded_card("Connor McDavid"))
        self.assertFalse(is_graded_card("Connor McDavid [BGS 9.5]")) # Regex only checks PSA currently

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

        # Test Empty Sales
        price_empty, stats_empty = calculate_fair_price([])
        self.assertIsNone(price_empty)
        self.assertEqual(stats_empty, {})

        # Test Insufficient Data (Single Sale)
        sales_single = [{'price_val': 50.0, 'days_ago': 1, 'title': 'Single'}]
        price_single, stats_single = calculate_fair_price(sales_single)
        self.assertEqual(price_single, 50.0)
        self.assertEqual(stats_single['trend'], 'insufficient data')

        # Test Trend Down
        sales_down = [
            {'price_val': 100.0, 'days_ago': 1, 'title': 'New Low'},
            {'price_val': 110.0, 'days_ago': 2, 'title': 'New Low 2'}, # Recent avg ~105
            {'price_val': 200.0, 'days_ago': 10, 'title': 'Old High'},
            {'price_val': 190.0, 'days_ago': 11, 'title': 'Old High 2'}, # Older avg ~195
        ]
        # (105 - 195) / 195 * 100 = -46% < -10% -> Down
        price_down, stats_down = calculate_fair_price(sales_down)
        self.assertEqual(stats_down['trend'], 'down')
        # Down -> pick lowest of top 3 (100, 110, 200). Lowest is 100.
        self.assertEqual(price_down, 100.0)

    @patch('scrape_card_prices.WebDriverWait')
    def test_search_ebay_sold(self, mock_wait):
        mock_driver = MagicMock()

        # Setup mock elements
        # Item 1: Valid match
        item1 = MagicMock()
        title1 = MagicMock(); title1.text = "Connor McDavid [PSA 10]"
        price1 = MagicMock(); price1.text = "$100.00"
        caption1 = MagicMock(); caption1.text = "Sold Oct 1, 2023"

        # Configure find_element side effect
        def item1_find_element(by, val):
            if val == '.s-card__title': return title1
            if val == '.s-card__price': return price1
            if val == '.s-card__caption': return caption1
            return MagicMock()
        item1.find_element.side_effect = item1_find_element

        # For shipping (find_elements)
        ship1 = MagicMock(); ship1.text = "+$10.00 shipping"
        item1.find_elements.return_value = [ship1]

        # Item 2: Mismatch title (e.g. wrong grade)
        item2 = MagicMock()
        title2 = MagicMock(); title2.text = "Connor McDavid [PSA 9]"
        item2.find_element.side_effect = lambda by, val: title2 if val == '.s-card__title' else MagicMock()

        mock_driver.find_elements.return_value = [item1, item2]

        # Mock WebDriverWait
        # It calls until, which returns True or whatever

        sales = search_ebay_sold(mock_driver, "Connor McDavid [PSA 10]")

        self.assertEqual(len(sales), 1)
        self.assertEqual(sales[0]['title'], "Connor McDavid [PSA 10]")
        # Price 100 + Shipping 10 = 110
        self.assertEqual(sales[0]['price_val'], 110.0)

    @patch('scrape_card_prices.get_driver')
    @patch('scrape_card_prices.search_ebay_sold')
    def test_process_card_success(self, mock_search, mock_get_driver):
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        mock_search.return_value = [
            {'title': 'T1', 'price_val': 100.0, 'days_ago': 1, 'search_url': 'http://url'}
        ]

        card, result = process_card("Card Name")

        self.assertEqual(card, "Card Name")
        self.assertEqual(result['estimated_value'], "$100.0")

    @patch('scrape_card_prices.get_driver')
    @patch('scrape_card_prices.search_ebay_sold')
    def test_process_card_retry(self, mock_search, mock_get_driver):
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        # First attempt returns empty
        mock_search.return_value = []

        # Setup mock elements for retry logic inside process_card
        item1 = MagicMock()
        title1 = MagicMock(); title1.text = "Card Name"
        price1 = MagicMock(); price1.text = "$50.00"
        caption1 = MagicMock(); caption1.text = "Sold Oct 1, 2023"

        def item1_find_element(by, val):
            if val == '.s-card__title': return title1
            if val == '.s-card__price': return price1
            if val == '.s-card__caption': return caption1
            return MagicMock()
        item1.find_element.side_effect = item1_find_element

        item1.find_elements.return_value = [] # No shipping

        mock_driver.find_elements.return_value = [item1]

        card, result = process_card("Card Name")

        # search_ebay_sold was called
        mock_search.assert_called_once()

        # Driver.get should have been called for retry
        mock_driver.get.assert_called()

        self.assertEqual(result['estimated_value'], "$50.0")

if __name__ == '__main__':
    unittest.main()
