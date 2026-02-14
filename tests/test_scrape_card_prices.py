import sys
from unittest.mock import MagicMock

# Mock selenium before importing scrape_card_prices to avoid installation attempt
sys.modules["selenium"] = MagicMock()
sys.modules["selenium.webdriver"] = MagicMock()
sys.modules["selenium.webdriver.chrome.options"] = MagicMock()
sys.modules["selenium.webdriver.common.by"] = MagicMock()
sys.modules["selenium.webdriver.support.ui"] = MagicMock()
sys.modules["selenium.webdriver.support"] = MagicMock()
sys.modules["selenium.webdriver.support.expected_conditions"] = MagicMock()

import pytest
from scrape_card_prices import get_grade_info

def test_get_grade_info_standard():
    card_name = "[PSA 10] 2023-24 Upper Deck Connor McDavid"
    assert get_grade_info(card_name) == ("PSA 10", 10)

def test_get_grade_info_case_insensitive():
    card_name = "[psa 9] 2023-24 Upper Deck Connor McDavid"
    assert get_grade_info(card_name) == ("PSA 9", 9)

def test_get_grade_info_no_grade():
    card_name = "2023-24 Upper Deck Connor McDavid"
    assert get_grade_info(card_name) == (None, None)

def test_get_grade_info_no_brackets():
    # Current regex requires opening bracket: r'\[PSA (\d+)'
    card_name = "PSA 10 2023-24 Upper Deck Connor McDavid"
    assert get_grade_info(card_name) == (None, None)

def test_get_grade_info_other_service():
    card_name = "[BGS 9.5] 2023-24 Upper Deck Connor McDavid"
    assert get_grade_info(card_name) == (None, None)

def test_get_grade_info_multiple():
    # Should return the first match
    card_name = "[PSA 9] [PSA 10] 2023-24 Upper Deck Connor McDavid"
    assert get_grade_info(card_name) == ("PSA 9", 9)

def test_get_grade_info_middle_of_string():
    card_name = "2023-24 Upper Deck [PSA 8] Connor McDavid"
    assert get_grade_info(card_name) == ("PSA 8", 8)
