import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")
NUMBER = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"


def parse_rate(text):
    """Extract the first number from text, e.g. '1,234.56 IDR' -> 1234.56. Returns None if absent."""
    match = re.search(NUMBER, text or "")
    return float(match.group(1).replace(",", "")) if match else None


def extract_rate(html, currency_from, currency_to):
    """
    Find the exchange rate in an xe.com converter page.

    Tries the CSS class from config first; if the site layout changed, falls back to
    searching the page text for '1 FROM = X TO'.
    """
    soup = BeautifulSoup(html, "lxml")

    rate_section = soup.find("p", class_=config.RATE_CSS_CLASS)
    if rate_section:
        return parse_rate(rate_section.get_text(" ", strip=True))

    page_text = soup.get_text(" ", strip=True)
    pattern = rf"1(?:\.0+)?\s*{currency_from}\s*=\s*{NUMBER}\s*{currency_to}"
    match = re.search(pattern, page_text)
    return float(match.group(1).replace(",", "")) if match else None


def get_exchange_rate(session, currency_from, currency_to):
    """
    Fetches the exchange rate between two currencies using a given session.

    Returns:
        tuple: (currency_from, currency_to, rate), where rate is a float or None if it could not be found.
    """
    params = {"Amount": config.DEFAULT_AMOUNT, "From": currency_from, "To": currency_to}

    try:
        response = session.get(config.BASE_URL, params=params, headers=config.HEADERS,
                               timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        rate = extract_rate(response.content, currency_from, currency_to)
        if rate is None:
            print(f"Rate not found on the page for {currency_from} to {currency_to}")
        return currency_from, currency_to, rate

    except Exception as e:
        print(f"Error fetching or parsing data for {currency_from} to {currency_to}: {e}")
        return currency_from, currency_to, None


def fetch_multiple_exchange_rates(session, pairs):
    """
    Fetches exchange rates for multiple currency pairs concurrently.

    Args:
        pairs (list): Currency pairs, e.g. [('USD', 'EUR'), ('GBP', 'JPY')].

    Returns:
        list of dict: {"from", "to", "rate"} for every pair, in the same order as `pairs`.
                      "rate" is None if it could not be fetched.
    """
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        futures = [executor.submit(get_exchange_rate, session, pair[0], pair[1]) for pair in pairs]

    results = []
    for pair, future in zip(pairs, futures):
        try:
            _, _, rate = future.result()
        except Exception as e:
            print(f"Exception for {pair[0]} to {pair[1]}: {e}")
            rate = None
        results.append({"from": pair[0], "to": pair[1], "rate": rate})
    return results


def load_config():
    """Read config.json. Returns the parsed dict, or None if the file is missing or not valid JSON."""
    try:
        with open(config.CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"\t\tWARNING: Cannot read {config.CONFIG_FILE}: {e}")
        return None


def write_results_to_file(results):
    """Write the results with a timestamp to the output JSON file (atomically, via a temp file)."""
    tmp_file = config.OUTPUT_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "exchange_rates": results,
        }, f, indent=4)
    os.replace(tmp_file, config.OUTPUT_FILE)  # readers never see a half-written file
    print(f"Results written to {config.OUTPUT_FILE}")


def validate_config(config_data):
    """
    Validates the configuration data.

    Expected keys:
        - "interval_seconds" (positive int): pause between fetches.
        - "currency_pairs" (list): pairs of 3-letter currency codes, e.g. [["USD", "EUR"]].

    Returns:
        bool: True if the configuration is valid; otherwise prints a warning and returns False.
    """
    if config_data is None:
        print(f"\t\tWARNING: Syntax error in {config.CONFIG_FILE}.")
        return False

    required_keys = {"interval_seconds": int, "currency_pairs": list}

    for key, expected_type in required_keys.items():
        if key not in config_data:
            print(f"\t\tWARNING: Missing required config key '{key}'.")
            return False
        if not isinstance(config_data[key], expected_type) or isinstance(config_data[key], bool):
            print(f"\t\tWARNING: Invalid type for '{key}'. Expected {expected_type.__name__}.")
            return False

    if config_data["interval_seconds"] <= 0:
        print("\t\tWARNING: 'interval_seconds' must be positive.")
        return False

    for pair in config_data["currency_pairs"]:
        if not (isinstance(pair, list) and len(pair) == 2
                and all(isinstance(code, str) and CURRENCY_CODE.match(code) for code in pair)):
            print(f"\t\tWARNING: Invalid currency pair {pair!r}. Use two 3-letter codes, e.g. [\"USD\", \"EUR\"].")
            return False

    return True


def create_session():
    """HTTP session that retries failed requests with exponential backoff."""
    session = requests.Session()
    retries = Retry(total=config.RETRY_COUNT, backoff_factor=config.BACKOFF_FACTOR,
                    status_forcelist=config.RETRY_STATUS_CODES)
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def main():
    last_modified_time = os.path.getmtime(config.CONFIG_FILE)
    config_data = load_config()

    if not validate_config(config_data):
        print(f"\t\tInvalid initial configuration. Please check '{config.CONFIG_FILE}'.")
        return

    session = create_session()

    while True:
        current_modified_time = os.path.getmtime(config.CONFIG_FILE)
        if current_modified_time != last_modified_time:
            last_modified_time = current_modified_time  # warn once per change, not on every loop
            print("Configuration file changed. Reloading...")
            new_config_data = load_config()
            if validate_config(new_config_data):
                config_data = new_config_data
            else:
                print("\t\tWARNING: Invalid configuration. Continuing with the previous valid configuration.")

        interval_seconds = config_data["interval_seconds"]
        start_time = time.time()
        exchange_rates = fetch_multiple_exchange_rates(session, config_data["currency_pairs"])
        write_results_to_file(exchange_rates)

        execution_time = time.time() - start_time
        print(f"Received data in {execution_time:.2f} sec. Waiting {interval_seconds} seconds until next run...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
