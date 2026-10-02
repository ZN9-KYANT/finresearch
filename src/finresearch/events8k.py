"""finresearch 8k — recent 8-K event feed by item code.

Item codes (Form 8-K): 1.01 material agreement, 1.02 termination, 1.05
cybersecurity incident, 2.02/2.03 financial info & obligations, 3.01
delisting/notice, 4.01 auditor change, 4.02 non-reliance on prior financials
(the classic restatement tell), 5.01 change in control, 5.02 director/officer
changes, 7.01 Reg FD, 8.01 other events. Also surfaces the earnings-release items (2.02) as a proxy for
"company just reported" events.
"""

import re

from .edgar_common import fetch_doc_text, list_filings
from .formatting import print_table
from .output import emit_json
from .sec_edgar import resolve_ciks

ITEM_MEANING = {  # Form 8-K item numbers (SEC General Instructions)
    "101": "material agreement", "102": "agreement terminated",
    "103": "bankruptcy / receivership", "104": "mine safety",
    "105": "material cybersecurity incident",
    "201": "acquisition/disposition completed", "202": "results of operations (earnings)",
    "203": "direct financial obligation", "204": "obligation triggered/accelerated",
    "205": "costs of exit/disposal", "206": "material impairment",
    "301": "delisting / listing notice", "302": "unregistered sales of equity",
    "303": "security holder rights modification",
    "401": "auditor change", "402": "non-reliance on prior financials",
    "501": "change in control", "502": "director/officer change",
    "503": "amend articles/bylaws", "504": "benefit-plan trading blackout",
    "505": "amend code of ethics", "506": "shell company status change",
    "507": "shareholder vote results", "508": "shareholder director nominations",
    "601": "ABS informational material", "701": "Reg FD disclosure",
    "801": "other events", "901": "financial statements & exhibits",
}


def _meaning(item_code):
    """Human meaning for an item code 'X.YY' (8-K items are x.0y-style)."""
    try:
        a, b = item_code.split(".")
        return ITEM_MEANING.get(f"{int(a)}{int(b):02d}", "see filing")
    except ValueError:
        return "see filing"


def extract_items(text):
    """Set of Item codes found in an 8-K body: ('2.02', '9.01')."""
    return sorted(set(re.findall(r"Item\s+(\d\.\d\d)", text)))


def scan_8k(tickers, days=60):
    """8-K rows per ticker. Item codes come from the submissions feed's `items`
    column (no per-filing request); the document is only fetched and grepped
    when that column is empty (very old filings)."""
    out = []
    for ticker, cik10 in resolve_ciks(tickers):
        for f in list_filings(cik10, ["8-K"], days=days):
            items = sorted({i.strip() for i in f["items"].split(",") if i.strip()})
            if not items and f["primary_doc"]:
                text = fetch_doc_text(cik10, f["accession"], prefer_primary=f["primary_doc"])
                if text:
                    items = extract_items(text)
            out.append({
                "ticker": ticker,
                "form": f["form"],
                "filed": f["filing_date"],
                "items": items,
                "summary": f.get("primary_doc") or "-",
                "accession": f["accession"],
            })
    out.sort(key=lambda r: r["filed"], reverse=True)
    return out


def cmd_8k(args):
    """finresearch 8k <TICKERS> [--days 60] [--has 2.02,4.02] — event stream."""
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    want = set(i.strip() for i in (args.has or "").split(",") if i.strip())
    rows = scan_8k(tickers, days=args.days)
    if want:
        rows = [r for r in rows if want & set(r["items"])]
    if args.json:
        emit_json(rows)
        return
    if not rows:
        print("No 8-K filings in the period (or none matching --has filter).")
        return
    headers = ["date", "ticker", "items", "what"]
    table_rows = []
    for r in rows[:60]:
        whats = "; ".join(dict.fromkeys(_meaning(i) for i in r["items"])) or "-"
        table_rows.append([r["filed"], r["ticker"], " ".join(r["items"]) or "-", whats[:60]])
    print_table(headers, table_rows)
    n = sum(1 for r in rows if "2.02" in r["items"])
    print(f"\n{len(rows)} 8-K filings | {n} with earnings item 2.02 | "
          "4.02 non-reliance = classic restatement tell, 4.01 = auditor change")
