"""finresearch activist — SC 13D/G ownership stakes on a ticker's registrant.

13D = 5%+ holder INTENDING influence; 13G = passive. Amendments (13D/A) carry the
real-time moves (buys/sells by the holder, purpose changes). The issuer's own
submissions feed lists both sides: form "SC 13D*" rows are OWNERSHIP filings
*about this issuer* filed by its 5% holders (with older ones in the submissions
'files' backfill — the module reports the API window it can see and says so).
"""

import json
import re

from .edgar_common import fetch_doc_text, list_filings
from .formatting import print_table
from .sec_edgar import resolve_cik

SUBJECT_HINTS = ("SUBJECT COMPANY", "NAME OF ISSUER")


def _conformed_name_after(text, marker):
    """'FILED BY:' / 'SUBJECT COMPANY:' blocks are followed by a COMPANY DATA
    block with 'COMPANY CONFORMED NAME: <name>' (EDGAR submission-header docs)."""
    i = text.upper().find(marker)
    if i < 0:
        return None
    m = re.search(r"COMPANY CONFORMED NAME:\s*([^\n]+)", text[i:i + 800],
                  flags=re.IGNORECASE)
    return m.group(1).strip() if m else None


def _extract_filed_by(text):
    """Filer (activist) name from the submission header."""
    name = _conformed_name_after(text, "FILED BY")
    return name[:80] if name else None


def _extract_subject(text):
    """Subject issuer name from the submission header."""
    name = _conformed_name_after(text, "SUBJECT COMPANY")
    return name[:120] if name else None


def activation_flag(text):
    """13D original: the famous activist trigger phrase (Rule 13d-1(k) vs intent).

    Returns 'activist' when the calc-of-schedule language intends influence,
    else 'passive' (13G or no-intent 13D)."""
    t = text[:20000].upper()
    if "CHECK THIS BOX IF" in t and "13G" in t:
        return "passive"
    phrases = ("INTEND TO INFLUENCE", "SEEK TO INFLUENCE", "FACILITATE AN ACQUISITION")
    # 13G/A amendments that converted to 13D also carry the phrase
    return "activist" if any(p in t for p in phrases) else "passive"


def scan_activist(tickers, days=400):
    """Rows: [{ticker, form, filed, filer, flag, accession}] newest first."""
    out = []
    for ticker in tickers:
        cik10 = resolve_cik(ticker)
        if not cik10:
            continue
        # form names vary by era: 'SC 13D/A' vs 'SCHEDULE 13D/A'
        filings = list_filings(cik10, [], regex=r"13[DG]", days=days)
        for f in filings:
            filer = None
            text = None
            if f["primary_doc"] and not f["primary_doc"].endswith(".txt"):
                text = fetch_doc_text(cik10, f["accession"], prefer_primary=f["primary_doc"])
                if text:
                    filer = _extract_filed_by(text)
            out.append({
                "ticker": ticker,
                "form": f["form"],
                "filed": f["filing_date"],
                "filer": filer or "-",
                "flag": activation_flag(text) if text else "unparsed",
                "accession": f["accession"],
            })
    out.sort(key=lambda r: r["filed"], reverse=True)
    return out


def cmd_activist(args):
    """finresearch activist <TICKER> [--days 400] — SC 13D/G stakes on an issuer."""
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    rows = scan_activist(tickers, days=args.days)
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return
    if not rows:
        print("No SC 13D/G filings in the period.")
        return
    headers = ["ticker", "form", "filed", "filer", "read", "flag"]
    table_rows = [[r["ticker"], r["form"], r["filed"], r["filer"],
                   r["accession"][:12] + "...", r["flag"]] for r in rows]
    print_table(headers, table_rows)
    print(f"\n{len(rows)} 13D/G filings | read = doc opened, unparsed = listed w/o doc")
