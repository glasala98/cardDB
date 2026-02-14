import unittest
import pandas as pd
import os
import sys

# Add root directory to path
sys.path.insert(0, os.getcwd())

from dashboard_utils import save_data, load_data

class TestCSVSecurity(unittest.TestCase):
    def setUp(self):
        self.temp_csv = 'test_security_temp.csv'

    def tearDown(self):
        if os.path.exists(self.temp_csv):
            os.remove(self.temp_csv)

    def test_csv_injection_sanitization(self):
        # Data with dangerous characters
        data = {
            'Card Name': ['=1+1', '+2-2', '-3*3', '@SUM(A1:A2)', 'Normal'],
            'Fair Value': [10.0, 20.0, 30.0, 40.0, 50.0],
            'Num Sales': [1, 2, 3, 4, 5],
            'Trend': ['up', 'down', 'stable', 'no data', 'up'],
            'Top 3 Prices': ['', '', '', '', ''],
            'Median (All)': [10.0, 20.0, 30.0, 40.0, 50.0],
            'Min': [10.0, 20.0, 30.0, 40.0, 50.0],
            'Max': [10.0, 20.0, 30.0, 40.0, 50.0]
        }
        df = pd.DataFrame(data)

        # Save
        save_data(df, self.temp_csv)

        # Check raw content for sanitization
        with open(self.temp_csv, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check that no line starts with a dangerous character (except header)
        lines = content.strip().split('\n')
        for line in lines[1:]:
            # If field is quoted, it starts with ", but inside quotes should be '
            # If field is not quoted, it should start with '
            first_char = line.strip()[0]
            self.assertNotIn(first_char, ['=', '+', '-', '@'], f"Unsanitized line found: {line}")

            # More rigorous check: parse manually or verify the value starts with '
            # Since we know Card Name is likely first
            parts = line.split(',')
            first_val = parts[0]
            if first_val.startswith('"'):
                # Quoted: check second char
                if len(first_val) > 1:
                    # It should be "'..." inside quotes
                    self.assertNotEqual(first_val[1], '=', f"Quoted unsanitized value found: {first_val}")
            else:
                self.assertNotEqual(first_val[0], '=', f"Unsanitized value found: {first_val}")


        # Load back
        loaded_df = load_data(self.temp_csv)

        # Verify data restoration
        original_names = data['Card Name']
        loaded_names = loaded_df['Card Name'].tolist()

        self.assertEqual(loaded_names, original_names, "Loaded data does not match original (sanitization not reversed correctly?)")

if __name__ == '__main__':
    unittest.main()
