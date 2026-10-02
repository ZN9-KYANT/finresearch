"""finresearch dilution — S-3 shelf registrations, 424B offerings, ATM programs.

The bearish mirror of insider buying: the machinery of new share issuance.
S-3/S-3ASR = shelf (may never price); 424B2/424B5 = priced offerings; "at-the-market"
phrasing = ATM equity program. Extracts share counts / dollar sizes heuristically
from the prospectus text (numbers are as-filed, best-effort).
"""

import json
import re

from .edgar_common import fetch_doc_text, list_filings
from .formatting import print_table
from .sec_edgar import resolve_cik


def _first_number(text, patterns):
    """First match of any pattern; returns the matched fragment trimmed."""
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            frag = m.group(0)
            return re.sub(r"\s+", " ", frag).strip()
    return None


def _offering_hints(text):
    """(shares_hint, size_hint, atm_flag) from prospectus text."""
    shares = _first_number(text, [
        r"[\d,]{3,}(?:\.\d+)?\s+shares\s+of\s+(?:its\s+)?common stock",
        r"up\s+to\s+[\d,]{3,}\s+shares",
        r"[\d,]{3,}(?:\.\d+)?\s+shares",
    ])
    size = _first_number(text, [
        r"\$\s?[\d,]{6,}(?:\.\d+)?",
        r"aggregate\s+(?:offering\s+)?(?:purchase\s+)?price[^.]{0,40}\$[\d,]+",
    ])
    atm = "at-the-market" in text.lower() or "at the market offering" in text.lower()
    return shares, size, atm


def scan_dilution(tickers, days=365):
    out = []
    for ticker in tickers:
        cik10 = resolve_cik(ticker)
        if not cik10:
            continue
        filings = list_filings(cik10, [], regex=r"^(S-3\b|S-3ASR|424B)", days=days)
        for f in filings:
            shares = size = None
            atm = False
            if f["primary_doc"]:
                text = fetch_doc_text(cik10, f["accession"], prefer_primary=f["primary_doc"])
                if text:
                    shares, size, atm = _offering_hints(text[:160_000])
            out.append({
                "ticker": ticker,
                "form": f["form"],
                "filed": f["filing_date"],
                "shares_hint": shares or "-",
                "size_hint": size or "-",
                "atm": atm,
                "accession": f["accession"],
            })
    out.sort(key=lambda r: r["filed"], reverse=True)
    return out


def cmd_dilution(args):
    """finresearch dilution <TICKERS> [--days 365] — shelf/priced offering pipeline."""
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    rows = scan_dilution(tickers, days=args.days)
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return
    if not rows:
        print("No S-3/424B filings in the period.")
        return
    headers = ["ticker", "form", "filed", "shares", "size", "atm"]
    table_rows = [[r["ticker"], r["form"], r["filed"],
                   (r["shares_hint"] or "-")[:44],
                   (r["size_hint"] or "-")[:26],
                   "yes" if r["atm"] else ""] for r in rows]
    print_table(headers, table_rows)
    print("\nS-3 = shelf (may never price) | 424B* = priced offering | "
          "atm = at-the-market program | hints parsed from prospectus text")
