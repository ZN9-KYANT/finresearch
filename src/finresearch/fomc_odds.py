"""finresearch fomc odds — market-implied FOMC decision probabilities via Polymarket.

CME FedWatch is IP-blocked for scraping (Akamai) and ToS-restricted, so the
prediction-market price is the free market-implied distribution: the FOMC series'
child markets are mutually-exclusive rate buckets (25bp cut / hold / 25bp hike...).
Live events only (closed=false); Yes prices ~ probabilities, normalized across
buckets per meeting. Gamma API: gamma-api.polymarket.com (no auth; be gentle).
"""

import json
import urllib.parse
import urllib.request

from .config import DEFAULT_USER_AGENT as UA
from .formatting import fmt_num

GAMMA = "https://gamma-api.polymarket.com"

NORMALIZE = True  # bucket Yes prices are un-normalized (sums observed 1.00-1.02)


def _get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def live_fomc_events(limit=5):
    """Open FOMC decision events, soonest first."""
    url = f"{GAMMA}/events?series_slug=fomc&closed=false&limit={limit}"
    events = _get_json(url)
    events.sort(key=lambda e: e.get("endDate") or "")
    return events


def _bucket_probs(event):
    """[(label, prob)] for the event's mutually-exclusive rate buckets."""
    markets = event.get("markets") or []
    out = []
    for mk in markets:
        label = mk.get("groupItemTitle") or mk.get("question", "")[:40]
        try:
            prices = json.loads(mk.get("outcomePrices") or "[]")
        except (ValueError, TypeError):
            prices = []
        yes = float(prices[0]) if prices else None
        if yes is None:
            continue
        out.append((label, yes))
    if NORMALIZE and out:
        total = sum(p for _, p in out)
        if total > 0:
            out = [(lbl, p / total) for lbl, p in out]
    out.sort(key=lambda t: -t[1])
    return out


def _extract_meeting(event):
    """'Fed decision in october 2026...' -> 'October 2026' best-effort."""
    title = (event.get("title") or "?").replace("Fed decision in ", "")
    title = title.replace("Fed decision ", "").strip()
    return title[:40] or event.get("slug", "?")[:40]


def snapshot(limit=3):
    """[{meeting, end_date, volume, buckets:[(label,prob)]}] for live meetings."""
    out = []
    for ev in live_fomc_events(limit=limit):
        buckets = _bucket_probs(ev)
        if buckets:
            out.append({
                "meeting": _extract_meeting(ev),
                "end_date": ev.get("endDate", ""),
                "volume": ev.get("volume"),
                "buckets": buckets,
            })
    return out


def _fmt_pct(p):
    return f"{p * 100:.1f}%"


def cmd_fomc_odds(args):
    """finresearch fomc odds — market-implied rate-decision probabilities."""
    snap = snapshot(limit=args.limit)
    if args.json:
        print(json.dumps([{**s, "buckets": dict(s["buckets"])} for s in snap],
                          indent=2, default=str))
        return
    if not snap:
        print("No open FOMC events found (between-meetings gap or API change).")
        return
    for s in snap:
        try:
            vol = float(s["volume"] or 0)
            vol_s = fmt_num(vol)
        except (TypeError, ValueError):
            vol_s = str(s["volume"])
        print(f"=== {s['meeting']} (decision market closes {s['end_date'][:10]}, "
              f"vol {vol_s}) ===")
        for label, prob in s["buckets"]:
            bar = "#" * int(round(prob * 30))
            print(f"  {label:>18s}  {_fmt_pct(prob):>6s}  {bar}")
        print()


# used by fomc subcommand wiring
def register(subparsers):
    odds = subparsers.add_parser("odds", help="Market-implied rate-decision probabilities (Polymarket)")
    odds.add_argument("--limit", type=int, default=3, help="Meetings shown (default: 3)")
    odds.add_argument("--json", action="store_true", help="Output as JSON")
