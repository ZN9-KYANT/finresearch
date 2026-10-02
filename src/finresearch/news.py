"""News headlines for a ticker via Google Finance SSR (no JS rendering needed).

Also the shared Google Finance helper for `gappers` catalyst lookups.
"""

import json
import re
import time
from html import unescape

import requests
from bs4 import BeautifulSoup

from .output import fail

# Google Finance quote URL — SSR, works with plain requests
GF_URL = "https://www.google.com/finance/quote/{ticker}:{exchange}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

# Exchange codes as other sources spell them -> Google Finance's spelling
EXCHANGE_MAP = {
    "NASDAQ": "NASDAQ",
    "NYSE": "NYSE",
    "NYSEARCA": "NYSEARCA",
    "NYSE ARCA": "NYSEARCA",
    "AMEX": "NYSEAMERICAN",
}
_PROBE_ORDER = ("NASDAQ", "NYSE", "NYSEARCA", "NYSEAMERICAN")
_NAV_WORDS = ("about", "news", "overview", "financials", "forecast")


def fetch_quote_page(ticker, exchange=None):
    """(exchange, html) for a ticker's Google Finance page, or (None, None).

    A known exchange is tried first; otherwise US exchanges are probed in turn."""
    first = EXCHANGE_MAP.get((exchange or "").upper())
    order = [first] + [e for e in _PROBE_ORDER if e != first] if first else list(_PROBE_ORDER)
    for i, ex in enumerate(order):
        if i:
            time.sleep(0.2)
        try:
            resp = requests.get(GF_URL.format(ticker=ticker, exchange=ex), headers=HEADERS,
                                timeout=10, allow_redirects=True)
        except requests.RequestException:
            continue
        # unknown symbols still get a 200 page; a real quote's <title> names
        # the ticker: "Apple Inc (AAPL) Stock Price & News - Google Finance"
        if resp.status_code == 200 and f"({ticker.upper()})" in _title(resp.text):
            return ex, resp.text
    return None, None


def _title(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    return unescape(m.group(1)).strip() if m else ""


def parse_headlines(html, max_items=15):
    """External news links ({title, url}) from Google Finance SSR HTML, deduped."""
    soup = BeautifulSoup(html, "html.parser")
    seen, unique = set(), []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        # External news article links (not Google Finance internal nav)
        if not href.startswith("https://") or "google.com/finance" in href \
                or "google.com/search" in href:
            continue
        title = a.get_text(strip=True)
        if not title or not 10 < len(title) < 300 or title.lower() in _NAV_WORDS:
            continue
        key = title[:60]
        if key not in seen:
            seen.add(key)
            unique.append({"title": title, "url": href})
            if len(unique) >= max_items:
                break
    return unique


def _parse_price_info(html):
    """Company name (from the page title) and last price from a quote page."""
    info = {}
    m = re.match(r"(.+?) \([A-Z0-9.\-]+\) Stock Price", _title(html))
    if m:
        info["name"] = m.group(1)
    # the quote's own price sits behind a "Current" label; other price spans on
    # the page belong to the market ticker bar. ETF pages have no such label:
    # better no price than a wrong one.
    m = re.search(r'Current <span jsname="Pdsbrc"[^>]*><span>([^<]+)</span>', html)
    if m:
        try:
            info["price"] = float(re.sub(r"[^\d.\-]", "", m.group(1)))
        except ValueError:
            pass
    return info


def cmd_news(args):
    """Fetch news headlines for a ticker via Google Finance."""
    ticker = args.ticker.upper()
    max_items = args.max_items or 15
    json_output = getattr(args, "json", False)

    exchange, html = fetch_quote_page(ticker)

    if not html:
        fail(f"ticker {ticker} not found on Google Finance")

    headlines = parse_headlines(html, max_items)
    price_info = _parse_price_info(html)
    name = price_info.get("name", ticker)

    if json_output:
        print(json.dumps({
            "ticker": ticker,
            "exchange": exchange,
            "name": name,
            "price": price_info.get("price"),
            "headlines": headlines,
            "source": "google_finance",
        }, indent=2))
        return

    print(f"\n# News for {name} ({ticker})\n")
    if price_info.get("price"):
        print(f"**Price:** ${price_info['price']:,.2f} | **Exchange:** {exchange}\n")

    if headlines:
        print(f"## Recent Headlines ({len(headlines)} found)\n")
        for i, h in enumerate(headlines, 1):
            print(f"{i}. [{h['title']}]({h['url']})")
    else:
        print("## Recent Headlines\n\n*No headlines found via Google Finance SSR.*\n")

    print("\n---\n*Source: Google Finance*")
