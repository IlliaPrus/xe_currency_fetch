# Currency Exchange Rate Fetcher

A small service that collects exchange rates for a list of currency pairs from
[xe.com](https://www.xe.com/) at a set interval and saves them to a JSON file.
Pairs are fetched in parallel, failed requests are retried, and the
configuration can be changed on the fly without restarting the script.

## Features

- **Parallel requests** — `ThreadPoolExecutor` fetches all pairs at once.
- **Retries with backoff** — `requests` session with `urllib3` `Retry` for 429/5xx responses, plus request timeouts.
- **Hot config reload** — edits to `config.json` are picked up on the next cycle; an invalid config is rejected and the last valid one keeps running.
- **Config validation** — positive interval, pairs of 3-letter currency codes.
- **Resilient parsing** — looks for the rate element by CSS class and falls back to the page text (`1 USD = 0.92 EUR`) if the site layout changes; handles thousands separators.
- **Safe output** — results are written atomically, so readers never see a half-written file.
- **Unit tests** — 16 tests with mocked HTTP responses.

## How it works

```
config.json ──► validate ──► parallel requests to xe.com (retry + timeout)
            ──► parse rate (CSS class → text fallback) ──► exchange_rates.json ──► sleep ──► repeat
```

## Requirements

- Python 3.8+

## Setup

```sh
git clone https://github.com/<your-username>/xe_currency_fetch.git
cd xe_currency_fetch
pip3 install -r requirements.txt
```

## Configuration

`config.json`:

```json
{
  "interval_seconds": 15,
  "currency_pairs": [
    ["EUR", "GBP"],
    ["USD", "EUR"]
  ]
}
```

| Key | Description |
| --- | --- |
| `interval_seconds` | Pause between fetch cycles, in seconds (positive integer) |
| `currency_pairs` | List of `[from, to]` pairs of 3-letter currency codes |

Other settings (output file, timeout, retries, number of workers, CSS class of
the rate element) are in `config.py`.

## Usage

```sh
python3 main.py
```

Stop with `Ctrl+C`. Output in `exchange_rates.json`:

```json
{
    "timestamp": "2026-10-09T00:15:02.481233",
    "exchange_rates": [
        {"from": "EUR", "to": "GBP", "rate": 0.8421},
        {"from": "USD", "to": "EUR", "rate": 0.9213}
    ]
}
```

If a rate cannot be fetched, its `rate` is `null` and the other pairs are still saved.

## Testing

```sh
python3 -m unittest -v test_main
```

## Note

The script parses a public web page, so it depends on xe.com's layout. If rates
come back as `null`, update `RATE_CSS_CLASS` in `config.py`. Check the site's
terms of use before running it at short intervals; for production use, an
official exchange-rate API is the more reliable option.
