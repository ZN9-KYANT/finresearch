"""13f diff — quarter-over-quarter holder changes for one issuer.

'Which institutions ADDED or DROPPED (issuer) last quarter?' Per filer found via
full-text search, the two most recent 13F-HR filings are pulled from that filer's
submissions feed and the issuer's row is compared (shares and value deltas).
"""

from .edgar_common import to_float
from .form13f import load_info_table, recent_13f_filings, who_holds
from .formatting import fmt_num, fmt_shares, print_table


def _issuer_row(cik10, filing, issuer_upper):
    """The issuer's row in one 13F filing (largest row if several), scaled."""
    try:
        loaded = load_info_table(cik10, filing)
    except (ValueError, KeyError):
        return None
    if not loaded:
        return None
    parsed, scale, _why = loaded
    cands = [r for r in parsed["rows"]
             if issuer_upper in (r.get("nameOfIssuer") or "").upper()]
    if not cands:
        return None
    best = max(cands, key=lambda r: to_float(r.get("value")) or 0)
    return {
        "shares": to_float(best.get("shares")),
        "value_usd": (to_float(best.get("value")) or 0) * scale,
        "put_call": best.get("putCall"),
    }


def compute_diff(issuer_words, limit=15, min_shares=None):
    """Rows: [{filer, filer_cik, period_prev, period_now, shares_prev, shares_now,
    delta_shares, value_now_usd, action}] for filers with a prior filing.

    action: ADDED (no prior position), EXITED (now gone), BOUGHT/SELL,
    SAME (within rounding).
    """
    issuer_upper = " ".join(issuer_words).upper()
    filers = who_holds(issuer_upper, limit=limit)["filers"]
    out = []
    for f in filers:
        cik = f["cik"]
        filings = recent_13f_filings(cik, count=2)
        if not filings:
            continue
        now = _issuer_row(cik, filings[0], issuer_upper)
        prev = _issuer_row(cik, filings[1], issuer_upper) if len(filings) > 1 else None
        if now is None and prev is None:
            continue  # FTS hit but row not found (e.g. issuer under a different spelling)
        sh_now = now["shares"] if now else None
        sh_prev = prev["shares"] if prev else None
        if sh_prev is None and sh_now is not None:
            action = "ADDED"
        elif sh_prev is not None and sh_now in (None, 0):
            action = "EXITED"
        else:
            d = (sh_now or 0) - (sh_prev or 0)
            action = "SAME" if abs(d) < 1 else ("BOUGHT" if d > 0 else "SELL")
        if min_shares and (sh_now or 0) < min_shares and (sh_prev or 0) < min_shares:
            continue
        out.append({
            "filer": f["filer"],
            "filer_cik": cik,
            "period_prev": filings[1]["report_date"] if len(filings) > 1 else None,
            "period_now": filings[0]["report_date"],
            "shares_prev": sh_prev,
            "shares_now": sh_now,
            "delta_shares": (sh_now or 0) - (sh_prev or 0) if sh_prev is not None else None,
            "value_now_usd": (now or {}).get("value_usd"),
            "action": action,
        })
    order = {"BOUGHT": 0, "ADDED": 1, "SELL": 2, "EXITED": 3, "SAME": 4}
    out.sort(key=lambda r: (order.get(r["action"], 9), -(r["value_now_usd"] or 0)))
    return out


def print_diff(rows, issuer):
    if not rows:
        print(f"No QoQ compare available for {issuer} "
              "(single filing, or rows not found in the retrieved tables).")
        return
    header = ["filer", "action", "shares prev", "shares now", "delta", "value now"]
    table = []
    for r in rows:
        if r["delta_shares"] is not None:
            delta = fmt_shares(r["delta_shares"])
        else:
            delta = "ADDED" if r["action"] == "ADDED" else "-"
        table.append([
            r["filer"][:42],
            r["action"],
            fmt_shares(r["shares_prev"]) if r["shares_prev"] is not None else "-",
            fmt_shares(r["shares_now"]) if r["shares_now"] is not None else "-",
            delta,
            fmt_num(r["value_now_usd"]) if r["value_now_usd"] else "-",
        ])
    print_table(header, table)
    acts = {}
    for r in rows:
        acts[r["action"]] = acts.get(r["action"], 0) + 1
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(acts.items())) +
          " | QoQ from each filer's two most recent 13F-HR tables (quarter-end marks)")
