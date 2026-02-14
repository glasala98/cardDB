import sys
from unittest.mock import MagicMock

# Mock selenium and its submodules to avoid installation attempt during import
mock_selenium = MagicMock()
sys.modules["selenium"] = mock_selenium
sys.modules["selenium.webdriver"] = MagicMock()
sys.modules["selenium.webdriver.chrome.options"] = MagicMock()
sys.modules["selenium.webdriver.common.by"] = MagicMock()
sys.modules["selenium.webdriver.support.ui"] = MagicMock()
sys.modules["selenium.webdriver.support"] = MagicMock()
sys.modules["selenium.webdriver.support.expected_conditions"] = MagicMock()

import pytest
from scrape_card_prices import get_grade_info, is_graded_card

@pytest.mark.parametrize("card_name, expected_str, expected_num", [
    ("2023-24 Upper Deck Series 2 - [Base] #451 - Young Guns - Connor Bedard [PSA 10 GEM MT]", "PSA 10", 10),
    ("2023-24 Upper Deck Series 2 - [Base] #451 - Young Guns - Connor Bedard [PSA 9 MINT]", "PSA 9", 9),
    ("2023-24 O-Pee-Chee Platinum - [Base] - NHL Shield Variations #203 - Marquee Rookies - Adam Fantilli [PSA 10 GEM MT]", "PSA 10", 10),
    ("2024 Upper Deck PWHL 1st Edition - [Base] #61 - Young Guns - Taylor Heise [PSA 8 NM‑MT]", "PSA 8", 8),
    ("Connor Bedard [psa 10]", "PSA 10", 10),
    ("Connor Bedard [psa 7]", "PSA 7", 7),
    ("2022-23 Upper Deck Extended Series - [Base] #705 - Young Guns - Jonatan Berggren", None, None),
    ("2023-24 O-Pee-Chee Platinum - [Base] - Violet Pixels #236 - Marquee Rookies - Connor Zary [Passed Pre‑Grade Review] #168/299", None, None),
    ("2020-21 Upper Deck - [Base] - Photo Variation #419 - Auston Matthews [Poor to Fair]", None, None),
    ("Connor Bedard PSA 10", None, None),
    ("[PSA 100] Super Rare Card", "PSA 100", 100),
])
def test_get_grade_info(card_name, expected_str, expected_num):
    grade_str, grade_num = get_grade_info(card_name)
    assert grade_str == expected_str
    assert grade_num == expected_num

@pytest.mark.parametrize("card_name, expected", [
    ("Connor Bedard [PSA 10]", True),
    ("Connor Bedard [psa 9]", True),
    ("Connor Bedard [PSA 1]", True),
    ("Connor Bedard [Base]", False),
    ("Connor Bedard", False),
    ("Connor Bedard [Passed Pre‑Grade Review]", False),
])
def test_is_graded_card(card_name, expected):
    assert is_graded_card(card_name) == expected
