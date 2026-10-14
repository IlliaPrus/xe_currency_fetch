import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
import requests
from main import (get_exchange_rate, fetch_multiple_exchange_rates, extract_rate, parse_rate,
                  validate_config, write_results_to_file)

class TestGetExchangeRate(unittest.TestCase):

    @patch('main.requests.Session.get')
    def test_get_exchange_rate_success(self, mock_get):
        # Mock response content
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = '''
        <html>
            <body>
                <p class="sc-63d8b7e3-1 bMdPIi">1.2345</p>
            </body>
        </html>
        '''
        mock_get.return_value = mock_response

        session = requests.Session()
        currency_from = 'USD'
        currency_to = 'EUR'
        result = get_exchange_rate(session, currency_from, currency_to)

        self.assertEqual(result, (currency_from, currency_to, 1.2345))

    @patch('main.requests.Session.get')
    def test_get_exchange_rate_no_rate_section(self, mock_get):
        # Mock response content without rate section
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = '''
        <html>
            <body>
                <p class="some-other-class">No rate here</p>
            </body>
        </html>
        '''
        mock_get.return_value = mock_response

        session = requests.Session()
        currency_from = 'USD'
        currency_to = 'EUR'
        result = get_exchange_rate(session, currency_from, currency_to)

        self.assertEqual(result, (currency_from, currency_to, None))

    @patch('main.requests.Session.get')
    def test_get_exchange_rate_invalid_rate_format(self, mock_get):
        # Mock response content with invalid rate format
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = '''
        <html>
            <body>
                <p class="sc-63d8b7e3-1 bMdPIi">Invalid rate</p>
            </body>
        </html>
        '''
        mock_get.return_value = mock_response

        session = requests.Session()
        currency_from = 'USD'
        currency_to = 'EUR'
        result = get_exchange_rate(session, currency_from, currency_to)

        self.assertEqual(result, (currency_from, currency_to, None))

    @patch('main.requests.Session.get')
    def test_get_exchange_rate_http_error(self, mock_get):
        # Mock HTTP error
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError
        mock_get.return_value = mock_response

        session = requests.Session()
        currency_from = 'USD'
        currency_to = 'EUR'
        result = get_exchange_rate(session, currency_from, currency_to)

        self.assertEqual(result, (currency_from, currency_to, None))

    @patch('main.requests.Session.get')
    def test_get_exchange_rate_exception(self, mock_get):
        # Mock general exception
        mock_get.side_effect = Exception("Some error")

        session = requests.Session()
        currency_from = 'USD'
        currency_to = 'EUR'
        result = get_exchange_rate(session, currency_from, currency_to)

        self.assertEqual(result, (currency_from, currency_to, None))


class TestFetchMultipleExchangeRates(unittest.TestCase):

    @patch('main.get_exchange_rate')
    @patch('main.requests.Session')
    def test_fetch_multiple_exchange_rates_success(self, mock_session, mock_get_exchange_rate):
        # Mock get_exchange_rate to return a successful rate
        mock_get_exchange_rate.side_effect = [
            ('USD', 'EUR', 1.2345),
            ('GBP', 'USD', 1.5678)
        ]

        pairs = [('USD', 'EUR'), ('GBP', 'USD')]
        results = fetch_multiple_exchange_rates(mock_session, pairs)

        expected_results = [
            {"from": "USD", "to": "EUR", "rate": 1.2345},
            {"from": "GBP", "to": "USD", "rate": 1.5678}
        ]

        self.assertEqual(results, expected_results)

    @patch('main.get_exchange_rate')
    @patch('main.requests.Session')
    def test_fetch_multiple_exchange_rates_partial_failure(self, mock_session, mock_get_exchange_rate):
        # Mock get_exchange_rate to return a mix of successful and None rates
        mock_get_exchange_rate.side_effect = [
            ('USD', 'EUR', 1.2345),
            ('GBP', 'USD', None)
        ]

        pairs = [('USD', 'EUR'), ('GBP', 'USD')]
        results = fetch_multiple_exchange_rates(mock_session, pairs)

        expected_results = [
            {"from": "USD", "to": "EUR", "rate": 1.2345},
            {"from": "GBP", "to": "USD", "rate": None}
        ]

        self.assertEqual(results, expected_results)

    @patch('main.get_exchange_rate')
    @patch('main.requests.Session')
    def test_fetch_multiple_exchange_rates_all_failure(self, mock_session, mock_get_exchange_rate):
        # Mock get_exchange_rate to return None for all pairs
        mock_get_exchange_rate.side_effect = [
            ('USD', 'EUR', None),
            ('GBP', 'USD', None)
        ]

        pairs = [('USD', 'EUR'), ('GBP', 'USD')]
        results = fetch_multiple_exchange_rates(mock_session, pairs)

        expected_results = [
            {"from": "USD", "to": "EUR", "rate": None},
            {"from": "GBP", "to": "USD", "rate": None}
        ]

        self.assertEqual(results, expected_results)

class TestFetchOrderAndErrors(unittest.TestCase):

    @patch('main.get_exchange_rate')
    def test_results_keep_input_order(self, mock_get_exchange_rate):
        # the first pair answers slowest; results must still follow the input order
        def slow_first(session, cur_from, cur_to):
            time.sleep(0.2 if cur_from == 'USD' else 0)
            return cur_from, cur_to, 1.0
        mock_get_exchange_rate.side_effect = slow_first

        pairs = [['USD', 'EUR'], ['GBP', 'USD'], ['JPY', 'USD']]
        results = fetch_multiple_exchange_rates(Mock(), pairs)

        self.assertEqual([(r['from'], r['to']) for r in results], [tuple(p) for p in pairs])

    @patch('main.get_exchange_rate')
    def test_unexpected_exception_gives_none(self, mock_get_exchange_rate):
        mock_get_exchange_rate.side_effect = RuntimeError("boom")
        results = fetch_multiple_exchange_rates(Mock(), [['USD', 'EUR']])
        self.assertEqual(results, [{"from": "USD", "to": "EUR", "rate": None}])


class TestExtractRate(unittest.TestCase):

    def test_fallback_to_page_text(self):
        html = '<html><body><p class="new-class">1 USD = 0.9213 EUR</p></body></html>'
        self.assertEqual(extract_rate(html, 'USD', 'EUR'), 0.9213)

    def test_thousands_separator(self):
        html = '<html><body><p class="new-class">1.00 USD = 16,245.50 IDR</p></body></html>'
        self.assertEqual(extract_rate(html, 'USD', 'IDR'), 16245.5)

    def test_parse_rate(self):
        self.assertEqual(parse_rate("1,234.5 JPY"), 1234.5)
        self.assertEqual(parse_rate("18 ZAR"), 18.0)
        self.assertIsNone(parse_rate("no number"))


class TestValidateConfig(unittest.TestCase):

    def test_valid(self):
        self.assertTrue(validate_config({"interval_seconds": 15, "currency_pairs": [["USD", "EUR"]]}))

    def test_invalid(self):
        bad_configs = [
            None,
            {"currency_pairs": [["USD", "EUR"]]},                      # missing key
            {"interval_seconds": "15", "currency_pairs": []},          # wrong type
            {"interval_seconds": 0, "currency_pairs": []},             # not positive
            {"interval_seconds": 15, "currency_pairs": [["USD"]]},     # not a pair
            {"interval_seconds": 15, "currency_pairs": [["usd", "EURO"]]},  # bad codes
        ]
        for cfg in bad_configs:
            with self.subTest(cfg=cfg):
                self.assertFalse(validate_config(cfg))


class TestWriteResults(unittest.TestCase):

    def test_output_structure(self):
        results = [{"from": "USD", "to": "EUR", "rate": 0.92}]
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'rates.json')
            with patch('main.config.OUTPUT_FILE', out):
                write_results_to_file(results)
            with open(out, encoding='utf-8') as f:
                data = json.load(f)
        self.assertIn("timestamp", data)
        self.assertEqual(data["exchange_rates"], results)  # a flat list, not nested


if __name__ == '__main__':
    unittest.main()
