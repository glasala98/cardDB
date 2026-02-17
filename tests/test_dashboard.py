import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import importlib

class TestDashboard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Save original sys.modules
        cls.original_modules = sys.modules.copy()

        # ----------------------------------------------------------------------
        # DEFINE MOCKS
        # ----------------------------------------------------------------------

        # Helper to mock a module structure
        def mock_module(module_name):
            # We overwrite existing modules to ensure isolation for this test class
            sys.modules[module_name] = MagicMock()

        # Mocking modules
        mock_module('pandas')
        mock_module('plotly')
        mock_module('plotly.express')
        mock_module('plotly.graph_objects')
        mock_module('anthropic')

        # Mocking selenium deeply
        mock_module('selenium')
        mock_module('selenium.webdriver')
        mock_module('selenium.webdriver.common')
        mock_module('selenium.webdriver.common.by')
        mock_module('selenium.webdriver.support')
        mock_module('selenium.webdriver.support.ui')
        mock_module('selenium.webdriver.support.expected_conditions')
        mock_module('selenium.webdriver.chrome')
        mock_module('selenium.webdriver.chrome.options')
        mock_module('selenium.webdriver.chrome.service')
        mock_module('selenium.common')
        mock_module('selenium.common.exceptions')

        # Setup attributes for imports
        sys.modules['selenium.webdriver.common.by'].By = MagicMock()
        sys.modules['selenium.webdriver.support'].expected_conditions = sys.modules['selenium.webdriver.support.expected_conditions']
        sys.modules['selenium.webdriver.chrome.options'].Options = MagicMock()
        sys.modules['selenium.common.exceptions'].TimeoutException = Exception
        sys.modules['selenium.common.exceptions'].NoSuchElementException = Exception

        # Mock Streamlit
        mock_st = MagicMock()
        sys.modules['streamlit'] = mock_st
        mock_st.sidebar.button.return_value = False
        mock_st.sidebar.form_submit_button.return_value = False
        mock_st.button.return_value = False
        mock_st.text_input.return_value = ""
        mock_st.sidebar.text_input.return_value = ""
        mock_st.sidebar.file_uploader.return_value = None
        mock_st.sidebar.slider.return_value = 0
        mock_st.sidebar.multiselect.return_value = []
        mock_st.sidebar.checkbox.return_value = False

        def mock_columns(n):
            if isinstance(n, int):
                return [MagicMock() for _ in range(n)]
            return [MagicMock() for _ in range(len(n))]
        mock_st.columns.side_effect = mock_columns

        def mock_tabs(tabs):
            return [MagicMock() for _ in range(len(tabs))]
        mock_st.tabs.side_effect = mock_tabs

        class SessionState(dict):
            def __getattr__(self, item):
                return self.get(item)
            def __setattr__(self, key, value):
                self[key] = value
        mock_st.session_state = SessionState()

        # Mock Series
        mock_series = MagicMock()
        mock_series.__ge__.return_value = mock_series
        mock_series.__gt__.return_value = mock_series
        mock_series.__le__.return_value = mock_series
        mock_series.__lt__.return_value = mock_series
        mock_series.__and__.return_value = mock_series
        mock_series.__or__.return_value = mock_series
        mock_series.__rand__.return_value = mock_series

        mock_series.sum.return_value = 0.0
        mock_series.mean.return_value = 0.0
        mock_series.isin.return_value = mock_series
        mock_series.replace.return_value = mock_series
        mock_series.astype.return_value = mock_series
        mock_series.fillna.return_value = mock_series
        mock_series.apply.return_value = mock_series

        # unique().tolist()
        mock_unique = MagicMock()
        mock_unique.tolist.return_value = ['up']
        mock_series.unique.return_value = mock_unique

        # .str accessor
        mock_str_accessor = MagicMock()
        mock_str_accessor.replace.return_value = mock_series
        mock_series.str = mock_str_accessor

        # Mock DataFrame
        mock_df = MagicMock()

        def df_getitem(arg):
            if isinstance(arg, str):
                return mock_series
            # Assume it's a mask or list of cols, return df
            return mock_df

        mock_df.__getitem__.side_effect = df_getitem
        mock_df.__len__.return_value = 10
        mock_df.copy.return_value = mock_df
        mock_df.nlargest.return_value = mock_df
        mock_df.apply.return_value = mock_series
        mock_df.iterrows.return_value = []

        # Aggregation chain
        mock_agg = MagicMock()
        mock_agg.reindex.return_value.dropna.return_value.reset_index.return_value = mock_df
        mock_df.groupby.return_value.agg.return_value = mock_agg

        # Make data_editor return mock_df
        mock_st.data_editor.return_value = mock_df

        # Configure pandas module
        sys.modules['pandas'].read_csv.return_value = mock_df
        sys.modules['pandas'].to_numeric.return_value = mock_series
        sys.modules['pandas'].concat.return_value = mock_df
        sys.modules['pandas'].DataFrame.return_value = mock_df

        # ----------------------------------------------------------------------
        # IMPORT
        # ----------------------------------------------------------------------

        # Add project root to path
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Force fresh import of dashboard
        if 'dashboard' in sys.modules:
            del sys.modules['dashboard']

        # We also need to make sure imports inside dashboard (like scrape_card_prices) use our mocks
        # scrape_card_prices uses selenium, which we mocked.
        # But if scrape_card_prices was already imported by another test, it stays.
        # We should reload it or delete it too if we want it to use our mocks.
        if 'scrape_card_prices' in sys.modules:
             del sys.modules['scrape_card_prices']

        import dashboard
        cls.dashboard = dashboard

    @classmethod
    def tearDownClass(cls):
        # Restore original sys.modules
        sys.modules.clear()
        sys.modules.update(cls.original_modules)

        # Also ensure dashboard and scrape_card_prices are removed so other tests re-import them cleanly if needed
        if 'dashboard' in sys.modules:
            del sys.modules['dashboard']
        if 'scrape_card_prices' in sys.modules:
            del sys.modules['scrape_card_prices']

    def setUp(self):
        # Reset environment variable for each test
        self.environ_patcher = patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake_key"})
        self.environ_patcher.start()

    def tearDown(self):
        self.environ_patcher.stop()

    def test_analyze_card_images_success(self):
        # Mock anthropic within the imported dashboard module
        with patch.object(self.dashboard.anthropic, 'Anthropic') as mock_anthropic_class:
            # Setup mock client and response
            mock_client = MagicMock()
            mock_anthropic_class.return_value = mock_client

            # Prepare response mock
            mock_response = MagicMock()
            mock_message = MagicMock()
            mock_message.text = '{"is_sports_card": true, "player_name": "Wayne Gretzky", "card_number": "99"}'
            mock_response.content = [mock_message]
            mock_client.messages.create.return_value = mock_response

            # Call function
            front_bytes = b"front_image_data"
            back_bytes = b"back_image_data"
            result, error = self.dashboard.analyze_card_images(front_bytes, back_bytes)

            # Verify
            self.assertIsNotNone(result)
            self.assertIsNone(error)
            self.assertEqual(result['player_name'], "Wayne Gretzky")
            self.assertEqual(result['card_number'], "99")
            self.assertTrue(result['is_sports_card'])

            # Verify call arguments
            mock_client.messages.create.assert_called_once()
            args, kwargs = mock_client.messages.create.call_args
            self.assertEqual(kwargs['model'], "claude-sonnet-4-5-20250929")
            self.assertEqual(kwargs['max_tokens'], 500)

    def test_analyze_card_images_no_api_key(self):
        # Unset env var
        with patch.dict(os.environ, {}, clear=True):
            result, error = self.dashboard.analyze_card_images(b"img")
            self.assertIsNone(result)
            self.assertIn("ANTHROPIC_API_KEY not set", error)

    def test_analyze_card_images_no_package(self):
        # Patch HAS_ANTHROPIC on the imported module
        with patch.object(self.dashboard, 'HAS_ANTHROPIC', False):
            result, error = self.dashboard.analyze_card_images(b"img")
            self.assertIsNone(result)
            self.assertIn("anthropic package not installed", error)

    def test_analyze_card_images_api_error(self):
        with patch.object(self.dashboard.anthropic, 'Anthropic') as mock_anthropic_class:
            mock_client = MagicMock()
            mock_anthropic_class.return_value = mock_client
            mock_client.messages.create.side_effect = Exception("API Connection Error")

            result, error = self.dashboard.analyze_card_images(b"img")
            self.assertIsNone(result)
            self.assertEqual(error, "API Connection Error")

    def test_analyze_card_images_invalid_json(self):
        with patch.object(self.dashboard.anthropic, 'Anthropic') as mock_anthropic_class:
            mock_client = MagicMock()
            mock_anthropic_class.return_value = mock_client

            mock_response = MagicMock()
            mock_message = MagicMock()
            mock_message.text = 'This is not JSON'
            mock_response.content = [mock_message]
            mock_client.messages.create.return_value = mock_response

            result, error = self.dashboard.analyze_card_images(b"img")
            self.assertIsNone(result)
            self.assertIn("Could not parse response", error)

if __name__ == '__main__':
    unittest.main()
