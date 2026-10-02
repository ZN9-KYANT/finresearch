"""finresearch short — FINRA Consolidated Short Interest.

Keyless GET (historical slice) + optional keyed POST when FINRA_API_KEY is set:
  GET https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest
      -> CSV, default limit 1000, keyless slice is frozen to an old settlement date
  POST same URL, JSON body with compareFilters + limit + sortBy
      -> current data (requires free FINRA API key; FINRA_API_KEY env)
Dataset: biweekly settlement dates, all exchanges + OTC, 14 fields. Gotchas:
issueName may contain UNQUOTED commas -> right-anchor the last 11 fields;
daysToCoverQuantity 999.99 is a sentinel (ADV missing), 1.00 floor for <1.
"""

import json
import os
import sys
import urllib.request

from .config import DEFAULT_USER_AGENT as UA
from .formatting import fmt_shares, print_table

API = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"

# 14 columns; the FIRST 3 vary (year-month, symbol, name-with-commas)
_TAIL_FIELDS = [
    "exchange", "market_class", "current_short", "previous_short",
    "split_flag", "adv", "dtc", "revision", "change_pct", "change_num",
    "settlement_date",
]
HEADER_FIELDS = ["year_month", "symbol", "issue_name"] + _TAIL_FIELDS


def _parse_line(ln):
    """Right-anchored CSV row. issueName may contain UNQUOTED commas, so the
    name is everything in the middle: field 0 = year-month, 1 = symbol, the
    LAST 11 fields are fixed. Never naive-split into a fixed 14."""
    bits = ln.split(",")
    if len(bits) < 14:
        return None
    row = {"year_month": bits[0], "symbol": bits[1],
           "issue_name": ",".join(bits[2:-11]).strip()}
    for name, val in zip(_TAIL_FIELDS, bits[-11:]):
        row[name] = val
    return row


def _normalize(row):
    def _int(k):
        v = (row.get(k) or "").strip()
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None

    def _float(k):
        v = (row.get(k) or "").strip()
        try:
            return float(v)
        except (ValueError, TypeError):
            return None
    dtc = _float("dtc")
    return {
        "symbol": (row.get("symbol") or "").strip(),
        "name": (row.get("issue_name") or "").strip(),
        "settlement_date": (row.get("settlement_date") or "").strip(),
        "short_interest": _int("current_short"),
        "prev_short_interest": _int("previous_short"),
        "adv": _int("adv"),
        "days_to_cover": None if dtc == 999.99 else dtc,
        "change_pct": _float("change_pct"),
    }


def _key():
    return os.getenv("FINRA_API_KEY")


def fetch_recent(limit=50, settlement_date=None, symbols=None):
    """Current rows via keyed POST; raises if no API key is set."""
    if not _key():
        raise RuntimeError(
            "FINRA current data needs a free API key: export FINRA_API_KEY "
            "(https://finra.org/finra-data). Keyless slice is historical-only.")
    body = {"limit": limit, "compareFilters": [
        {"fieldName": "settlementDate", "fieldValue": settlement_date,
         "compareType": "EQUAL"}] if settlement_date else
        [{"fieldName": "settlementDate", "fieldValue": "latest", "compareType": "EQUAL"}]}
    if symbols:
        body["compareFilters"].append(
            {"fieldName": "symbolCode", "fieldValue": symbols, "compareType": "IN"})
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/csv",
                 "User-Agent": UA, "X-API-Key": _key()})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", "ignore")
    rows = [r for r in (_parse_line(ln) for ln in text.splitlines()[1:]) if r]
    return [_normalize(r) for r in rows]


def fetch_free_slice(limit=1000):
    """The keyless GET slice (frozen historical date) — useful for format/dev."""
    req = urllib.request.Request(API, headers={"Accept": "*/*", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", "ignore")
    rows = [r for r in (_parse_line(ln) for ln in text.splitlines()[1:]) if r]
    return [_normalize(r) for r in rows[:limit]]


def rank(rows, top=15, by="dtc", min_si=None):
    pool = [r for r in rows if r["days_to_cover"] is not None] if by == "dtc" else rows
    if min_si:
        pool = [r for r in pool if (r["short_interest"] or 0) >= min_si]
    key = (lambda r: r["days_to_cover"]) if by == "dtc" else (lambda r: r["short_interest"] or 0)
    return sorted(pool, key=key, reverse=True)[:top]


def cmd_short(args):
    """finresearch short top — short-interest ranking (keyed current / keyless slice)."""
    rows = None
    note = ""
    if args.settlement and not _key():
        print("--settlement needs FINRA_API_KEY (the keyless slice has one frozen date); "
              "showing the keyless slice instead.", file=sys.stderr)
    if _key() and (args.settlement or not args.free):
        try:
            rows = fetch_recent(limit=args.limit, settlement_date=args.settlement)
            note = "current data via FINRA keyed API"
        except Exception as e:
            print(f"Keyed fetch failed ({e}); falling back to the keyless slice.",
                  file=sys.stderr)
            rows = None
    if rows is None:
        rows = fetch_free_slice(limit=args.limit)
        note = ("FREE HISTORICAL SLICE (keyless API is frozen at one old settlement "
                "date). Set FINRA_API_KEY for current biweekly data.")
    top = rank(rows, top=args.top, by=args.by, min_si=args.min_si)
    if args.json:
        print(json.dumps({"mode": note, "rows": top}, indent=2, default=str))
        return
    if not top:
        print("No rows (dataset slice empty — keyed API may need a settlement date).")
        return
    print(f"=== FINRA short interest — {'top by ' + ('days-to-cover' if args.by == 'dtc' else 'short interest')} ===")
    table = [[r["symbol"], r["name"][:34], r["settlement_date"],
              fmt_shares(r["short_interest"]),
              f"{r['days_to_cover']:.2f}" if r["days_to_cover"] is not None else "-",
              f"{r['change_pct']:+.1f}%" if r["change_pct"] is not None else "-"]
             for r in top]
    print_table(["symbol", "name", "settlement", "short int", "dtc", "chg"], table)
    print("\n" + note)
    print("dtc = short interest / avg daily volume (in-file field; 999.99 sentinel filtered).")
