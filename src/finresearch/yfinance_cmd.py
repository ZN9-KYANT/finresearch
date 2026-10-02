"""yfinance ticker data commands.

Currency contract (verified live, e.g. TSM = USD-listed ADR of a TWD reporter):
  * info['currency'] (LISTING currency): price, 52w/MA levels, market cap, EPS,
    analyst targets, holder position values.
  * info['financialCurrency'] (REPORTING currency): revenue, gross profit,
    EBITDA, free cash flow, financial statements, revenue estimates.
For most listings the two are the same; for ADRs they are not.
"""

import time

import numpy as np
import pandas as pd
import yfinance as yf

from .formatting import fmt_date, fmt_num, fmt_pct, print_table
from .output import emit_json, fail


def get_ticker(ticker_symbol):
    """Get yfinance Ticker object."""
    return yf.Ticker(ticker_symbol)


def _safe(val):
    """Convert numpy/pandas values to JSON-safe Python types."""
    if val is None or val is pd.NA or val is pd.NaT:
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        if np.isnan(val):
            return None
        return float(val)
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, float) and val != val:  # NaN
        return None
    return val


def _is_num(v):
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) \
        and v == v


def _fmt(kind, v, cur, fin_cur):
    """Render one metric by kind (see INFO_SECTIONS)."""
    if kind == "str":
        return str(v) if v not in (None, "") else "N/A"
    if not _is_num(v):
        return "N/A"
    if kind == "cur":
        return fmt_num(v, cur)
    if kind == "fin":
        return fmt_num(v, fin_cur)
    if kind == "eps":
        return fmt_num(v, f"{cur}/shares")
    if kind == "shares":
        return fmt_num(v, "shares")
    if kind == "pct":
        return fmt_pct(v)
    if kind == "pct_points":
        return fmt_pct(v, percent_units=True)
    if kind == "x1":
        return f"{v:.1f}"
    if kind == "x2":
        return f"{v:.2f}"
    if kind == "int":
        return f"{int(v):,}"
    raise ValueError(kind)


# (json section, markdown title, [(json key, info key, label, kind)])
INFO_SECTIONS = [
    ("overview", "Price & Valuation", [
        ("price", "currentPrice", "Price", "cur"),
        ("52w_high", "fiftyTwoWeekHigh", "52w High", "cur"),
        ("52w_low", "fiftyTwoWeekLow", "52w Low", "cur"),
        ("50d_ma", "fiftyDayAverage", "50-day MA", "cur"),
        ("200d_ma", "twoHundredDayAverage", "200-day MA", "cur"),
        ("avg_volume", "averageVolume", "Volume (avg)", "shares"),
        ("shares_outstanding", "sharesOutstanding", "Shares Out", "shares"),
        ("float_shares", "floatShares", "Float", "shares"),
        ("short_pct_float", "shortPercentOfFloat", "Short % Float", "pct"),
        ("short_ratio", "shortRatio", "Short Ratio (days)", "x2"),
    ]),
    ("valuation", "Valuation Metrics", [
        ("eps_ttm", "trailingEps", "EPS (TTM)", "eps"),
        ("eps_fwd", "forwardEps", "EPS (Fwd)", "eps"),
        ("pe_ttm", "trailingPE", "P/E (TTM)", "x1"),
        ("pe_fwd", "forwardPE", "P/E (Fwd)", "x1"),
        ("peg_ratio", "pegRatio", "PEG Ratio", "x2"),
        ("price_to_book", "priceToBook", "Price/Book", "x2"),
        ("ev_to_ebitda", "enterpriseToEbitda", "EV/EBITDA", "x1"),
        ("ev_to_revenue", "enterpriseToRevenue", "EV/Revenue", "x2"),
        # yfinance >= 1.4 serves dividendYield in percent points
        ("dividend_yield", "dividendYield", "Div Yield", "pct_points"),
        ("payout_ratio", "payoutRatio", "Payout Ratio", "pct"),
    ]),
    ("profitability", "Profitability & Efficiency", [
        ("revenue", "totalRevenue", "Revenue", "fin"),
        ("gross_profit", "grossProfits", "Gross Profit", "fin"),
        ("ebitda", "ebitda", "EBITDA", "fin"),
        ("gross_margin", "grossMargins", "Gross Margin", "pct"),
        ("operating_margin", "operatingMargins", "Operating Margin", "pct"),
        ("profit_margin", "profitMargins", "Profit Margin", "pct"),
        ("roe", "returnOnEquity", "Return on Equity", "pct"),
        ("roa", "returnOnAssets", "Return on Assets", "pct"),
        ("debt_to_equity", "debtToEquity", "Debt/Equity", "x2"),
    ]),
    ("analyst", "Analyst Consensus", [
        ("target_mean", "targetMeanPrice", "Target Mean", "cur"),
        ("target_median", "targetMedianPrice", "Target Median", "cur"),
        ("target_high", "targetHighPrice", "Target High", "cur"),
        ("target_low", "targetLowPrice", "Target Low", "cur"),
        ("num_analysts", "numberOfAnalystOpinions", "# Analysts", "int"),
        ("recommendation", "recommendationKey", "Recommendation", "str"),
    ]),
]

STATEMENTS = [  # (json key, markdown title, Ticker attribute, keyword group)
    ("annual_income", "Annual Income Statement", "financials", "income"),
    ("quarterly_income", "Quarterly Income Statement", "quarterly_financials", "income"),
    ("annual_balance", "Annual Balance Sheet", "balance_sheet", "balance"),
    ("quarterly_balance", "Quarterly Balance Sheet", "quarterly_balance_sheet", "balance"),
    ("annual_cashflow", "Annual Cash Flow", "cashflow", "cashflow"),
    ("quarterly_cashflow", "Quarterly Cash Flow", "quarterly_cashflow", "cashflow"),
]

STATEMENT_KEYWORDS = {
    "income": ['Total Revenue', 'Revenues', 'Gross Profit', 'EBIT', 'EBITDA',
               'Net Income', 'Net Income From Continuing Operations',
               'Interest Expense', 'Operating Revenue', 'Cost Of Revenue'],
    "balance": ['Total Assets', 'Total Liabilities', 'Common Stock Equity',
                'Net Debt', 'Total Debt', 'Cash', 'Cash And Cash Equivalents',
                'Working Capital', 'Invested Capital'],
    "cashflow": ['Free Cash Flow', 'Operating Cash Flow', 'Capital Expenditure',
                 'Repurchase Of Capital Stock', 'Repayment Of Debt', 'Issuance Of Debt',
                 'Dividends Paid'],
}


def _has_rows(df):
    return df is not None and len(df) > 0


def _col_name(c):
    return c.strftime("%Y-%m-%d") if hasattr(c, "strftime") else str(c)


# ------------------------------------------------------------ section data
# Each extractor returns plain JSON-safe data; JSON prints it, markdown formats it.

def _estimates(df):
    if not _has_rows(df):
        return []
    return [{"period": str(idx), "avg": _safe(row.get("avg")), "low": _safe(row.get("low")),
             "high": _safe(row.get("high")), "growth": _safe(row.get("growth"))}
            for idx, row in df.iterrows()]


def _earnings_history(t):
    eh = t.earnings_history
    if not _has_rows(eh):
        return []
    out = []
    for idx, row in eh.iterrows():
        surprise = _safe(row.get("surprisePercent"))
        out.append({
            "quarter": str(idx)[:10],
            "eps_actual": _safe(row.get("epsActual")),
            "eps_estimate": _safe(row.get("epsEstimate")),
            "surprise_pct": surprise,
            "beat": bool(surprise and surprise > 0),
        })
    return out


def _calendar(t):
    cal = t.calendar
    if not cal:
        return None
    edate = cal.get("Earnings Date")
    if isinstance(edate, (list, tuple)):
        edate = edate[0] if edate else None
    return {
        "next_earnings": str(edate) if edate else None,
        "eps_avg": _safe(cal.get("Earnings Average")),
        "eps_high": _safe(cal.get("Earnings High")),
        "eps_low": _safe(cal.get("Earnings Low")),
        "revenue_avg": _safe(cal.get("Revenue Average")),
        "ex_dividend": str(cal["Ex-Dividend Date"]) if cal.get("Ex-Dividend Date") else None,
    }


def _insider_transactions(t):
    it = t.insider_transactions
    if not _has_rows(it):
        return []
    return [{
        "insider": str(row.get("Insider", "")),
        "position": str(row.get("Position", "")),
        "transaction": str(row.get("Transaction", "") or row.get("Text", "")),
        "shares": _safe(row.get("Shares")),
        "date": str(row.get("Start Date", ""))[:10],
    } for _, row in it.head(15).iterrows()]


def _labeled_values(df):
    """Two-column Yahoo summary frames (label, value) -> {label: value}."""
    if not _has_rows(df):
        return {}
    try:
        return {str(df.iloc[i, 0]): _safe(df.iloc[i, 1]) for i in range(len(df))}
    except (IndexError, ValueError):
        return {}


def _major_holders(t):
    mh = t.major_holders
    if not _has_rows(mh):
        return {}
    return {str(idx): _safe(row.iloc[0]) for idx, row in mh.iterrows()}


def _holders(df, n, with_position):
    if not _has_rows(df):
        return []
    out = []
    for _, row in df.head(n).iterrows():
        rec = {"holder": str(row.get("Holder", "")), "pct_held": _safe(row.get("pctHeld"))}
        if with_position:
            rec.update(shares=_safe(row.get("Shares")), value=_safe(row.get("Value")),
                       pct_change=_safe(row.get("pctChange")))
        rec["date_reported"] = str(row.get("Date Reported", ""))[:10]
        out.append(rec)
    return out


# ------------------------------------------------------------------ command

def _has_quote(info):
    """Yahoo answers unknown symbols with a near-empty info dict (no quoteType)."""
    return bool(info) and "quoteType" in info


def cmd_ticker(args):
    """Main ticker command."""
    ticker_symbol = args.ticker.upper()
    t = get_ticker(ticker_symbol)
    info = t.info
    if not _has_quote(info):
        fail(f"no Yahoo Finance quote for {ticker_symbol}")
    cur = info.get("currency") or "USD"
    fin_cur = info.get("financialCurrency") or cur
    section = args.section or "overview"

    def want(name):
        return section in (name, "all")

    if getattr(args, "json", False):
        _ticker_json(t, ticker_symbol, info, section, want)
        return

    if want("overview"):
        print(f"\n# {info.get('shortName', ticker_symbol)} ({ticker_symbol})\n")
        print(f"**Sector:** {info.get('sector', 'N/A')} | **Industry:** {info.get('industry', 'N/A')}")
        mcap = f"**Market Cap:** {fmt_num(info.get('marketCap'), cur)}"
        if isinstance(info.get("fullTimeEmployees"), int):
            mcap += f" | **Employees:** {info['fullTimeEmployees']:,}"
        print(mcap)
        if fin_cur != cur:
            print(f"**Currencies:** listing {cur}, financials reported in {fin_cur}")
        print(f"**Website:** {info.get('website', 'N/A')}\n")
        for _key, title, fields in INFO_SECTIONS:
            print_table(["Metric", "Value"],
                        [[label, _fmt(kind, info.get(ik), cur, fin_cur)]
                         for _jk, ik, label, kind in fields],
                        title=title)

    if want("financials"):
        for _key, title, attr, group in STATEMENTS:
            df = getattr(t, attr)
            if _has_rows(df):
                _print_financial_table(df, STATEMENT_KEYWORDS[group], title, fin_cur)

    if want("kpis"):
        rows = [[e["period"], *(fmt_num(e[k], f"{cur}/shares") for k in ("avg", "low", "high")),
                 fmt_pct(e["growth"])] for e in _estimates(t.earnings_estimate)]
        if rows:
            print_table(["Period", "Avg EPS", "Low", "High", "YoY Growth"], rows,
                        title="EPS Estimates")
        rows = [[e["period"], *(fmt_num(e[k], fin_cur) for k in ("avg", "low", "high")),
                 fmt_pct(e["growth"])] for e in _estimates(t.revenue_estimate)]
        if rows:
            print_table(["Period", "Avg Revenue", "Low", "High", "YoY Growth"], rows,
                        title="Revenue Estimates")

    if want("earnings"):
        rows = [[h["quarter"],
                 f"{h['eps_actual']:.2f}" if _is_num(h["eps_actual"]) else "N/A",
                 f"{h['eps_estimate']:.2f}" if _is_num(h["eps_estimate"]) else "N/A",
                 fmt_pct(h["surprise_pct"]), "✓" if h["beat"] else "✗"]
                for h in _earnings_history(t)]
        if rows:
            print_table(["Quarter", "Actual EPS", "Est EPS", "Surprise %", "Beat?"], rows,
                        title="Earnings History & Surprises")
        cal = _calendar(t)
        if cal:
            print_table(["Metric", "Value"], [
                ["Next Earnings", cal["next_earnings"] or "N/A"],
                ["EPS Est (Avg)", fmt_num(cal["eps_avg"], f"{cur}/shares")],
                ["EPS Est (High)", fmt_num(cal["eps_high"], f"{cur}/shares")],
                ["EPS Est (Low)", fmt_num(cal["eps_low"], f"{cur}/shares")],
                ["Rev Est (Avg)", fmt_num(cal["revenue_avg"], fin_cur)],
                ["Ex-Dividend", cal["ex_dividend"] or "N/A"],
            ], title="Upcoming Events")

    if want("insiders"):
        rows = [[tx["insider"][:25], tx["position"][:20], tx["transaction"][:30],
                 fmt_num(tx["shares"], "shares"), fmt_date(tx["date"] or None)]
                for tx in _insider_transactions(t)]
        if rows:
            print_table(["Insider", "Position", "Transaction", "Shares", "Date"], rows,
                        title="Recent Insider Transactions")
        summary = _labeled_values(t.insider_purchases)
        if summary:
            # '% ...' rows are fractions; the rest are share counts
            rows = [[label, fmt_pct(v) if label.startswith("%") else fmt_num(v, "shares")]
                    for label, v in summary.items()]
            print_table(["Metric", "Value"], rows,
                        title="Insider Purchase Summary (Last 6 Months)")
        major = _major_holders(t)
        if major:
            rows = [[label, fmt_pct(v) if "Percent" in label
                     else (f"{int(v):,}" if _is_num(v) else str(v))]
                    for label, v in major.items()]
            print_table(["Metric", "Value"], rows, title="Major Holders Breakdown")

    if want("holdings"):
        rows = [[h["holder"][:35], fmt_pct(h["pct_held"]), fmt_num(h["shares"], "shares"),
                 fmt_num(h["value"], cur), fmt_pct(h["pct_change"]),
                 fmt_date(h["date_reported"] or None)]
                for h in _holders(t.institutional_holders, 15, with_position=True)]
        if rows:
            print_table(["Holder", "% Held", "Shares", "Value", "% Chg", "Reported"], rows,
                        title="Top Institutional Holders")
        rows = [[h["holder"][:35], fmt_pct(h["pct_held"]), fmt_date(h["date_reported"] or None)]
                for h in _holders(t.mutualfund_holders, 10, with_position=False)]
        if rows:
            print_table(["Fund", "% Held", "Reported"], rows, title="Top Mutual Fund Holders")

    if section == "technicals":
        from .technicals import compute_technicals
        compute_technicals(t)


def _ticker_json(t, ticker_symbol, info, section, want):
    """Output ticker data as structured JSON (raw values, documented units)."""
    result = {"ticker": ticker_symbol,
              "currency": info.get("currency"),
              "financial_currency": info.get("financialCurrency"),
              "quote_type": info.get("quoteType")}

    if want("overview"):
        result["overview"] = {
            "name": info.get("shortName", ticker_symbol),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": _safe(info.get("marketCap")),
            "employees": _safe(info.get("fullTimeEmployees")),
            "website": info.get("website"),
        }
        for key, _title, fields in INFO_SECTIONS:
            result.setdefault(key, {}).update(
                {jk: _safe(info.get(ik)) for jk, ik, _label, _kind in fields})

    if want("financials"):
        fin_data = {}
        for key, _title, attr, _group in STATEMENTS:
            df = getattr(t, attr)
            if _has_rows(df):
                cols = df.columns[:4]
                fin_data[key] = {str(idx): {_col_name(c): _safe(df.loc[idx, c]) for c in cols}
                                 for idx in df.index}
        result["financials"] = fin_data

    if want("kpis"):
        kpis = {}
        eps_est = _estimates(t.earnings_estimate)
        if eps_est:
            kpis["eps_estimates"] = eps_est
        rev_est = _estimates(t.revenue_estimate)
        if rev_est:
            kpis["revenue_estimates"] = rev_est
        result["kpis"] = kpis

    if want("earnings"):
        earnings = {}
        history = _earnings_history(t)
        if history:
            earnings["history"] = history
        cal = _calendar(t)
        if cal:
            earnings["calendar"] = cal
        result["earnings"] = earnings

    if want("insiders"):
        insiders = {}
        txns = _insider_transactions(t)
        if txns:
            insiders["transactions"] = txns
        summary = _labeled_values(t.insider_purchases)
        if summary:
            insiders["purchase_summary"] = summary
        major = _major_holders(t)
        if major:
            insiders["major_holders"] = major
        result["insiders"] = insiders

    if want("holdings"):
        holdings = {}
        inst = _holders(t.institutional_holders, 15, with_position=True)
        if inst:
            holdings["institutional"] = inst
        funds = _holders(t.mutualfund_holders, 10, with_position=False)
        if funds:
            holdings["mutual_funds"] = funds
        result["holdings"] = holdings

    if section == "technicals":
        from .technicals import compute_technicals
        tech = compute_technicals(t, json_output=True)
        if tech:
            result["technicals"] = tech

    emit_json(result)


# compare columns: (json key, info key, header, kind)
COMPARE_FIELDS = [
    ("price", "currentPrice", "Price", "cur"),
    ("market_cap", "marketCap", "Mkt Cap", "cur"),
    ("pe_ttm", "trailingPE", "P/E", "x1"),
    ("pe_fwd", "forwardPE", "Fwd P/E", "x1"),
    ("profit_margin", "profitMargins", "Margin", "pct"),
    ("revenue", "totalRevenue", "Revenue", "fin"),
    ("ebitda", "ebitda", "EBITDA", "fin"),
    ("free_cashflow", "freeCashflow", "FCF", "fin"),
    ("num_analysts", "numberOfAnalystOpinions", "# Analysts", "int"),
    ("target_mean", "targetMeanPrice", "Target", "cur"),
]


def cmd_compare(args):
    """Compare key metrics across multiple tickers."""
    tickers = [t.upper() for t in args.tickers]
    records = []
    for i, ticker_symbol in enumerate(tickers):
        try:
            info = yf.Ticker(ticker_symbol).info
            if not _has_quote(info):
                raise LookupError("no Yahoo Finance quote")
            cur = info.get("currency") or "USD"
            records.append({
                "ticker": ticker_symbol,
                "name": info.get("shortName"),
                "currency": cur,
                "financial_currency": info.get("financialCurrency") or cur,
                **{jk: _safe(info.get(ik)) for jk, ik, _h, _k in COMPARE_FIELDS},
            })
        except Exception as e:
            records.append({"ticker": ticker_symbol, "error": str(e)})
        if i < len(tickers) - 1:
            time.sleep(0.5)  # be gentle with Yahoo

    if records and all("error" in r for r in records):
        fail("no data for any ticker: " + "; ".join(f"{r['ticker']}: {r['error']}"
                                                     for r in records))
    if getattr(args, "json", False):
        emit_json(records)
        return

    rows = []
    for r in records:
        if "error" in r:
            rows.append([r["ticker"], "ERROR", r["error"][:30]] + [""] * (len(COMPARE_FIELDS) - 1))
            continue
        rows.append([r["ticker"], (r["name"] or "N/A")[:25]] +
                    [_fmt(kind, r[jk], r["currency"], r["financial_currency"])
                     for jk, _ik, _h, kind in COMPARE_FIELDS])
    print("\n# Multi-Ticker Comparison\n")
    print_table(["Ticker", "Name"] + [h for _jk, _ik, h, _k in COMPARE_FIELDS], rows,
                title="Comparison")
    print("\nPrice/cap/target in listing currency; revenue/EBITDA/FCF in each "
          "company's reporting currency.")


def _print_financial_table(df, keywords, title, currency="USD"):
    """Helper to print a financial DataFrame filtering by keywords."""
    cols = df.columns[:4]
    headers = ["Metric"] + [_col_name(c) for c in cols]
    rows = []
    for idx in df.index:
        if any(imp.lower() in idx.lower() for imp in keywords):
            rows.append([idx] + [fmt_num(df.loc[idx, c], currency) for c in cols])
    if rows:
        print_table(headers, rows, title=f"{title} ({currency})")
