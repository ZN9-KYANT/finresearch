"""finresearch buyback — issuer repurchase programs and execution.

Authorization: 8-K announcing a new repurchase program (text grep, best-effort).
Execution: XBRL us-gaap:ShareRepurchase amount history via companyconcept — the
aggregate $ spent per period as reported by the company itself.
"""

import json
import re

from .edgar_common import (
    _get_json,
    fetch_doc_text,
    fetch_file,
    filing_index,
    list_filings,
    strip_tags,
)
from .formatting import fmt_num, print_table
from .sec_edgar import SEC_BASE, resolve_cik


def _announced_programs(text):
    """(title_lines) mentioning repurchase authorization in an 8-K body."""
    t = text.lower()
    if "repurchase" not in t and "buyback" not in t and "buy-back" not in t:
        return []
    titles = []
    for m in re.finditer(
            r"([^\n.]{0,120}(?:repurchase|buy-?back)[^\n.]{0,120})", text, flags=re.I):
        seg = m.group(1).strip()
        if re.search(r"authoriz|approv|program|up to \$|board", seg, re.I):
            titles.append(re.sub(r"\s+", " ", seg)[:160])
    return list(dict.fromkeys(titles))[:3]


def _repurchase_history(cik10, periods=8):
    """(spend_history, authorization, remaining) via XBRL companyconcept.

    Spend = us-gaap:PaymentsForRepurchaseOfCommonStock (cash-flow aggregate).
    Authorization/remaining = StockRepurchaseProgram* tags when the company
    files them (latest value anywhere in the history).
    """
    def concept(tag):
        try:
            return _get_json(f"{SEC_BASE}/api/xbrl/companyconcept/CIK{cik10}/us-gaap/{tag}.json")
        except Exception:
            return None

    spend_rows = None
    d = concept("PaymentsForRepurchaseOfCommonStock")
    if d:
        units = d.get("units", {}).get("USD", [])
        seen = {}
        for e in units:
            key = (e.get("start"), e.get("end"))
            if key not in seen or e.get("filed", "") > seen[key].get("filed", ""):
                seen[key] = e
        rows = sorted(seen.values(), key=lambda e: (e.get("end"), e.get("filed")))
        spend_rows = [{
            "start": (e.get("start") or "")[:10],
            "end": (e.get("end") or "")[:10],
            "amount_usd": e.get("val"),
            "form": e.get("form"),
        } for e in rows[-periods:]]

    def latest_usd(tag):
        # many program tags accumulate over the years; the CURRENT program's
        # value carries the latest period end
        d = concept(tag)
        usd = (d or {}).get("units", {}).get("USD", [])
        return max(usd, key=lambda e: (e.get("end", ""), e.get("filed", ""))).get("val") if usd else None

    auth = latest_usd("StockRepurchaseProgramAuthorizedAmount")
    rem = latest_usd("StockRepurchaseProgramRemainingAuthorizedRepurchaseAmount")
    if spend_rows is None and auth is None:
        return None
    return {"spend": spend_rows or [], "authorized": auth, "remaining": rem}


def scan_buyback(tickers, days=400, exhibit_limit=30):
    """Per issuer: XBRL spend/authorization + press-release (ex-99) language grep."""
    out = []
    for ticker in tickers:
        cik10 = resolve_cik(ticker)
        if not cik10:
            continue
        hist = _repurchase_history(cik10)
        filings = list_filings(cik10, ["8-K"], days=days)[:exhibit_limit]
        hits = []
        for f in filings:
            text = fetch_doc_text(cik10, f["accession"], prefer_primary=f["primary_doc"])
            if not text:
                continue
            # Authorization announcements usually live in the EX-99 press release,
            # not the 8-K body. Grep body first (cheap), then exhibit files.
            for title in _announced_programs(text):
                hits.append({"ticker": ticker, "filed": f["filing_date"],
                             "note": title, "source": "8-K body"})
            try:
                names = filing_index(cik10, f["accession"])
            except Exception:
                continue
            exhibits = [n for n in names
                        if re.search(r"ex.?99|press|release", n, re.I)
                        and n.endswith((".htm", ".html", ".txt"))][:2]
            for name in exhibits:
                try:
                    ex_text = strip_tags(fetch_file(cik10, f["accession"], name))
                except Exception:
                    continue
                for title in _announced_programs(ex_text):
                    hits.append({"ticker": ticker, "filed": f["filing_date"],
                                 "note": title, "source": name[:40]})
        out.append({
            "ticker": ticker,
            "history": hist,
            "announcements": hits[:5],
        })
    return out


def cmd_buyback(args):
    """finresearch buyback <TICKERS> [--days 400] — repurchase programs + spend."""
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    rows = scan_buyback(tickers, days=args.days)
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return
    for r in rows:
        print(f"\n=== {r['ticker']} ===")
        hist = r["history"]
        if hist:
            spend = hist.get("spend") or []
            if spend:
                table = [[h["start"] or "-", h["end"], fmt_num(h["amount_usd"]), h["form"]]
                         for h in spend]
                print_table(["period start", "end", "repurchased (USD)", "form"], table)
                total = sum(h["amount_usd"] or 0 for h in spend)
                print(f"last {len(spend)} periods total: {fmt_num(total)} "
                      "(XBRL PaymentsForRepurchaseOfCommonStock — cash-flow aggregate)")
            auth, rem = hist.get("authorized"), hist.get("remaining")
            if auth or rem:
                bits = []
                if auth:
                    bits.append(f"authorized {fmt_num(auth)}")
                if rem:
                    bits.append(f"remaining {fmt_num(rem)}")
                print("program: " + " | ".join(bits))
        else:
            print("no XBRL repurchase concepts reported")
        if r["announcements"]:
            print(f"{len(r['announcements'])} recent filing(s) with program language:")
            for a in r["announcements"]:
                print(f"  {a['filed']}  [{a['source']}]  {a['note'][:110]}")
        else:
            print("no recent 8-K/exhibit mentions a repurchase authorization "
                  "(text grep is best-effort; filings without exhibits aren't scanned)")
