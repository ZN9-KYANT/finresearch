"""SEC EDGAR structured data commands + ticker/CIK resolution."""

import functools
import json
import os
import sys
import time
import urllib.error

from .config import cache_dir
from .edgar_common import DATA_BASE, SEC_USER_AGENT, _get, _get_json  # noqa: F401  (UA re-export)
from .formatting import fmt_num, print_table

SEC_BASE = DATA_BASE
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def sec_get(url):
    """Fetch JSON from SEC EDGAR (shared polite fetcher: UA, pacing, timeout)."""
    return _get_json(url)


@functools.lru_cache(maxsize=1)
def company_tickers():
    """SEC company_tickers.json, cached on disk for a day and parsed once per run."""
    cache = cache_dir() / "company_tickers.json"
    if not cache.exists() or (time.time() - cache.stat().st_mtime) > 86400:
        data = _get(TICKERS_URL)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, cache)
    with open(cache) as f:
        return list(json.load(f).values())


@functools.lru_cache(maxsize=1)
def _ticker_index():
    return {v["ticker"].upper(): (str(v["cik_str"]).zfill(10), v["title"])
            for v in company_tickers()}


def find_cik(ticker):
    """Ticker -> (cik10, company title), or (None, None)."""
    return _ticker_index().get(ticker.upper(), (None, None))


def resolve_cik(ticker):
    """Ticker -> cik10 or None (network/cache failures are a miss, not a crash)."""
    try:
        return find_cik(ticker)[0]
    except Exception:
        return None


def _resolve_concept(concept):
    """Resolve a user-friendly concept name to its XBRL tag, with fallbacks."""
    aliases = {
        "revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "revenues": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "net_income": "NetIncomeLoss",
        "netincome": "NetIncomeLoss",
        "operating_income": "OperatingIncomeLoss",
        "operatingincome": "OperatingIncomeLoss",
        "eps": "EarningsPerShareBasic",
        "eps_basic": "EarningsPerShareBasic",
        "assets": "Assets",
        "liabilities": "Liabilities",
        "equity": "StockholdersEquity",
        "stockholders_equity": "StockholdersEquity",
        "cash": "CashAndCashEquivalentsAtCarryingValue",
        "debt": "LongTermDebt",
        "long_term_debt": "LongTermDebt",
        "shares": "CommonStockSharesOutstanding",
        "shares_outstanding": "CommonStockSharesOutstanding",
        "gross_profit": "GrossProfit",
        "grossprofit": "GrossProfit",
    }
    return aliases.get(concept.lower(), concept)


# Preferred unit order when a concept reports several
_UNIT_PREFERENCE = ("USD", "USD/shares", "shares", "pure")


def cmd_sec(args):
    """SEC EDGAR structured data."""
    ticker = args.ticker.upper()
    cik, name = find_cik(ticker)
    if not cik:
        print(f"ERROR: Ticker {ticker} not found in SEC EDGAR.", file=sys.stderr)
        sys.exit(1)

    print(f"\n# {name} ({ticker}) — CIK: {cik}\n")

    if args.type:
        # List recent filings of a specific type
        data = sec_get(f"{SEC_BASE}/submissions/CIK{cik}.json")
        r = data["filings"]["recent"]
        rows = []
        for i, form in enumerate(r["form"]):
            if form == args.type:
                date = r["filingDate"][i]
                doc = r["primaryDocument"][i][:60]
                rows.append([form, date, doc])
                if len(rows) >= 10:
                    break
        print_table(["Form", "Date", "Document"], rows, title=f"Recent {args.type} Filings")

    elif args.concept:
        concept = _resolve_concept(args.concept)
        url = f"{SEC_BASE}/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"
        try:
            units = sec_get(url)["units"]
        except (urllib.error.HTTPError, KeyError, ValueError):
            print(f"ERROR: Concept '{args.concept}' (resolved to '{concept}') not found "
                  f"for {ticker}.", file=sys.stderr)
            print("Try: revenue, net_income, operating_income, eps, assets, liabilities, "
                  "equity, cash, debt, shares, gross_profit", file=sys.stderr)
            sys.exit(1)
        unit_key = next((u for u in _UNIT_PREFERENCE if u in units), next(iter(units)))
        entries_data = units[unit_key]

        rows = []
        for e in entries_data[-12:]:
            val = e.get("val", 0)
            start = e.get("start", e.get("end", "N/A"))[:10]
            end = e.get("end", "N/A")[:10]
            form = e.get("form", "N/A")
            shown = f"{val:g}" if unit_key == "pure" else fmt_num(val, unit_key)
            rows.append([start, end, shown, form])
        print_table(["Start", "End", "Value", "Form"], rows, title=f"{concept} — {name} ({unit_key})")

    else:
        # Default: show key financial facts
        data = sec_get(f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json")
        us_gaap = data.get("facts", {}).get("us-gaap", {})

        key_metrics = [
            ("Revenues", "USD", "Revenue"),
            ("RevenueFromContractWithCustomerExcludingAssessedTax", "USD", "Revenue (Contract)"),
            ("NetIncomeLoss", "USD", "Net Income"),
            ("OperatingIncomeLoss", "USD", "Operating Income"),
            ("GrossProfit", "USD", "Gross Profit"),
            ("Assets", "USD", "Total Assets"),
            ("Liabilities", "USD", "Total Liabilities"),
            ("StockholdersEquity", "USD", "Shareholders' Equity"),
            ("CashAndCashEquivalentsAtCarryingValue", "USD", "Cash & Equivalents"),
            ("LongTermDebtNoncurrent", "USD", "Long-Term Debt"),
            ("LongTermDebt", "USD", "Long-Term Debt (alt)"),
            ("EarningsPerShareBasic", "USD/shares", "EPS (Basic)"),
            ("CommonStockSharesOutstanding", "shares", "Shares Outstanding"),
        ]

        rows = []
        for xbrl_tag, unit, label in key_metrics:
            if xbrl_tag in us_gaap:
                unit_key = list(us_gaap[xbrl_tag]["units"].keys())[0]
                latest = us_gaap[xbrl_tag]["units"][unit_key][-1]
                val = latest.get("val", "N/A")
                end = latest.get("end", "N/A")[:10]
                rows.append([label, fmt_num(val, unit_key), end])
            else:
                rows.append([label, "N/A", ""])

        print_table(["Metric", "Latest Value", "Period End"], rows, title="SEC EDGAR Financial Facts")

        # Show last 8 periods of revenue
        if "Revenues" in us_gaap:
            entries = us_gaap["Revenues"]["units"].get("USD", [])
            rows = []
            for e in entries[-8:]:
                start = e.get("start", "N/A")[:10]
                end = e.get("end", "N/A")[:10]
                form = e.get("form", "N/A")
                rows.append([start, end, fmt_num(e.get("val", 0)), form])
            print_table(["Start", "End", "Revenue", "Form"], rows, title="Revenue History (Last 8 Periods)")
