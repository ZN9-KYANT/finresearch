"""SEC EDGAR structured data commands + ticker/CIK resolution."""

import functools
import json
import os
import time
import urllib.error

from .config import cache_dir
from .edgar_common import DATA_BASE, SEC_USER_AGENT, _get, _get_json  # noqa: F401  (UA re-export)
from .formatting import fmt_num, print_table
from .output import emit_json, fail, warn

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


def resolve_ciks(tickers):
    """[(TICKER, cik10)] for the tickers SEC knows. Unknown ones get a [skip]
    notice on stderr; if none resolve at all, that's an error (exit 1)."""
    out = []
    for t in tickers:
        cik = resolve_cik(t)
        if cik:
            out.append((t.upper(), cik))
        else:
            warn(f"  [skip] {t}: no SEC CIK mapping found")
    if tickers and not out:
        fail(f"no SEC CIK found for: {', '.join(tickers)}")
    return out


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


def _fact_rows(us_gaap):
    """Latest value of each headline XBRL fact (None when not reported)."""
    out = []
    for tag, label in KEY_FACTS:
        units = us_gaap.get(tag, {}).get("units", {})
        if not units:
            out.append({"label": label, "tag": tag, "unit": None, "value": None,
                        "period_end": None})
            continue
        unit_key = next(iter(units))
        latest = units[unit_key][-1]
        out.append({"label": label, "tag": tag, "unit": unit_key, "value": latest.get("val"),
                    "period_end": (latest.get("end") or "")[:10] or None})
    return out


KEY_FACTS = [
    ("Revenues", "Revenue"),
    ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenue (Contract)"),
    ("NetIncomeLoss", "Net Income"),
    ("OperatingIncomeLoss", "Operating Income"),
    ("GrossProfit", "Gross Profit"),
    ("Assets", "Total Assets"),
    ("Liabilities", "Total Liabilities"),
    ("StockholdersEquity", "Shareholders' Equity"),
    ("CashAndCashEquivalentsAtCarryingValue", "Cash & Equivalents"),
    ("LongTermDebtNoncurrent", "Long-Term Debt"),
    ("LongTermDebt", "Long-Term Debt (alt)"),
    ("EarningsPerShareBasic", "EPS (Basic)"),
    ("CommonStockSharesOutstanding", "Shares Outstanding"),
]


def _observation(e):
    return {"start": (e.get("start") or "")[:10] or None, "end": (e.get("end") or "")[:10] or None,
            "value": e.get("val"), "form": e.get("form"), "filed": e.get("filed"),
            "fiscal_year": e.get("fy"), "fiscal_period": e.get("fp")}


def cmd_sec(args):
    """SEC EDGAR structured data: key facts, filings by type, or one XBRL concept."""
    ticker = args.ticker.upper()
    cik, name = find_cik(ticker)
    if not cik:
        fail(f"ticker {ticker} not found in SEC EDGAR")
    as_json = getattr(args, "json", False)
    base = {"ticker": ticker, "cik": cik, "company": name}

    if args.type:
        r = sec_get(f"{SEC_BASE}/submissions/CIK{cik}.json")["filings"]["recent"]
        filings = [{"form": form, "filing_date": r["filingDate"][i],
                    "accession": r["accessionNumber"][i],
                    "primary_document": r["primaryDocument"][i]}
                   for i, form in enumerate(r["form"]) if form == args.type][:10]
        if as_json:
            emit_json({**base, "form": args.type, "filings": filings})
            return
        print(f"\n# {name} ({ticker}) — CIK: {cik}\n")
        print_table(["Form", "Date", "Document"],
                    [[f["form"], f["filing_date"], f["primary_document"][:60]] for f in filings],
                    title=f"Recent {args.type} Filings")

    elif args.concept:
        concept = _resolve_concept(args.concept)
        url = f"{SEC_BASE}/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"
        try:
            units = sec_get(url)["units"]
        except (urllib.error.HTTPError, KeyError, ValueError):
            fail(f"concept '{args.concept}' (resolved to '{concept}') not found for {ticker}. "
                 "Try: revenue, net_income, operating_income, eps, assets, liabilities, "
                 "equity, cash, debt, shares, gross_profit")
        unit_key = next((u for u in _UNIT_PREFERENCE if u in units), next(iter(units)))
        entries = units[unit_key]
        if as_json:  # full history; the table shows the last 12
            emit_json({**base, "concept": concept, "unit": unit_key,
                       "observations": [_observation(e) for e in entries]})
            return
        print(f"\n# {name} ({ticker}) — CIK: {cik}\n")
        rows = []
        for e in entries[-12:]:
            o = _observation(e)
            val = o["value"] if o["value"] is not None else 0
            shown = f"{val:g}" if unit_key == "pure" else fmt_num(val, unit_key)
            rows.append([o["start"] or o["end"] or "N/A", o["end"] or "N/A", shown,
                         o["form"] or "N/A"])
        print_table(["Start", "End", "Value", "Form"], rows,
                    title=f"{concept} — {name} ({unit_key})")

    else:
        us_gaap = sec_get(f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json") \
            .get("facts", {}).get("us-gaap", {})
        facts = _fact_rows(us_gaap)
        revenue = [_observation(e) for e in
                   us_gaap.get("Revenues", {}).get("units", {}).get("USD", [])[-8:]]
        if as_json:
            emit_json({**base, "facts": facts, "revenue_history": revenue})
            return
        print(f"\n# {name} ({ticker}) — CIK: {cik}\n")
        print_table(["Metric", "Latest Value", "Period End"],
                    [[f["label"], fmt_num(f["value"], f["unit"]) if f["unit"] else "N/A",
                      f["period_end"] or ""] for f in facts],
                    title="SEC EDGAR Financial Facts")
        if revenue:
            print_table(["Start", "End", "Revenue", "Form"],
                        [[o["start"] or "N/A", o["end"] or "N/A", fmt_num(o["value"] or 0),
                          o["form"] or "N/A"] for o in revenue],
                        title="Revenue History (Last 8 Periods)")
