BASE_URL = "https://www.xe.com/currencyconverter/convert/"
DEFAULT_AMOUNT = 1
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
}
# CSS class of the element with the rate on xe.com. The site generates these class names,
# so they change after redesigns; if so, update it here (a text-based fallback is used meanwhile).
RATE_CSS_CLASS = "sc-63d8b7e3-1 bMdPIi"
REQUEST_TIMEOUT = 10  # seconds
MAX_WORKERS = 5
RETRY_COUNT = 3
BACKOFF_FACTOR = 0.1
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]
CONFIG_FILE = 'config.json'
OUTPUT_FILE = 'exchange_rates.json'
