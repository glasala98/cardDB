# Testing the Sports Card Dashboard

This directory contains the unit test suite for the project, ensuring that core logic in the scraper and dashboard utilities functions correctly.

## Running Tests

From the project root directory, run:

```bash
python run_tests.py
```

This script discovers and runs all tests in the `tests/` directory using Python's built-in `unittest` framework.

## Test Structure

Tests are located in the `tests/` directory and follow the naming convention `test_*.py`.

| Test File | Description |
|-----------|-------------|
| `test_dashboard_utils.py` | Tests for `dashboard_utils.py`. Covers image analysis (mocking Anthropic API), single card scraping (mocking Selenium), and data loading/saving logic. |
| `test_scrape_card_prices.py` | Tests for `scrape_card_prices.py`. Covers card name parsing, grade extraction, fair price calculation logic (including outlier removal), and search query building. |

## Mocking External Dependencies

The tests use `unittest.mock` to simulate external interactions, ensuring tests run quickly and without needing live API keys or browser sessions.

- **Selenium (`selenium`)**: The `webdriver.Chrome` instance is mocked to prevent launching a real browser. Search results are simulated by mocking `find_elements` and other driver methods.
- **Anthropic API (`anthropic`)**: The `Anthropic` client is mocked to return predefined JSON responses for image analysis tests, avoiding actual API calls and costs.

## Adding New Tests

1. Create a new test file in `tests/` (e.g., `test_new_feature.py`) or add to an existing one.
2. Import the module you want to test. Note that `sys.path` modification in the test files allows importing modules from the root directory.
3. Write test cases inheriting from `unittest.TestCase`.
4. Use `@patch` decorators to mock external dependencies.
5. Run `python run_tests.py` to verify your new tests.
