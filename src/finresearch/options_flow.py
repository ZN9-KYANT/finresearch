"""finresearch options — unusual options activity via yfinance chains.

Per ticker: current chain snapshot → aggregate call/put volume vs open interest,
a simple volume/OI ratio flag (v/OI > threshold on a strike = fresh positioning),
put/call ratio, and a put-minus-call IV skew proxy per expiry. Free + keyless (yfinance). Chain rules
of thumb (not financial advice encoded as truth): high volume-on-low-OI = new
positions; high OI on low puts = potential dealer hedging pressure.
"""

import json

import yfinance as yf

from .formatting import fmt_shares, print_table
from .output import emit_json


def _safe(v):
    try:
        f = float(v)
        return f if f == f else None  # NaN guard
    except (TypeError, ValueError):
        return None


def chains_snapshot(ticker, max_expiry=2):
    """Aggregates across the front N expiries."""
    tk = yf.Ticker(ticker)
    expiries = tk.options[:max_expiry]
    if not expiries:
        return None
    out = {"ticker": ticker, "expiries": list(expiries), "rows": []}
    for exp in expiries:
        ch = tk.option_chain(exp)
        for side, df in (("call", ch.calls), ("put", ch.puts)):
            for _, r in df.iterrows():
                row = {
                    "expiry": exp, "side": side,
                    "strike": _safe(r.get("strike")),
                    "last": _safe(r.get("lastPrice")),
                    "bid": _safe(r.get("bid")), "ask": _safe(r.get("ask")),
                    "iv": _safe(r.get("impliedVolatility")),
                    "volume": _safe(r.get("volume")) or 0,
                    "oi": _safe(r.get("openInterest")) or 0,
                }
                row["vol_oi"] = (row["volume"] / row["oi"]) if row["oi"] else None
                out["rows"].append(row)
    return out


def unusual_activity(snap, vol_oi_min=1.0, min_volume=100, top=12):
    """Strikes with volume >= vol_oi_min x open interest and real volume."""
    pool = [r for r in snap["rows"]
            if r["vol_oi"] is not None and r["vol_oi"] >= vol_oi_min
            and r["volume"] >= min_volume]
    pool.sort(key=lambda r: -r["vol_oi"])
    return pool[:top]


def totals(snap):
    """Per-expiry put/call volume + OI ratios and an IV skew proxy
    (average put IV minus average call IV across the listed strikes)."""
    per = {}
    for r in snap["rows"]:
        e = per.setdefault(r["expiry"], {"cv": 0, "pv": 0, "coi": 0, "poi": 0,
                                         "civ": [], "piv": []})
        if r["side"] == "call":
            e["cv"] += r["volume"]
            e["coi"] += r["oi"]
            if r["iv"]:
                e["civ"].append(r["iv"])
        else:
            e["pv"] += r["volume"]
            e["poi"] += r["oi"]
            if r["iv"]:
                e["piv"].append(r["iv"])
    def _avg(xs):
        return sum(xs) / len(xs) if xs else None

    out = []
    for exp, e in per.items():
        iv_call, iv_put = _avg(e["civ"]), _avg(e["piv"])
        out.append({
            "expiry": exp,
            "call_vol": e["cv"], "put_vol": e["pv"],
            "pc_vol_ratio": (e["pv"] / e["cv"]) if e["cv"] else None,
            "call_oi": e["coi"], "put_oi": e["poi"],
            "pc_oi_ratio": (e["poi"] / e["coi"]) if e["coi"] else None,
            "iv_call_avg": iv_call, "iv_put_avg": iv_put,
            "iv_skew": (iv_put - iv_call) if iv_put is not None and iv_call is not None else None,
        })
    return out


def cmd_options(args):
    """finresearch options <TICKER> [--vol-oi 1.0] — unusual activity + ratios."""
    snap = chains_snapshot(args.ticker, max_expiry=args.expiries)
    if not snap or not snap["rows"]:
        if args.json:
            emit_json({"ticker": args.ticker, "expiries": [], "totals": [], "unusual": []})
        else:
            print(f"No option chains available for {args.ticker} (not an optionable listing?).")
        return
    if args.json:
        print(json.dumps({
            "ticker": args.ticker,
            "expiries": snap["expiries"],
            "totals": totals(snap),
            "unusual": unusual_activity(snap, vol_oi_min=args.vol_oi,
                                        min_volume=args.min_volume, top=args.top),
        }, indent=2, default=str))
        return
    tot = totals(snap)
    rows = [[t["expiry"], fmt_shares(t["call_vol"]), fmt_shares(t["put_vol"]),
             f"{t['pc_vol_ratio']:.2f}" if t["pc_vol_ratio"] else "-",
             f"{t['iv_call_avg'] * 100:.0f}%" if t["iv_call_avg"] else "-",
             f"{t['iv_put_avg'] * 100:.0f}%" if t["iv_put_avg"] else "-",
             f"{t['iv_skew'] * 100:+.1f}pt" if t["iv_skew"] is not None else "-"]
            for t in tot]
    print_table(["expiry", "call vol", "put vol", "P/C vol", "IV call", "IV put", "skew"],
                rows)
    un = unusual_activity(snap, vol_oi_min=args.vol_oi,
                          min_volume=args.min_volume, top=args.top)
    if un:
        print(f"\n=== unusual activity (volume >= {args.vol_oi}x OI) ===")
        urows = [[r["side"].upper(), r["strike"], r["expiry"],
                  fmt_shares(r["volume"]), fmt_shares(r["oi"]),
                  f"{r['vol_oi']:.1f}x", f"{r['iv'] * 100:.0f}%" if r["iv"] else "-"]
                 for r in un]
        print_table(["side", "strike", "expiry", "volume", "OI", "v/OI", "IV"], urows)
    else:
        print(f"\nno strikes with volume >= {args.vol_oi}x OI "
              "(quiet positioning, or low-liquidity name)")
    print("\nvolume >> OI = fresh positioning; P/C vol + IV skew = direction/bearish tilt "
          "(yfinance data, delayed)")
