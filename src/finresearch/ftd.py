"""finresearch ftd — SEC Fails-to-Deliver (FTD) data.

Twice-monthly zips under www.sec.gov/files/data/fails-deliver-data/:
cnsfails{YYYY}{MM}{a|b}.zip — a = settlement dates 1st-15th, b = 16th-end.
Each contains ONE pipe-delimited file: SETTLEMENT DATE|CUSIP|SYMBOL|
QUANTITY (FAILS)|DESCRIPTION|PRICE (price = previous-day close, '.' = none).
These are the GME-era squeeze-screen numbers, straight from the SEC.
"""

import datetime as _dt
import functools
import io
import json
import sys
import urllib.error
import zipfile

from .edgar_common import _get
from .formatting import fmt_num, fmt_shares, print_table

FTD_BASE = "https://www.sec.gov/files/data/fails-deliver-data"

FIELDS = ["settlement_date", "cusip", "symbol", "quantity_fails", "description", "price"]


def parse_ftd_zip(raw_bytes):
    """One FTD zip -> (rows[dict], trailer_dict). Verified layout, 6 pipe fields."""
    z = zipfile.ZipFile(io.BytesIO(raw_bytes))
    txt = z.read(z.namelist()[0]).decode("latin-1")
    rows, trailer = [], {}
    for ln in txt.splitlines():
        if not ln.strip() or ln.startswith("SETTLEMENT DATE|"):
            continue
        if ln.startswith("Trailer"):
            # two trailer lines: 'Trailer record count 50332' and
            # 'Trailer total quantity of shares 1796162548'
            nums = [tok for tok in ln.replace("|", " ").split() if tok.isdigit()]
            low = ln.lower()
            if nums and "record count" in low:
                trailer["record_count"] = nums[-1]
            elif nums and "total quantity" in low:
                trailer["total_quantity"] = nums[-1]
            continue
        bits = ln.split("|")
        if len(bits) != 6:
            continue  # tolerate stray blank-trailing lines
        d, cusip, sym, qty, desc, price = bits
        try:
            qty_n = int(qty)
            price_v = None if price.strip() == "." else float(price)
        except ValueError:
            continue  # malformed row: skip it, the trailer check below reports the gap
        rows.append({
            "settlement_date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
            "cusip": cusip,
            "symbol": sym.strip(),
            "quantity_fails": qty_n,
            "description": desc.strip(),
            "price": price_v,
        })
    expected = trailer.get("record_count")
    if expected is not None and int(expected) != len(rows):
        print(f"WARNING: FTD file trailer says {expected} records, parsed {len(rows)}",
              file=sys.stderr)
    return rows, trailer


@functools.lru_cache(maxsize=8)
def _download(yyyy, mm, half):
    """One FTD zip's bytes (cached: the discovery probe IS the download)."""
    return _get(f"{FTD_BASE}/cnsfails{yyyy}{mm:02d}{half}.zip", timeout=60)


def latest_ftd_files(count=1, back_months=8):
    """Discover the newest FTD zips available: [(yyyy, mm, half)], oldest first."""
    today = _dt.date.today()
    found = []
    y, m = today.year, today.month
    for _ in range(back_months + 1):
        for half in ("b", "a"):
            try:
                _download(y, m, half)
            except (urllib.error.URLError, OSError):
                continue  # not published yet (404) or unreachable
            found.append((y, m, half))
            if len(found) >= count:
                return list(reversed(found))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return list(reversed(found))


def fetch_ftd(yyyy, mm, half):
    return parse_ftd_zip(_download(yyyy, mm, half))


def aggregate_top(rows, top=15, by="value", min_quantity=None):
    """Aggregate per symbol across a file (rows repeat per settlement date).

    by='value' -> max(quantity x price); by='quantity' -> max(quantity).
    Using max (not sum): the balance is outstanding per date; max = latest peak.
    """
    per = {}
    for r in rows:
        if min_quantity and r["quantity_fails"] < min_quantity:
            continue
        sym = r["symbol"]
        val = r["quantity_fails"] * (r["price"] or 0)
        cur = per.get(sym)
        cand = {
            "symbol": sym,
            "description": r["description"],
            "peak_date": r["settlement_date"],
            "peak_quantity": r["quantity_fails"],
            "peak_value_usd": val,
            "price": r["price"],
        }
        if cur is None:
            per[sym] = cand
        else:
            keep_val = val if by == "value" else r["quantity_fails"]
            cur_val = cur["peak_value_usd"] if by == "value" else cur["peak_quantity"]
            if keep_val > cur_val:
                per[sym] = cand
    out = sorted(per.values(),
                 key=lambda x: x["peak_value_usd"] if by == "value" else x["peak_quantity"],
                 reverse=True)
    return out[:top]


def symbol_history(symbol, files=3):
    """Fails history for one symbol over the last `files` FTD files."""
    hist = []
    for (y, m, half) in latest_ftd_files(count=files):
        rows, _ = fetch_ftd(y, m, half)
        for r in rows:
            if r["symbol"].upper() == symbol.upper():
                hist.append(r)
    hist.sort(key=lambda r: r["settlement_date"], reverse=True)
    return hist


def cmd_ftd(args):
    """finresearch ftd top|sym — aggregate fails or one symbol's history."""
    sub = getattr(args, "ftd_cmd", None)
    if sub == "sym":
        hist = symbol_history(args.symbol, files=args.files)
        if args.json:
            print(json.dumps(hist, indent=2, default=str))
            return
        if not hist:
            print(f"No FTD rows for {args.symbol} in the latest {args.files} files.")
            return
        table = [[r["settlement_date"], fmt_shares(r["quantity_fails"]),
                  fmt_num(r["price"]) if r["price"] else "-",
                  fmt_num(r["quantity_fails"] * (r["price"] or 0))]
                 for r in hist]
        print_table(["settlement date", "fails (shares)", "prev close", "fails $"], table)
        print("\nSEC Fails-to-Deliver — outstanding fails per settlement date "
              "(twice-monthly publication).")
        return

    # default: top across the latest file
    files = latest_ftd_files(count=1)
    if not files:
        print("Could not reach any recent FTD file (sec.gov unreachable?).")
        return
    y, m, half = files[0]
    rows, trailer = fetch_ftd(y, m, half)
    if args.json:
        top = aggregate_top(rows, top=args.top, by=args.by, min_quantity=args.min_quantity)
        print(json.dumps({"file": f"{y}{m:02d}{half}", "rows": len(rows), "top": top},
                          indent=2, default=str))
        return
    top = aggregate_top(rows, top=args.top, by=args.by, min_quantity=args.min_quantity)
    print(f"=== SEC Fails-to-Deliver — file {y}-{m:02d}{half} "
          f"({len(rows)} rows{' | trailer ' + str(trailer.get('record_count')) if trailer else ''}) ===")
    hdr = ["symbol", "description", "peak date", "fails (sh)", "prev close", "fails $"]
    table = [[r["symbol"], r["description"][:28], r["peak_date"],
              fmt_shares(r["peak_quantity"]),
              fmt_num(r["price"]) if r["price"] else "-",
              fmt_num(r["peak_value_usd"])] for r in top]
    print_table(hdr, table)
    print("\nRank by fails $ (shares x prev close), peak settlement date in the file. "
          "Persistently high names are the classic squeeze-screen inputs.")
