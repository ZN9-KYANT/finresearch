"""Stock screener — filter tickers by sector and fundamental metrics.

Uses yfinance to fetch data for a list of tickers, then applies filters.
No external API key needed — all via yfinance.

Usage:
    finresearch screen --tickers NVDA,AMD,AVGO,MU,QCOM --min-revgrowth 20 --max-pe 60
    finresearch screen --tickers NVDA,AMD,AVGO --json
    finresearch screen --tickers NVDA,AMD,AVGO,MU,QCOM,TSM,INTC --sort peg
"""

import json
import time

import yfinance as yf

from .config import load_watchlist
from .formatting import fmt_num, fmt_pct, print_table
from .output import fail


def _safe_float(val):
    """Convert to float, return None for NaN/None/str."""
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return f
    except (TypeError, ValueError):
        return None


def _fetch_ticker_data(ticker_symbol):
    """Fetch screening-relevant data for a single ticker."""
    try:
        t = yf.Ticker(ticker_symbol)
        info = t.info
        if not info or "quoteType" not in info:
            return {"ticker": ticker_symbol, "name": "ERROR: no Yahoo Finance quote",
                    "error": "no Yahoo Finance quote"}
        return {
            "ticker": ticker_symbol,
            "name": info.get("shortName", "N/A"),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "price": _safe_float(info.get("currentPrice")),
            "market_cap": _safe_float(info.get("marketCap")),
            "trailing_pe": _safe_float(info.get("trailingPE")),
            "forward_pe": _safe_float(info.get("forwardPE")),
            "peg_ratio": _safe_float(info.get("pegRatio")),
            "revenue": _safe_float(info.get("totalRevenue")),
            "revenue_growth": _safe_float(info.get("revenueGrowth")),  # Quarterly YoY
            "gross_margin": _safe_float(info.get("grossMargins")),
            "operating_margin": _safe_float(info.get("operatingMargins")),
            "profit_margin": _safe_float(info.get("profitMargins")),
            "debt_to_equity": _safe_float(info.get("debtToEquity")),
            "roe": _safe_float(info.get("returnOnEquity")),
            "fcf": _safe_float(info.get("freeCashflow")),
            "target_mean": _safe_float(info.get("targetMeanPrice")),
            "analysts": info.get("numberOfAnalystOpinions", 0),
            "recommendation": info.get("recommendationKey", "N/A"),
            "beta": _safe_float(info.get("beta")),
            # Yahoo dividendYield is PERCENT POINTS since yfinance 1.4.x; store
            # a normalized fraction so filter math (v >= t/100) stays consistent
            "dividend_yield": (_safe_float(info.get("dividendYield")) or 0) / 100
            if info.get("dividendYield") is not None else None,
            "currency": info.get("currency") or "USD",
        }
    except Exception as e:
        return {"ticker": ticker_symbol, "name": f"ERROR: {str(e)[:30]}", "error": str(e)}


def _passes_filters(data, args):
    """Check if a ticker passes all filter criteria."""
    if "error" in data:
        return False

    # A set filter needs the metric: a missing value FAILS it (no trailing P/E
    # must not sneak a loss-maker through --max-pe).
    filters = [
        ("min_pe", "trailing_pe", lambda v, t: v >= t),
        ("max_pe", "trailing_pe", lambda v, t: v <= t),
        ("min_fwd_pe", "forward_pe", lambda v, t: v >= t),
        ("max_fwd_pe", "forward_pe", lambda v, t: v <= t),
        ("min_peg", "peg_ratio", lambda v, t: v >= t),
        ("max_peg", "peg_ratio", lambda v, t: v <= t),
        ("min_revgrowth", "revenue_growth", lambda v, t: v >= t / 100),
        ("min_margin", "operating_margin", lambda v, t: v >= t / 100),
        ("max_debt_equity", "debt_to_equity", lambda v, t: v <= t),
        ("min_mktcap", "market_cap", lambda v, t: v >= t),
        ("max_mktcap", "market_cap", lambda v, t: v <= t),
        ("min_beta", "beta", lambda v, t: v >= t),
        ("max_beta", "beta", lambda v, t: v <= t),
    ]

    for arg_name, field, check in filters:
        threshold = getattr(args, arg_name, None)
        if threshold is not None:
            val = data.get(field)
            if val is None or not check(val, threshold):
                return False

    # Sector filter (substring match, case-insensitive)
    if args.sector:
        if args.sector.lower() not in (data.get("sector") or "").lower():
            return False

    # Industry filter
    if args.industry:
        if args.industry.lower() not in (data.get("industry") or "").lower():
            return False

    return True


def cmd_screen(args):
    """Screen stocks by fundamental metrics via yfinance."""
    # Parse tickers
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        # --watchlist, or no tickers given: config file (or neutral demo default)
        tickers = load_watchlist()

    results = []
    for i, ticker_symbol in enumerate(tickers):
        data = _fetch_ticker_data(ticker_symbol)
        passes = _passes_filters(data, args)
        data["_passes"] = passes
        results.append(data)
        if i < len(tickers) - 1:
            time.sleep(0.3)  # yfinance rate limiting

    # Filter to only passing tickers for display
    passing = [r for r in results if r.get("_passes")]
    failing = [r for r in results if not r.get("_passes") and "error" not in r]
    errored = [r for r in results if "error" in r]
    if results and len(errored) == len(results):
        fail("no data for any ticker: " + "; ".join(f"{r['ticker']}: {r['error'][:60]}"
                                                     for r in errored))

    # Sort
    sort_field = args.sort if args.sort else "market_cap"
    if sort_field == "pe":
        sort_field = "trailing_pe"
    elif sort_field == "fwd_pe":
        sort_field = "forward_pe"
    elif sort_field == "peg":
        sort_field = "peg_ratio"
    elif sort_field == "growth":
        sort_field = "revenue_growth"
    elif sort_field == "mktcap":
        sort_field = "market_cap"

    def sort_key(d):
        v = d.get(sort_field)
        return v if v is not None else float("-inf")

    passing.sort(key=sort_key, reverse=not args.ascending)

    if args.json:
        output = {
            "query": {
                "tickers": tickers,
                "filters": {
                    k: v for k, v in vars(args).items()
                    if v is not None and k not in ("command", "tickers", "json", "sort",
                                                   "ascending", "watchlist", "quiet")
                },
                "sort": sort_field,
            },
            "total_scanned": len(tickers),
            "total_passing": len(passing),
            "results": [{k: v for k, v in r.items() if k != "_passes"} for r in passing],
            "excluded": [{"ticker": r["ticker"], "name": r.get("name", "")} for r in failing],
            "errors": [{"ticker": r["ticker"], "error": r["error"]} for r in errored],
        }
        print(json.dumps(output, indent=2, default=str))
        return

    # Markdown output
    print("\n# Stock Screener\n")
    filter_desc = []
    if args.sector:
        filter_desc.append(f"sector={args.sector}")
    if args.min_pe is not None:
        filter_desc.append(f"P/E≥{args.min_pe}")
    if args.max_pe is not None:
        filter_desc.append(f"P/E≤{args.max_pe}")
    if args.max_peg is not None:
        filter_desc.append(f"PEG≤{args.max_peg}")
    if args.min_revgrowth is not None:
        filter_desc.append(f"rev growth≥{args.min_revgrowth}%")
    if args.max_fwd_pe is not None:
        filter_desc.append(f"fwd P/E≤{args.max_fwd_pe}")
    filters_str = " | ".join(filter_desc) if filter_desc else "no filters"
    print(f"**Scanned:** {len(tickers)} | **Passing:** {len(passing)} | **Filters:** {filters_str}\n")
    print(f"**Sort:** {sort_field} {'↑' if args.ascending else '↓'}\n")

    if passing:
        rows = []
        for r in passing:
            rows.append([
                r["ticker"],
                r.get("name", "N/A")[:25],
                fmt_num(r.get("price"), r.get("currency") or "USD"),
                fmt_num(r.get("market_cap"), r.get("currency") or "USD"),
                f"{r['trailing_pe']:.1f}" if r.get("trailing_pe") else "N/A",
                f"{r['forward_pe']:.1f}" if r.get("forward_pe") else "N/A",
                f"{r['peg_ratio']:.2f}" if r.get("peg_ratio") else "N/A",
                fmt_pct(r.get("revenue_growth")) if r.get("revenue_growth") else "N/A",
                fmt_pct(r.get("operating_margin")) if r.get("operating_margin") else "N/A",
                f"{r.get('beta', 'N/A'):.2f}" if r.get("beta") else "N/A",
                fmt_num(r.get("target_mean"), r.get("currency") or "USD"),
            ])
        print_table(
            ["Ticker", "Name", "Price", "Mkt Cap", "P/E", "Fwd P/E", "PEG", "Rev Growth", "Op Margin", "Beta", "Target"],
            rows,
            title="Screening Results",
        )
    else:
        print("*No tickers passed the filters.*\n")

    if failing and not args.quiet:
        print(f"\n## Excluded ({len(failing)})\n")
        excluded_str = ", ".join(f"{r['ticker']}" for r in failing)
        print(excluded_str)

    if errored:
        print(f"\n## Fetch errors ({len(errored)})\n")
        for r in errored:
            print(f"- {r['ticker']}: {r['error'][:80]}")
