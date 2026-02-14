import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import pandas as pd
import json

# Add root directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard_utils import (
    analyze_card_images,
    scrape_single_card,
    load_data,
    save_data
)

class TestDashboardUtils(unittest.TestCase):

    @patch('dashboard_utils.anthropic')
    @patch('dashboard_utils.os.environ.get')
    def test_analyze_card_images(self, mock_env_get, mock_anthropic):
        mock_env_get.return_value = 'fake_api_key'

        # Mock Anthropic Client
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        # Mock Response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"is_sports_card": true, "player_name": "Test Player"}')]
        mock_client.messages.create.return_value = mock_response

        # Call function
        front_img = b'fake_front_bytes'
        result, error = analyze_card_images(front_img)

        self.assertIsNotNone(result)
        self.assertIsNone(error)
        self.assertEqual(result['player_name'], 'Test Player')
        self.assertTrue(result['is_sports_card'])

    @patch('dashboard_utils.anthropic')
    @patch('dashboard_utils.os.environ.get')
    def test_analyze_card_images_no_api_key(self, mock_env_get, mock_anthropic):
        mock_env_get.return_value = ''
        result, error = analyze_card_images(b'bytes')
        self.assertIsNone(result)
        self.assertIn("ANTHROPIC_API_KEY not set", error)

    @patch('dashboard_utils.CardScraper')
    def test_scrape_single_card_success(self, MockCardScraper):
        # Mock instance
        mock_instance = MockCardScraper.return_value

        # Mock scrape_card return value
        mock_instance.scrape_card.return_value = ("Test Card", {
            'stats': {'fair_price': 100, 'num_sales': 1},
            'raw_sales': [{'title': 'Card', 'price_val': 100}],
            'estimated_value': '$100'
        })

        stats = scrape_single_card("Test Card")

        self.assertIsNotNone(stats)
        self.assertEqual(stats['fair_price'], 100)
        mock_instance.quit.assert_called_once()

    @patch('dashboard_utils.CardScraper')
    def test_scrape_single_card_no_sales(self, MockCardScraper):
        mock_instance = MockCardScraper.return_value

        # Mock scrape_card returning no sales
        mock_instance.scrape_card.return_value = ("Test Card", {
            'stats': {'num_sales': 0},
            'raw_sales': [],
            'estimated_value': '$5.00'
        })

        stats = scrape_single_card("Test Card")
        self.assertIsNone(stats)
        mock_instance.quit.assert_called_once()

    def test_load_save_data(self):
        # Test with a temporary CSV file
        temp_csv = 'temp_test_data.csv'

        # Create dummy data
        data = {
            'Card Name': ['Card A'],
            'Fair Value': [10.0],
            'Trend': ['stable'],
            'Num Sales': [5],
            'Min': [5.0],
            'Max': [15.0],
            'Top 3 Prices': ['10'],
            'Median (All)': [10.0]
        }
        df = pd.DataFrame(data)

        try:
            # Save
            save_data(df, temp_csv)
            self.assertTrue(os.path.exists(temp_csv))

            # Load
            loaded_df = load_data(temp_csv)
            self.assertEqual(len(loaded_df), 1)
            self.assertEqual(loaded_df.iloc[0]['Card Name'], 'Card A')
            self.assertEqual(loaded_df.iloc[0]['Fair Value'], 10.0)

        finally:
            if os.path.exists(temp_csv):
                os.remove(temp_csv)

if __name__ == '__main__':
    unittest.main()
