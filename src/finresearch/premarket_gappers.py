"""Premarket gappers scanner — top gap-up stocks with real premarket data.

DATA SOURCES (primary to fallback):
  1. TradingView Web — https://www.tradingview.com/markets/stocks-usa/
     market-movers-pre-market-gappers/
     SSR HTML, ~100 rows, explicit premarket gap%/price/volume
  2. Stock Analysis — https://stockanalysis.com/markets/premarket/gainers/
     SvelteKit SSR inline script, ~20-27 rows

Both sources are accessible via raw HTTP (no JS rendering required).
Core dependencies: requests, beautifulsoup4.

CATALYST SOURCES (optional, for news headlines):
  1. google_finance — https://www.google.com/finance/quote/{TICKER}:{EXCHANGE}
     SSR HTML, works with plain requests. Default, no extra deps.
  2. crawl4ai — Uses crawl4ai CLI (crwl) for JS-rendered pages.
     Supports TradingView news and Yahoo Finance.
     Requires crawl4ai installed (`pip install crawl4ai`).
     TV news URL: /symbols/{EXCHANGE}-{TICKER}/news/
  3. none — Skip catalyst lookup entirely.

Use --catalyst to select source, or --no-catalyst to skip.
"""

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .config import cache_dir
from .formatting import print_table
from .news import fetch_quote_page, parse_headlines
from .output import warn

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_MIN_GAP_PCT = 5.0
DEFAULT_MIN_PRICE = 3.0
DEFAULT_MIN_VOLUME = 50_000
DEFAULT_MAX_RESULTS = 10
OUTPUT_DIR = cache_dir() / "gappers"

TV_GAPPERS_URL = (
    "https://www.tradingview.com/markets/stocks-usa/"
    "market-movers-pre-market-gappers/"
)
SA_GAPPERS_URL = "https://stockanalysis.com/markets/premarket/gainers/"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Data fetching — TradingView Web (SSR HTML)
# ---------------------------------------------------------------------------

def _parse_tv_volume(text: str) -> float:
    """Parse TV volume: '14.89 M' -> 14890000."""
    if not text or text in ("—", "-", ""):
        return 0
    text = text.strip().replace(",", "").replace(" ", "").replace("\u202f", "")
    try:
        if text.upper().endswith("K"):
            return float(text[:-1]) * 1_000
        if text.upper().endswith("M"):
            return float(text[:-1]) * 1_000_000
        if text.upper().endswith("B"):
            return float(text[:-1]) * 1_000_000_000
        return float(text)
    except (ValueError, IndexError):
        return 0


def _parse_tv_pct(text: str) -> float:
    """Parse TV percentage: '+218.18%' -> 218.18, '−64.88%' -> -64.88."""
    if not text or text in ("—", "-"):
        return 0
    cleaned = text.replace("%", "").replace("+", "").replace(" ", "").strip()
    cleaned = cleaned.replace("\u2212", "-").replace("−", "-")
    try:
        return float(cleaned)
    except ValueError:
        return 0


def _parse_tv_price(text: str) -> float:
    """Parse TV price: '2.04 USD' -> 2.04."""
    if not text or text in ("—", "-"):
        return 0
    cleaned = text.replace("USD", "").replace(",", "").replace(" ", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0


def _fetch_gappers_tradingview() -> list[dict]:
    """Fetch premarket gappers from TradingView web (SSR HTML).

    Returns list of dicts with premarket fields.
    """
    try:
        resp = requests.get(TV_GAPPERS_URL, headers={"User-Agent": UA}, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        warn(f"  TradingView fetch failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        warn("  TradingView: no tables found in HTML")
        return []

    # Find the gappers table — it has 'Pre-mkt gap' in headers
    target_table = None
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if any("gap" in h.lower() for h in headers):
            target_table = table
            break

    if not target_table:
        # Fallback: use the largest table
        target_table = max(tables, key=lambda t: len(t.find_all("tr")))

    rows = target_table.find_all("tr")
    gappers = []

    for row in rows[1:]:  # skip header
        cells = row.find_all("td")
        if len(cells) < 9:  # symbol + 8 data columns are read unconditionally below
            continue

        # Symbol cell: ticker link + name link
        symbol_cell = cells[0]
        links = symbol_cell.find_all("a")
        ticker_link = links[0] if links else None
        name_link = links[1] if len(links) > 1 else None

        ticker = ticker_link.get_text(strip=True) if ticker_link else ""
        name = name_link.get_text(strip=True) if name_link else ""

        # Exchange from data-rowkey or href
        rowkey = row.get("data-rowkey") or ""
        if ":" in rowkey:
            exchange = rowkey.split(":")[0]
            symbol = rowkey
        else:
            href = ticker_link.get("href", "") if ticker_link else ""
            ex_match = re.search(r"symbols/([A-Z]+)-", href)
            exchange = ex_match.group(1) if ex_match else ""
            symbol = f"{exchange}:{ticker}" if exchange else ticker

        gappers.append({
            "symbol": symbol,
            "ticker": ticker,
            "exchange": exchange,
            "name": name,
            "premarket_gap_pct": _parse_tv_pct(cells[1].get_text(strip=True)),
            "premarket_price": _parse_tv_price(cells[2].get_text(strip=True)),
            "premarket_chg": _parse_tv_price(cells[3].get_text(strip=True)),
            "premarket_chg_pct": _parse_tv_pct(cells[4].get_text(strip=True)),
            "premarket_volume": _parse_tv_volume(cells[5].get_text(strip=True)),
            "close_price": _parse_tv_price(cells[6].get_text(strip=True)),
            "chg_pct": _parse_tv_pct(cells[7].get_text(strip=True)),
            "volume": _parse_tv_volume(cells[8].get_text(strip=True)),
            "mkt_cap": cells[9].get_text(strip=True) if len(cells) > 9 else "",
            "mkt_cap_perf_1y": _parse_tv_pct(cells[10].get_text(strip=True)) if len(cells) > 10 else 0,
            "source": "tradingview",
        })

    return gappers


# ---------------------------------------------------------------------------
# Data fetching — Stock Analysis (SSR inline script)
# ---------------------------------------------------------------------------

def _fetch_gappers_stockanalysis() -> list[dict]:
    """Fetch premarket gappers from Stock Analysis (SSR inline script data).

    Returns list of dicts with premarket fields.
    """
    try:
        resp = requests.get(SA_GAPPERS_URL, headers={"User-Agent": UA}, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        warn(f"  Stock Analysis fetch failed: {e}")
        return []

    html = resp.text

    # Extract SvelteKit inline script data objects
    pattern = (
        r'\{no:(\d+),s:"([^"]+?)",n:"([^"]+?)",'
        r'premarketChangePercent:([\d.\-]+),premarketDate:"([^"]+?)",'
        r'premarketPrice:([\d.\-]+),premarketVolume:(\d+),marketCap:(\d+)\}'
    )
    matches = re.findall(pattern, html)

    if not matches:
        warn("  Stock Analysis: no premarket data objects found in HTML")
        return []

    gappers = []
    for m in matches:
        no, ticker, name, chg_pct, date, price, vol, mcap = m
        gappers.append({
            "symbol": ticker,
            "ticker": ticker,
            "exchange": "",
            "name": name,
            "premarket_gap_pct": float(chg_pct),
            "premarket_price": float(price),
            "premarket_chg": 0,
            "premarket_chg_pct": float(chg_pct),
            "premarket_volume": int(vol),
            "close_price": 0,
            "chg_pct": 0,
            "volume": 0,
            "mkt_cap": f"${int(mcap):,}" if int(mcap) > 0 else "",
            "mkt_cap_perf_1y": 0,
            "source": "stockanalysis",
        })

    return gappers


# ---------------------------------------------------------------------------
# Catalyst lookup — Google Finance (SSR HTML, requests-only)
# ---------------------------------------------------------------------------

def _fetch_catalyst_google(symbol: str) -> dict:
    """Fetch news catalyst from Google Finance (SSR HTML, no JS needed).

    Returns {catalyst: str|None, headlines: list[str]}.
    """
    exchange, ticker = symbol.split(":", 1) if ":" in symbol else ("", symbol)
    _ex, html = fetch_quote_page(ticker, exchange or None)
    headlines = [h["title"] for h in parse_headlines(html, max_items=3)] if html else []
    return {"catalyst": headlines[0] if headlines else None, "headlines": headlines}


# ---------------------------------------------------------------------------
# Catalyst lookup — crawl4ai (JS-rendered pages)
# ---------------------------------------------------------------------------

def _crwl_extract_headlines(md: str, url: str) -> list[str]:
    """Extract news headlines from crawl4ai markdown output.

    Handles TradingView, Yahoo Finance, and Google Finance markdown formats.
    """
    headlines = []

    # Determine source from URL for source-specific parsing
    is_tv = "tradingview.com/symbols" in url and "/news" in url

    # Pattern 1: TradingView news page
    # Format: "Stock Story Headline text ](https://www.tradingview.com/news/...)["
    # or: "Jun 4 Reuters Headline text ](https://www.tradingview.com/news/...)["
    # or: "Feb 5GlobeNewswire Headline text ](https://www.tradingview.com/news/...)["
    if is_tv:
        # TV crawl4ai markdown doesn't use standard [text](url) link format.
        # News items appear as lines like:
        #   "Stock Story Headline text ](https://www.tradingview.com/news/...)["
        #   "Jun 4 Reuters Headline text ](https://www.tradingview.com/news/...)["
        #   "Feb 5GlobeNewswire Headline text ](https://www.tradingview.com/news/...)["
        # Extract the text BEFORE ](tv_news_url) on each line.

        tv_pattern = r'(.+?)\s*\]\(https?://www\.tradingview\.com/news/'
        tv_matches = re.findall(tv_pattern, md)
        for h in tv_matches:
            h = h.strip()
            # Skip non-headline matches (nav, sectors, etc.)
            skip_exact = {"latest headlines", "more in news flow", "news", "news flow"}
            if h.lower().rstrip() in skip_exact:
                continue
            # Remove leading date (e.g., "Jun 4", "Feb 5", "Aug 30, 2025")
            h = re.sub(r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:,?\s*\d{4})?\s*', '', h)
            # Remove leading provider name
            for prefix in ["Stock Story ", "Reuters ", "TradingView ", "Dow Jones Newswires ",
                            "MarketWatch ", "Benzinga ", "Investing.com ", "GlobeNewswire ",
                            "MarketBeat ", "Quartr "]:
                if h.startswith(prefix):
                    h = h[len(prefix):]
                    break
            # Skip paywalled/placeholder items
            if h.lower() in ("sign in to read exclusive news", ""):
                continue
            # Clean whitespace and newlines
            h = h.strip().replace('\n', ' ').replace('\ufeff', '')
            h = re.sub(r'\s{2,}', ' ', h)
            if 15 <= len(h) <= 200:
                headlines.append(h)
        if headlines:
            return headlines

    # Pattern 2: Yahoo Finance — numbered list with timestamps
    # e.g., "1. [ News • 2 hours ago Some headline text ](url)"
    numbered = re.findall(
        r'\d+\.\s*\[\s*(?:News|Breaking News)\s*[•\-]\s*\d+\s*(?:hour|day|minute)s?\s+ago\s+(.*?)\s*\]',
        md, re.IGNORECASE
    )
    for h in numbered:
        h = h.strip()
        if len(h) > 15 and len(h) < 200:
            headlines.append(h)

    if headlines:
        return headlines

    # Pattern 3: generic linked headlines
    link_heads = re.findall(r'\[\s*(.*?)\s*\]\(https?://[^)]*\)', md)
    skip_words = [
        "trending", "markets open", "yahoo finance", "sign in", "portfolio",
        "download", "app store", "google play", "skip to", "navigation",
        "latest headlines", "more in news", "show more", "see on supercharts",
        "commercial services", "advertising/marketing", "ice data services",
    ]
    for h in link_heads:
        h = h.strip()
        if len(h) > 15 and len(h) < 200:
            if any(w in h.lower() for w in skip_words):
                continue
            headlines.append(h)

    return headlines


def _fetch_catalyst_crawl4ai(symbol: str) -> dict:
    """Fetch news catalyst via crawl4ai CLI (crwl).

    Tries TradingView news first (ticker-specific, high quality),
    falls back to Yahoo Finance, then Google Finance.
    Requires crawl4ai installed (`pip install crawl4ai`).

    Returns {catalyst: str|None, headlines: list[str]}.
    """
    ticker = symbol.split(":")[-1] if ":" in symbol else symbol
    exchange = symbol.split(":")[0] if ":" in symbol else ""

    # Map exchange format for TradingView URL: NASDAQ → NASDAQ, NYSE → NYSE
    tv_exchange_map = {
        "NASDAQ": "NASDAQ", "NYSE": "NYSE", "NYSE ARCA": "NYSE",
        "AMEX": "AMEX", "BATS": "BATS",
    }
    tv_exchange = tv_exchange_map.get(exchange, "NASDAQ" if not exchange else exchange)

    # Source 1: TradingView /symbols/{EXCHANGE}-{TICKER}/news/
    # Best quality — ticker-specific, no account needed
    tv_url = f"https://www.tradingview.com/symbols/{tv_exchange}-{ticker}/news/"
    try:
        result = subprocess.run(
            ["crwl", "crawl", "-o", "markdown", "-b", "wait=3", tv_url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            headlines = _crwl_extract_headlines(result.stdout, tv_url)
            if headlines:
                return {"catalyst": headlines[0], "headlines": headlines[:3]}
    except FileNotFoundError:
        warn("    crawl4ai (crwl) not found. Install with: pip install crawl4ai")
        warn("    Falling back to Google Finance (requests-only)...")
        return _fetch_catalyst_google(symbol)
    except Exception as e:
        warn(f"    crawl4ai TradingView failed: {e}")

    # Source 2: Yahoo Finance (JS-rendered, needs crawl4ai)
    yf_url = f"https://finance.yahoo.com/quote/{ticker}/news/"
    try:
        result = subprocess.run(
            ["crwl", "crawl", "-o", "markdown", yf_url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            headlines = _crwl_extract_headlines(result.stdout, yf_url)
            if headlines:
                return {"catalyst": headlines[0], "headlines": headlines[:3]}
    except Exception as e:
        warn(f"    crawl4ai Yahoo Finance failed: {e}")

    # Source 3: Fallback to Google Finance (requests-only, always available)
    return _fetch_catalyst_google(symbol)


# ---------------------------------------------------------------------------
# Catalyst dispatcher
# ---------------------------------------------------------------------------

def _fetch_catalyst(symbol: str, source: str = "google_finance") -> dict:
    """Fetch news catalyst for a ticker.

    Args:
        source: "google_finance" (default, requests-only),
                "crawl4ai" (JS-rendered pages via crwl CLI),
                "none" (skip).

    Returns {catalyst: str|None, headlines: list[str]}.
    """
    if source == "none":
        return {"catalyst": None, "headlines": []}
    elif source == "crawl4ai":
        return _fetch_catalyst_crawl4ai(symbol)
    else:  # google_finance (default)
        return _fetch_catalyst_google(symbol)


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------

def scan_gappers(
    min_gap_pct: float = DEFAULT_MIN_GAP_PCT,
    min_price: float = DEFAULT_MIN_PRICE,
    min_volume: int = DEFAULT_MIN_VOLUME,
    max_results: int = DEFAULT_MAX_RESULTS,
    catalyst_source: str = "google_finance",
    source: str = "auto",
    verbose: bool = True,
) -> dict:
    """Run the premarket gappers scan.

    Args:
        catalyst_source: "google_finance" (default, requests-only),
                         "crawl4ai" (JS-rendered, needs crawl4ai),
                         "none" (skip catalyst lookup).
        source: "auto" (try TV then SA), "tradingview", "stockanalysis"
        verbose: Print progress messages (False for JSON output mode)

    Returns dict: {scanned_at, source, total_raw, gappers: [...]}
    """
    scanned_at = datetime.now(timezone.utc).isoformat()

    # Step 1: Fetch from source(s)
    raw = []
    source_used = ""

    if source in ("auto", "tradingview"):
        raw = _fetch_gappers_tradingview()
        source_used = "tradingview"

    if not raw and source in ("auto", "stockanalysis"):
        raw = _fetch_gappers_stockanalysis()
        source_used = "stockanalysis"

    if not raw:
        if verbose:
            print("  No gappers data retrieved from any source.")
        return {"scanned_at": scanned_at, "source": source_used, "total_raw": 0, "gappers": []}

    total_raw = len(raw)

    # Step 2: Filter
    filtered = [
        g for g in raw
        if g.get("premarket_gap_pct", 0) >= min_gap_pct
        and g.get("premarket_price", 0) >= min_price
        and g.get("premarket_volume", 0) >= min_volume
    ]

    # Step 3: Sort by gap desc, cap results
    filtered.sort(key=lambda g: g.get("premarket_gap_pct", 0), reverse=True)
    filtered = filtered[:max_results]

    # Step 4: Add rank + optional catalyst
    gappers = []
    for i, g in enumerate(filtered, 1):
        entry = {**g, "rank": i}

        if catalyst_source != "none":
            if verbose:
                print(f"  Fetching catalyst for {g['symbol']}...")
            cat = _fetch_catalyst(g["symbol"], source=catalyst_source)
            entry["catalyst"] = cat.get("catalyst")
            entry["headlines"] = cat.get("headlines", [])
            time.sleep(0.5)
        else:
            entry["catalyst"] = None
            entry["headlines"] = []

        gappers.append(entry)

    return {
        "scanned_at": scanned_at,
        "source": source_used,
        "total_raw": total_raw,
        "gappers": gappers,
    }


def save_results(data: dict, output_dir: Path = OUTPUT_DIR) -> Path:
    """Save scan results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = output_dir / f"premarket_gappers_{date_str}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def print_summary(data: dict) -> str:
    """One-line summary of the scan results."""
    gappers = data.get("gappers", [])
    n = len(gappers)
    total = data.get("total_raw", 0)
    src = data.get("source", "?")

    if n == 0:
        return f"Premarket Gappers: 0/{total} from {src} passed filters."

    top3 = gappers[:3]
    parts = []
    for g in top3:
        cat = g.get("catalyst") or "no catalyst"
        if len(cat) > 50:
            cat = cat[:47] + "..."
        parts.append(f"{g['symbol']} ({g['premarket_gap_pct']:+.1f}%) - {cat}")

    return f"Premarket Gappers: {n}/{total} from {src}. Top: " + ", ".join(parts)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cmd_gappers(args):
    """CLI handler for `finresearch gappers`."""
    min_gap = getattr(args, "min_gap", DEFAULT_MIN_GAP_PCT)
    min_price = getattr(args, "min_price", DEFAULT_MIN_PRICE)
    min_vol = getattr(args, "min_volume", DEFAULT_MIN_VOLUME)
    max_results = getattr(args, "max_results", DEFAULT_MAX_RESULTS)
    no_catalyst = getattr(args, "no_catalyst", False)
    catalyst = getattr(args, "catalyst", None)
    output_dir = getattr(args, "output_dir", None)
    source = getattr(args, "source", "auto")
    output_format = getattr(args, "output_format", "markdown")

    # Determine catalyst source
    if no_catalyst:
        catalyst_source = "none"
    elif catalyst:
        catalyst_source = catalyst
    else:
        catalyst_source = "google_finance"

    if output_dir:
        out_path = Path(output_dir)
    else:
        out_path = OUTPUT_DIR

    if output_format != "json":
        print("\n# Premarket Gappers Scanner\n")
        print(f"  Source: {source} (TradingView web + Stock Analysis fallback)")
        print(f"  Filters: gap >= {min_gap}%, price >= ${min_price}, vol >= {min_vol:,}")
        print(f"  Max results: {max_results}")
        print(f"  Catalyst source: {catalyst_source}")
        print()

    data = scan_gappers(
        min_gap_pct=min_gap,
        min_price=min_price,
        min_volume=min_vol,
        max_results=max_results,
        catalyst_source=catalyst_source,
        source=source,
        verbose=output_format != "json",
    )

    # Always save JSON file
    path = save_results(data, output_dir=out_path)
    if output_format != "json":
        print(f"\n  Saved: {path}")

    # JSON output: print the entire result and exit
    if output_format == "json":
        print(json.dumps(data, indent=2))
        return data

    # Markdown output (default)
    gappers = data.get("gappers", [])
    if gappers:
        rows = []
        for g in gappers:
            cat = g.get("catalyst") or "N/A"
            if len(cat) > 50:
                cat = cat[:47] + "..."
            rows.append([
                g["rank"],
                g["symbol"],
                f"${g['premarket_price']:.2f}",
                f"{g['premarket_gap_pct']:+.1f}%",
                f"{g['premarket_volume']:,.0f}",
                f"${g['close_price']:.2f}",
                cat,
            ])
        print_table(
            ["#", "Symbol", "PM Price", "PM Gap%", "PM Vol", "Close", "Catalyst"],
            rows,
            title="Top Premarket Gappers",
        )

        # Headlines detail
        for g in gappers:
            headlines = g.get("headlines", [])
            if headlines:
                print(f"\n  {g['symbol']} headlines:")
                for h in headlines:
                    print(f"    - {h}")

    # Summary
    summary = print_summary(data)
    print(f"\n  {summary}\n")

    return data
