"""Institutional holdings — SEC EDGAR Form 13F-HR (native, no third-party API).

A 13F-HR is filed quarterly (~45 days after quarter end) by institutional investment
managers with >= $100M in 13(f) securities. Each filing has an information table
(one <infoTable> row per position: issuer, CUSIP, value, shares, optional put/call).

Known data traps handled here:
  * The <value> unit changed: filings made on/after 2023-01-03 report whole
    DOLLARS, earlier ones THOUSANDS — and some filers ignore the rule. The scale
    is decided per filing by comparing the biggest common-stock row's implied
    per-share price with the real price (yfinance); when no price is available
    the filing date decides. Never assume.
  * <value> for 13F filings is reported as of the END OF QUARTER (period_ending).

Commands:
  finresearch 13f holder BRK-B  — a filer's holdings (ticker via company_tickers, or CIK)
  finresearch 13f who NVIDIA CORP — which 13F filers hold an issuer (EDGAR full-text search)
  finresearch 13f diff NVIDIA CORP — quarter-over-quarter adds/drops (form13f_diff.py)
"""

import functools
import json
import math
import urllib.parse
import xml.etree.ElementTree as ET

from .edgar_common import (
    _get_json,
    child_text,
    fetch_file,
    filing_index,
    find_all,
    first,
    list_filings,
    to_float,
)
from .formatting import fmt_num, fmt_shares, print_table

EFTS = "https://efts.sec.gov/LATEST/search-index"

# SEC's 2022 Form 13F amendments: filings made on/after this date report
# <value> rounded to the nearest dollar; earlier filings reported thousands.
WHOLE_DOLLAR_SINCE = "2023-01-03"

_13F_HR = r"^13F-HR(/A)?$"  # holdings reports (13F-NT notices carry no table)


# ------------------------------------------------------------------ XML parse

def parse_13f_information_table(content):
    """Parse a 13F information-table XML into row dicts. Namespace-agnostic."""
    root = ET.fromstring(content)
    rows = []
    for info in find_all(root, "infoTable"):
        shrs = first(info, "shrsOrPrnAmt")
        rows.append({
            "nameOfIssuer": child_text(info, "nameOfIssuer"),
            "cusip": child_text(info, "cusip"),
            "value": child_text(info, "value"),
            "type": child_text(shrs, "sshPrnamtType"),
            "shares": child_text(shrs, "sshPrnamt"),
            "putCall": child_text(info, "putCall"),
            "investmentDiscretion": child_text(info, "investmentDiscretion"),
            "votingAuthoritySole": child_text(info, "votingAuthority", "Sole"),
            "otherManager": child_text(info, "otherManager"),
        })
    # filing-level metadata lives in the document header (derivative of primary doc)
    hdr = first(root, "period")
    return {"period": hdr.text if hdr is not None else None, "rows": rows}


@functools.lru_cache(maxsize=512)
def _yf_price(ticker):
    """Last price via yfinance (cached per run). ImportError propagates."""
    import yfinance as yf
    try:
        tk = yf.Ticker(ticker)
        return tk.fast_info.get("lastPrice") or tk.info.get("regularMarketPrice")
    except Exception:
        return None


def detect_value_scale(rows, price_lookup=None, filed=None):
    """Return (scale, reason): 1 if <value> is whole dollars, 1000 if thousands.

    The biggest common-stock row (SH, no put/call) is priced: value / shares is
    the implied per-share price under each reading, and the reading closest to
    the real price wins. Without a usable price, the filing date decides
    (WHOLE_DOLLAR_SINCE; an unknown date means a current filing -> dollars).

    price_lookup(ticker) -> float | None may be injected for tests.
    """
    lookup = price_lookup or _yf_price
    by_date = 1 if (filed or WHOLE_DOLLAR_SINCE) >= WHOLE_DOLLAR_SINCE else 1000
    fallback = "dollars" if by_date == 1 else "thousands"

    def default(why):
        return by_date, f"{fallback} by filing date ({why})"

    priceable = [r for r in rows
                 if (r.get("type") or "SH") == "SH" and not r.get("putCall")
                 and to_float(r.get("value")) and to_float(r.get("shares"))]
    if not priceable:
        return default("no priceable row")
    row = max(priceable, key=lambda r: to_float(r.get("value")))
    shares, value = to_float(row["shares"]), to_float(row["value"])
    ticker = _name_to_ticker((row.get("nameOfIssuer") or "").strip())
    if not ticker:
        return default("no ticker match")
    try:
        price = lookup(ticker)
    except ImportError:
        return default("yfinance unavailable")
    except Exception:
        price = None
    if not price or price <= 0:
        return default("price unavailable")

    implied = {1: value / shares, 1000: value * 1000 / shares}
    best = min(implied, key=lambda k: abs(math.log(implied[k] / price)))
    if abs(math.log(implied[best] / price)) > math.log(10):
        return default(f"price check inconclusive for {ticker}")
    label = "raw dollars" if best == 1 else "thousands"
    return best, f"{label} (implied ${implied[best]:,.2f} vs ${price:,.2f} for {ticker})"


_SUFFIX = frozenset({"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY",
                     "LTD", "LIMITED", "PLC", "SA", "NV", "THE"})


def _norm_name(s):
    toks = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in (s or "").upper()).split()
    return frozenset(t for t in toks if t not in _SUFFIX)


@functools.lru_cache(maxsize=1)
def _title_index():
    """Normalized company title -> ticker (first listing wins), built once."""
    from .sec_edgar import company_tickers
    idx = {}
    for v in company_tickers():
        idx.setdefault(_norm_name(v.get("title")), v["ticker"])
    return idx


def _name_to_ticker(name):
    """Rough issuer-name -> ticker via the shared company_tickers cache.

    Compares normalized token sets, dropping generic corporate suffixes,
    so 'ALLY FINL INC' matches 'ALLY FINANCIAL INC.'-style titles.
    """
    try:
        return _title_index().get(_norm_name(name))
    except Exception:
        return None


# ------------------------------------------------------------------ filer side

def info_table_name(cik10, accession):
    """The information-table XML in a 13F filing directory (or None)."""
    xmls = [n for n in filing_index(cik10, accession) if n.endswith(".xml") and "/" not in n]
    # the primary_doc.xml is the cover page; the info table is the other XML
    # (some filers embed the table in the primary doc only: fall back to it)
    return next((n for n in xmls if "primary_doc" not in n), xmls[0] if xmls else None)


def recent_13f_filings(cik10, count=1):
    """Last N 13F-HR(/A) filings for a filer CIK, newest first."""
    return list_filings(cik10, [], days=None, regex=_13F_HR)[:count]


def load_info_table(cik10, filing):
    """(parsed rows, scale, reason) for one 13F filing, or None."""
    name = info_table_name(cik10, filing["accession"])
    if not name:
        return None
    parsed = parse_13f_information_table(fetch_file(cik10, filing["accession"], name))
    scale, why = detect_value_scale(parsed["rows"], filed=filing["filing_date"])
    return parsed, scale, why


def fetch_holder_holdings(cik10):
    """Fetch + parse the latest 13F for a filer CIK.

    Returns dict with filer metadata, period, rows scaled to RAW DOLLARS,
    value_usd and value_scale metadata.
    """
    filings = recent_13f_filings(cik10, count=1)
    if not filings:
        return None
    fil = filings[0]
    loaded = load_info_table(cik10, fil)
    if not loaded:
        return None
    parsed, scale, why = loaded
    rows = []
    for r in parsed["rows"]:
        v = to_float(r.get("value"))
        rows.append({
            "issuer": r.get("nameOfIssuer"),
            "cusip": r.get("cusip"),
            "type": r.get("type"),
            "shares": to_float(r.get("shares")),
            "putCall": r.get("putCall"),
            "value_usd": (v * scale) if v is not None else None,
        })
    rows.sort(key=lambda x: (x["value_usd"] or 0), reverse=True)
    return {
        "accession": fil["accession"],
        "filed": fil["filing_date"],
        "period": fil["report_date"] or parsed.get("period"),
        "value_scale": {"factor": scale, "reason": why},
        "rows": rows,
    }


# ------------------------------------------------------------------ who-holds

def who_holds(issuer_name, limit=25, since=None):
    """Which 13F filers hold a named issuer (e.g. 'NVIDIA CORP')?

    Uses EDGAR full-text search restricted to 13F-HR. Returns hit metadata per
    filer: CIK, display name, accession, file_date, period_ending, file handle.
    Deduplicated by (cik) keeping the most recent filing.
    """
    params = {"q": f'"{issuer_name}"', "forms": "13F-HR"}
    if since:
        params["dateRange"] = "custom"
        params["startdt"] = since
    data = _get_json(EFTS + "?" + urllib.parse.urlencode(params))
    hits = data.get("hits", {}).get("hits", [])
    per_filer = {}
    for h in hits:
        src = h.get("_source", {})
        for cik in src.get("ciks") or []:
            rec = {
                "cik": cik,
                "filer": (src.get("display_names") or ["?"])[0],
                "accession": (h.get("_id", "").split(":")[0] or src.get("adsh", "")),
                "file": h.get("_id"),
                "file_date": src.get("file_date"),
                "period_ending": src.get("period_ending"),
            }
            cur = per_filer.get(cik)
            if cur is None or (rec["file_date"] or "") > (cur["file_date"] or ""):
                per_filer[cik] = rec
    out = sorted(per_filer.values(), key=lambda r: (r["file_date"] or ""), reverse=True)
    return {"total_raw_hits": data.get("hits", {}).get("total"), "filers": out[:limit]}


# ------------------------------------------------------------------ commands

def _resolve_holder(name):
    """'BRK-B' (ticker) or '0001067983' (CIK) -> cik10 + display name."""
    from .sec_edgar import find_cik
    if name.isdigit():
        return name.zfill(10), f"CIK {name}"
    return find_cik(name)


def cmd_13f(args):
    sub = getattr(args, "subcommand", None)
    if sub == "diff":
        from .form13f_diff import compute_diff, print_diff
        words = list(args.issuer_words)
        rows = compute_diff(words, limit=args.limit, min_shares=args.min_shares)
        print(f"=== 13F quarter-over-quarter changes for \"{' '.join(words)}\" ===")
        print_diff(rows, " ".join(words))
        return
    if sub == "who":
        name = " ".join(args.issuer_words).upper()
        res = who_holds(name, limit=args.limit)
        print(f"=== 13F filers holding \"{name}\" (full-text search) ===")
        print(f"raw hits: {res['total_raw_hits']}")
        if not res["filers"]:
            print("No filers found. 13F tables lag ~45 days after quarter end.")
            return
        header = ["filer", "cik", "file_date", "period_end"]
        rows = [[f["filer"].split("  (CIK")[0][:42], f["cik"], f["file_date"], f["period_ending"]]
                for f in res["filers"]]
        print_table(header, rows)
        print("\nSource: efts.sec.gov full-text search over 13F-HR information tables.")
        return

    if sub == "holder":
        cik, title = _resolve_holder(args.holder)
        if not cik:
            print(f"Unknown holder: {args.holder} (pass a ticker or 10-digit CIK)")
            return
        print(f"Fetching latest 13F-HR for {title} ({cik}) ...")
        data = fetch_holder_holdings(cik)
        if not data:
            print("No holdings table found in the latest filing.")
            return
        if args.json:
            print(json.dumps(data, indent=2, default=str))
            return
        vs = data["value_scale"]
        print(f"filed {data['filed']} | period {data['period']} "
              f"| value units: {vs['reason']}")
        top = data["rows"][:args.top]
        header = ["issuer", "cusip", "shares", "value_usd", "P/C"]
        rows = [[
            (r["issuer"] or "")[:36],
            r["cusip"] or "-",
            fmt_shares(r["shares"]),
            fmt_num(r["value_usd"]) if r["value_usd"] else "-",
            r["putCall"] or "-",
        ] for r in top]
        print_table(header, rows)
        total = sum(r["value_usd"] or 0 for r in data["rows"])
        print(f"\n{len(data['rows'])} positions | total reported value: {fmt_num(total)} "
              f"(13F values are quarter-end marks; put/call rows offset)")
        print("Source: SEC EDGAR 13F-HR information table (data.sec.gov).")
        return

    # bare `finresearch 13f` is handled by cli.py (prints subcommand help)
