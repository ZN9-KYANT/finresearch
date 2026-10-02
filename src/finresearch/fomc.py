"""FOMC (Federal Open Market Committee) statements, minutes, and sentiment analysis.

Scrapes federalreserve.gov for:
- FOMC meeting calendar
- Press release statements (HTML)
- Meeting minutes (HTML)
- Hawkish/dovish sentiment diff between meetings
"""

import functools
import json as json_module
import re
import sys
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

FED_BASE = "https://www.federalreserve.gov"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

# Known FOMC meeting dates (2023-2027) — used for URL construction
# URL pattern: monetaryYYYYMMDDa.htm (statement), fomcminutesYYYYMMDD.htm (minutes)
FOMC_MEETINGS = [
    # 2027 (tentative)
    {"date": "2027-01-26", "end": "2027-01-27", "sep": False, "year": 2027},
    {"date": "2027-03-16", "end": "2027-03-17", "sep": True, "year": 2027},
    {"date": "2027-04-27", "end": "2027-04-28", "sep": False, "year": 2027},
    {"date": "2027-06-08", "end": "2027-06-09", "sep": True, "year": 2027},
    {"date": "2027-07-27", "end": "2027-07-28", "sep": False, "year": 2027},
    {"date": "2027-09-14", "end": "2027-09-15", "sep": True, "year": 2027},
    {"date": "2027-10-26", "end": "2027-10-27", "sep": False, "year": 2027},
    {"date": "2027-12-07", "end": "2027-12-08", "sep": True, "year": 2027},
    # 2026
    {"date": "2026-01-27", "end": "2026-01-28", "sep": False, "year": 2026, "minutes": "2026-02-18"},
    {"date": "2026-03-17", "end": "2026-03-18", "sep": True, "year": 2026, "minutes": "2026-04-08"},
    {"date": "2026-04-28", "end": "2026-04-29", "sep": False, "year": 2026, "minutes": "2026-05-20"},
    {"date": "2026-06-16", "end": "2026-06-17", "sep": True, "year": 2026},
    {"date": "2026-07-28", "end": "2026-07-29", "sep": False, "year": 2026},
    {"date": "2026-09-15", "end": "2026-09-16", "sep": True, "year": 2026},
    {"date": "2026-10-27", "end": "2026-10-28", "sep": False, "year": 2026},
    {"date": "2026-12-08", "end": "2026-12-09", "sep": True, "year": 2026},
    # 2025
    {"date": "2025-01-28", "end": "2025-01-29", "sep": False, "year": 2025, "minutes": "2025-02-19"},
    {"date": "2025-03-18", "end": "2025-03-19", "sep": True, "year": 2025, "minutes": "2025-04-09"},
    {"date": "2025-05-06", "end": "2025-05-07", "sep": False, "year": 2025, "minutes": "2025-05-28"},
    {"date": "2025-06-17", "end": "2025-06-18", "sep": True, "year": 2025, "minutes": "2025-07-09"},
    {"date": "2025-07-29", "end": "2025-07-30", "sep": False, "year": 2025, "minutes": "2025-08-20"},
    {"date": "2025-09-16", "end": "2025-09-17", "sep": True, "year": 2025, "minutes": "2025-10-08"},
    {"date": "2025-10-28", "end": "2025-10-29", "sep": False, "year": 2025, "minutes": "2025-11-19"},
    {"date": "2025-12-09", "end": "2025-12-10", "sep": True, "year": 2025, "minutes": "2025-12-30"},
    # 2024
    {"date": "2024-01-30", "end": "2024-01-31", "sep": False, "year": 2024, "minutes": "2024-02-21"},
    {"date": "2024-03-19", "end": "2024-03-20", "sep": True, "year": 2024, "minutes": "2024-04-10"},
    {"date": "2024-04-30", "end": "2024-05-01", "sep": False, "year": 2024, "minutes": "2024-05-22"},
    {"date": "2024-06-11", "end": "2024-06-12", "sep": True, "year": 2024, "minutes": "2024-07-03"},
    {"date": "2024-07-30", "end": "2024-07-31", "sep": False, "year": 2024, "minutes": "2024-08-21"},
    {"date": "2024-09-17", "end": "2024-09-18", "sep": True, "year": 2024, "minutes": "2024-10-09"},
    {"date": "2024-11-06", "end": "2024-11-07", "sep": False, "year": 2024, "minutes": "2024-11-26"},
    {"date": "2024-12-17", "end": "2024-12-18", "sep": True, "year": 2024, "minutes": "2025-01-08"},
    # 2023
    {"date": "2023-01-31", "end": "2023-02-01", "sep": False, "year": 2023, "minutes": "2023-02-22"},
    {"date": "2023-03-21", "end": "2023-03-22", "sep": True, "year": 2023, "minutes": "2023-04-12"},
    {"date": "2023-05-02", "end": "2023-05-03", "sep": False, "year": 2023, "minutes": "2023-05-24"},
    {"date": "2023-06-13", "end": "2023-06-14", "sep": True, "year": 2023, "minutes": "2023-07-05"},
    {"date": "2023-07-25", "end": "2023-07-26", "sep": False, "year": 2023, "minutes": "2023-08-16"},
    {"date": "2023-09-19", "end": "2023-09-20", "sep": True, "year": 2023, "minutes": "2023-10-11"},
    {"date": "2023-10-31", "end": "2023-11-01", "sep": False, "year": 2023, "minutes": "2023-11-21"},
    {"date": "2023-12-12", "end": "2023-12-13", "sep": True, "year": 2023, "minutes": "2024-01-03"},
    # 2022
    {"date": "2022-01-25", "end": "2022-01-26", "sep": False, "year": 2022, "minutes": "2022-02-16"},
    {"date": "2022-03-15", "end": "2022-03-16", "sep": True, "year": 2022, "minutes": "2022-04-06"},
    {"date": "2022-05-03", "end": "2022-05-04", "sep": False, "year": 2022, "minutes": "2022-05-25"},
    {"date": "2022-06-14", "end": "2022-06-15", "sep": True, "year": 2022, "minutes": "2022-07-06"},
    {"date": "2022-07-26", "end": "2022-07-27", "sep": False, "year": 2022, "minutes": "2022-08-17"},
    {"date": "2022-09-20", "end": "2022-09-21", "sep": True, "year": 2022, "minutes": "2022-10-12"},
    {"date": "2022-11-01", "end": "2022-11-02", "sep": False, "year": 2022, "minutes": "2022-11-23"},
    {"date": "2022-12-13", "end": "2022-12-14", "sep": True, "year": 2022, "minutes": "2023-01-04"},
]

# Hawkish / dovish keyword lists for sentiment analysis
HAWKISH_TERMS = {
    "aggressive": 2, "tighten": 2, "tightening": 2, "firm": 1, "resolve": 1,
    "committed": 1, "vigilant": 2, "forceful": 2, "must": 1, "necessary": 1,
    "unacceptable": 2, "persistent": 1, "entrenched": 2, "price stability": 1,
    "reduce balance sheet": 2, "quantitative tightening": 2, "rate increase": 2,
    "rate hike": 2, "higher rates": 2, "restrictive": 2, "restrictive stance": 2,
    "above trend": 1, "overheated": 2, "overheating": 2, "exceed": 1,
    "carefully assess": 1, "wait": 1,
    "not yet": 1, "not appropriate": 1, "greater confidence": 1,
    "sustainably": 1, "convincing": 1, "signal": 1,
    "bearish": 1, "robust": 1, "strong": 1, "solid": 1, "above target": 1,
    "strongly committed": 2, "attentive to inflation": 2,
}

DOVISH_TERMS = {
    "accommodative": 2, "ease": 2, "easing": 2, "support": 1, "patient": 1,
    "measured": 1, "gradual": 1, "calibrate": 1,
    "transitory": 2, "temporary": 1, "moderate": 1, "moderating": 1,
    "slowing": 1, "softening": 1, "fragile": 1, "weakness": 1, "weak": 1,
    "uncertain": 1, "uncertainty": 1, "downside": 1, "risk": 1,
    "balance of risks": 1, "moving into better balance": 2,
    "below trend": 1, "slack": 1, "headwinds": 1,
    "disinflation": 2, "disinflationary": 2, "easing inflation": 2,
    "inflation has eased": 2, "inflation has slowed": 2,
    "rate cut": 2, "reduce the target range": 2, "lower rates": 2,
    "cut rates": 2, "bullish": 1, "neutral": 1, "normalizing": 1,
    "soft landing": 2, "goldilocks": 2, "approaching target": 1,
    "confident": 1, "sustainable": 1, "gaining confidence": 1,
}

# Context-dependent terms ("data dependent", "progress") are deliberately in
# neither list: a term scored on both sides only adds noise.


def _parse_date(date_str):
    """Parse YYYY-MM-DD string to datetime."""
    return datetime.strptime(date_str, "%Y-%m-%d")


def _statement_url(meeting):
    """Build the statement press release URL for a meeting."""
    # Use the END date of the meeting (statement released on last day)
    end_date = meeting.get("end", meeting["date"])
    d = _parse_date(end_date)
    return f"{FED_BASE}/newsevents/pressreleases/monetary{d.strftime('%Y%m%d')}a.htm"


def _minutes_url(meeting):
    """Build the minutes URL for a meeting.
    The Fed's site uses the meeting END date for the URL, not the release date.
    e.g. fomcminutes20260128.htm for the Jan 27-28 meeting.
    """
    # Minutes URL uses the END date of the meeting
    end_date = meeting.get("end", meeting["date"])
    d = _parse_date(end_date)
    return f"{FED_BASE}/monetarypolicy/fomcminutes{d.strftime('%Y%m%d')}.htm"


def _fetch_url(url):
    """Fetch and parse HTML from a URL."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        return resp.text
    except requests.RequestException:
        return None


def _extract_statement_text(html):
    """Extract the main statement text from the press release HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # The Fed's HTML puts all content in div.container.container__main
    # The statement text is NOT in <p> tags — it's raw text in the div
    content = soup.select_one("div.container.container__main")
    if not content:
        # Fallback to col-md-8
        for selector in [".col-md-8", "article", "main", "#content"]:
            content = soup.select_one(selector)
            if content:
                break
    if not content:
        content = soup.body or soup

    # Get full text and filter boilerplate
    full_text = content.get_text(separator="\n", strip=True)

    # Find the actual statement — starts after "approved the following statement"
    # and ends before "Voting for" or "For media inquiries" or "Implementation Note"
    lines = full_text.split("\n")
    statement_lines = []
    in_statement = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Start capturing when we hit the statement content
        if "approved the following statement" in line.lower():
            in_statement = True
            # Include this line (it has the vote count)
            statement_lines.append(line)
            continue
        if "Committee decided" in line and not in_statement:
            in_statement = True

        # Stop at end markers
        if in_statement:
            if line.startswith(("For media inquiries", "Last Update", "Implementation Note",
                                "Voting for", "For release at")):
                if "Voting for" in line:
                    statement_lines.append(line)  # Include voting members
                    continue
                break
            statement_lines.append(line)

    if statement_lines:
        return "\n\n".join(statement_lines)

    # Fallback: return everything after "For release at" line
    lines = full_text.split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        if "For release at" in line:
            start_idx = i + 1
            break
    return "\n".join(lines[start_idx:start_idx + 50]).strip()


def _extract_minutes_text(html):
    """Extract minutes text from the minutes HTML page."""
    soup = BeautifulSoup(html, "html.parser")

    content = None
    for selector in [".col-md-8", "div.col-xs-12.col-sm-8", "article", "main", "#content"]:
        content = soup.select_one(selector)
        if content:
            break

    if not content:
        content = soup.body or soup

    # Same approach as statement — get full text, filter boilerplate
    full_text = content.get_text(separator="\n\n", strip=True)
    blocks = full_text.split("\n\n")
    minutes_blocks = []
    boilerplate_prefixes = (
        "Search", "Sections", "Home", "News & Events",
        "Official websites use", "Secure .gov", "Last Update",
        "Skip to", "Toggle", "Advanced", "Share", "Subscribe",
        "Please enable JavaScript", "PDF",
    )
    boilerplate_contains = (
        "media@frb.gov", "twitter.com/share", "facebook.com/sharer",
        "linkedin.com/shareArticle", "Last Update",
    )

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 15:
            continue
        if block.startswith(boilerplate_prefixes):
            continue
        if any(bp in block for bp in boilerplate_contains):
            continue
        minutes_blocks.append(block)

    return "\n\n".join(minutes_blocks) if minutes_blocks else full_text


def _get_meeting_by_date(date_str):
    """Find a meeting by date string (YYYY-MM-DD) — matches either start or end date."""
    for m in FOMC_MEETINGS:
        if m["date"] == date_str or m.get("end") == date_str:
            return m
    return None


def _get_completed_meetings():
    """Get meetings that have already occurred (statement should be available), newest first."""
    now = datetime.now()
    completed = []
    for m in FOMC_MEETINGS:
        end = _parse_date(m.get("end", m["date"]))
        if end < now:
            completed.append(m)
    # Sort newest first
    completed.sort(key=lambda m: _parse_date(m["date"]), reverse=True)
    return completed


def _get_next_meeting():
    """Get the next upcoming meeting."""
    now = datetime.now()
    upcoming = [m for m in FOMC_MEETINGS if _parse_date(m["date"]) > now]
    upcoming.sort(key=lambda m: _parse_date(m["date"]))
    return upcoming[0] if upcoming else None


def _get_recent_meetings(n=2):
    """Get the N most recent completed meetings, newest first."""
    completed = _get_completed_meetings()
    return completed[:n]


@functools.lru_cache(maxsize=None)
def _term_regex(term):
    """Whole-word, case-insensitive matcher ('ease' must not hit 'increase');
    a trailing plural 's' is allowed, internal spaces match any whitespace."""
    body = r"\s+".join(re.escape(w) for w in term.lower().split())
    return re.compile(rf"\b{body}s?\b", re.IGNORECASE)


def _count_terms(text, terms):
    """{term: count}, longest phrase first; each match is masked once counted,
    so 'strongly committed' is not also counted as 'committed'."""
    counts = {}
    for term in sorted(terms, key=len, reverse=True):
        rx = _term_regex(term)
        n = len(rx.findall(text))
        if n:
            counts[term] = n
            text = rx.sub(lambda m: " " * len(m.group(0)), text)
    return counts


def _analyze_sentiment(text):
    """Analyze text for hawkish/dovish sentiment. Returns a score dict."""
    counts = _count_terms(text, list(HAWKISH_TERMS) + list(DOVISH_TERMS))

    def hits(table):
        return {t: {"count": counts[t], "weight": w, "score": counts[t] * w}
                for t, w in table.items() if t in counts}

    hawkish_hits = hits(HAWKISH_TERMS)
    dovish_hits = hits(DOVISH_TERMS)

    hawkish_score = sum(h["score"] for h in hawkish_hits.values())
    dovish_score = sum(d["score"] for d in dovish_hits.values())
    total = hawkish_score + dovish_score

    if total == 0:
        stance = "neutral"
        hawkish_pct = 50
    else:
        hawkish_pct = round(hawkish_score / total * 100, 1)
        if hawkish_pct >= 65:
            stance = "hawkish"
        elif hawkish_pct >= 55:
            stance = "slightly hawkish"
        elif hawkish_pct <= 35:
            stance = "dovish"
        elif hawkish_pct <= 45:
            stance = "slightly dovish"
        else:
            stance = "neutral"

    return {
        "stance": stance,
        "hawkish_score": hawkish_score,
        "dovish_score": dovish_score,
        "hawkish_pct": hawkish_pct,
        "dovish_pct": round(100 - hawkish_pct, 1),
        "hawkish_terms": hawkish_hits,
        "dovish_terms": dovish_hits,
    }


def _format_sentiment_summary(sentiment):
    """Format a sentiment dict into a readable line."""
    stance = sentiment["stance"]
    hawk = sentiment["hawkish_score"]
    dove = sentiment["dovish_score"]
    pct = sentiment["hawkish_pct"]
    return f"{stance} (hawkish: {hawk}, dovish: {dove}, {pct}% hawkish)"


def cmd_fomc(args):
    """Main FOMC command handler."""
    if args.subcommand == "calendar":
        _cmd_calendar(args)
    elif args.subcommand == "statement":
        _cmd_statement(args)
    elif args.subcommand == "minutes":
        _cmd_minutes(args)
    elif args.subcommand == "sentiment":
        _cmd_sentiment(args)
    elif args.subcommand == "odds":
        from .fomc_odds import cmd_fomc_odds
        cmd_fomc_odds(args)
    elif args.subcommand is None:
        # Default: show calendar
        _cmd_calendar(args)


def _cmd_calendar(args):
    """Show FOMC meeting calendar."""
    json_output = getattr(args, "json", False)

    # Find next meeting
    next_m = _get_next_meeting()
    now = datetime.now()

    if json_output:
        meetings = []
        for m in FOMC_MEETINGS:
            meetings.append({
                "date": m["date"],
                "end": m.get("end", m["date"]),
                "sep": m.get("sep", False),
                "year": m.get("year"),
                "minutes_date": m.get("minutes"),
                "status": "past" if _parse_date(m.get("end", m["date"])) < now else "future",
            })
        result = {
            "next_meeting": {"date": next_m["date"], "end": next_m["end"]} if next_m else None,
            "meetings": meetings,
        }
        print(json_module.dumps(result, indent=2))
        return

    print("\n# 📅 FOMC Meeting Calendar\n")

    if next_m:
        next_start = _parse_date(next_m["date"])
        days_until = (next_start - now).days
        print(f"**Next meeting:** {next_m['date']} → {next_m['end']}  "
              f"({days_until} days away{'  ★ SEP' if next_m.get('sep') else ''})\n")

    # Group by year, most recent first
    sorted_meetings = sorted(FOMC_MEETINGS, key=lambda m: _parse_date(m["date"]), reverse=True)
    current_year = None
    for m in sorted_meetings:
        y = m.get("year", _parse_date(m["date"]).year)
        if y != current_year:
            current_year = y
            print(f"## {y}")

        end_date = _parse_date(m.get("end", m["date"]))
        status = "✅" if end_date < now else "⏳"
        sep_mark = " ★" if m.get("sep") else ""
        minutes_str = f"  *(minutes: {m['minutes']})*" if m.get("minutes") else ""

        print(f"- {status} {m['date']} → {m.get('end', m['date'])}{sep_mark}{minutes_str}")
        print()


def _cmd_statement(args):
    """Fetch an FOMC statement."""
    json_output = getattr(args, "json", False)

    if args.date:
        meeting = _get_meeting_by_date(args.date)
        if not meeting:
            # Try to find by partial match
            matches = [m for m in FOMC_MEETINGS if args.date in m["date"] or args.date in m.get("end", "")]
            if matches:
                meeting = matches[-1]  # Most recent match
            else:
                print(f"\n*No meeting found for date '{args.date}'*", file=sys.stderr)
                print("Available dates can be found with: finresearch fomc calendar", file=sys.stderr)
                sys.exit(1)
    else:
        # Get most recent completed meeting
        recent = _get_recent_meetings(1)
        if not recent:
            print("\n*No completed meetings found*", file=sys.stderr)
            sys.exit(1)
        meeting = recent[-1]

    url = _statement_url(meeting)
    html = _fetch_url(url)

    if not html:
        print(f"\n*Could not fetch statement for {meeting['date']}*", file=sys.stderr)
        print(f"URL: {url}", file=sys.stderr)
        sys.exit(1)

    text = _extract_statement_text(html)

    if json_output:
        result = {
            "meeting_date": meeting["date"],
            "end_date": meeting.get("end", meeting["date"]),
            "url": url,
            "statement": text,
            "sentiment": _analyze_sentiment(text),
        }
        print(json_module.dumps(result, indent=2))
        return

    print(f"\n# FOMC Statement — {meeting['date']}")
    print(f"**URL:** {url}\n")
    print(text)

    # Always include sentiment
    sentiment = _analyze_sentiment(text)
    print(f"\n---\n**Sentiment:** {_format_sentiment_summary(sentiment)}")


def _cmd_minutes(args):
    """Fetch FOMC meeting minutes."""
    json_output = getattr(args, "json", False)

    if args.date:
        meeting = _get_meeting_by_date(args.date)
        if not meeting:
            matches = [m for m in FOMC_MEETINGS if args.date in m["date"] or args.date in m.get("end", "")]
            if matches:
                meeting = matches[-1]
            else:
                print(f"\n*No meeting found for date '{args.date}'*", file=sys.stderr)
                sys.exit(1)
    else:
        # Find most recent meeting that has minutes available
        # Minutes are released ~3 weeks after the meeting
        recent = _get_completed_meetings()
        meeting = None
        for m in recent:  # Already newest first
            # Check if minutes would be available (meeting end + 21 days)
            end_date = _parse_date(m.get("end", m["date"]))
            minutes_available_date = end_date + timedelta(days=21)
            if datetime.now() >= minutes_available_date:
                meeting = m
                break
        if not meeting:
            print("\n*No minutes available yet for recent meetings*", file=sys.stderr)
            sys.exit(1)

    url = _minutes_url(meeting)
    html = _fetch_url(url)

    if not html:
        print(f"\n*Could not fetch minutes for {meeting['date']}*", file=sys.stderr)
        print(f"URL: {url}", file=sys.stderr)
        sys.exit(1)

    text = _extract_minutes_text(html)

    if json_output:
        result = {
            "meeting_date": meeting["date"],
            "minutes_date": meeting.get("minutes"),
            "url": url,
            "minutes": text,
        }
        print(json_module.dumps(result, indent=2))
        return

    print(f"\n# FOMC Minutes — {meeting['date']}")
    print(f"**Released:** {meeting.get('minutes', '?')}")
    print(f"**URL:** {url}\n")

    # Show full text or summary depending on --full flag
    if args.full:
        print(text)
    else:
        # Show first ~2000 chars as summary
        if len(text) > 2000:
            print(text[:2000])
            print(f"\n... [{len(text) - 2000} more characters — use --full to see all]")
        else:
            print(text)

    print("\n---\n*Source: Federal Reserve*")


def _cmd_sentiment(args):
    """Compare sentiment between the two most recent FOMC statements."""
    json_output = getattr(args, "json", False)

    recent = _get_recent_meetings(3)  # Get up to 3 recent meetings, newest first
    if len(recent) < 2:
        print("\n*Need at least 2 completed meetings for sentiment diff*", file=sys.stderr)
        sys.exit(1)

    # Fetch the two most recent statements (newest first)
    current_meeting = recent[0]
    previous_meeting = recent[1]

    current_html = _fetch_url(_statement_url(current_meeting))
    previous_html = _fetch_url(_statement_url(previous_meeting))

    if not current_html or not previous_html:
        print("\n*Could not fetch both statements for comparison*", file=sys.stderr)
        sys.exit(1)

    current_text = _extract_statement_text(current_html)
    previous_text = _extract_statement_text(previous_html)

    current_sent = _analyze_sentiment(current_text)
    previous_sent = _analyze_sentiment(previous_text)

    # Find terms that changed
    def _term_diff(prev_terms, curr_terms):
        changes = []
        for term in set(list(prev_terms.keys()) + list(curr_terms.keys())):
            prev_count = prev_terms.get(term, {}).get("count", 0)
            curr_count = curr_terms.get(term, {}).get("count", 0)
            if prev_count != curr_count:
                changes.append({
                    "term": term,
                    "prev": prev_count,
                    "curr": curr_count,
                    "change": curr_count - prev_count,
                })
        return changes

    hawkish_changes = _term_diff(previous_sent["hawkish_terms"], current_sent["hawkish_terms"])
    dovish_changes = _term_diff(previous_sent["dovish_terms"], current_sent["dovish_terms"])

    # Removed/added phrase detection was too word-noisy; key-phrase tracking below.
    # Check for specific high-impact phrases
    KEY_PHRASES = [
        "patient", "transitory", "restrictive", "accommodative", "neutral",
        "substantial further progress", "greater confidence", "data dependent",
        "moving into better balance", "highly attentive to inflation",
        "strongly committed", "appropriate pace", "balance of risks",
        "tightly balanced", "sustainably toward 2 percent",
        "gaining confidence", "convincing", "progress on inflation",
        "not yet", "not appropriate", "carefully assess",
    ]

    phrase_changes = []
    for phrase in KEY_PHRASES:
        prev_count = len(_term_regex(phrase).findall(previous_text))
        curr_count = len(_term_regex(phrase).findall(current_text))
        if prev_count != curr_count:
            phrase_changes.append({
                "phrase": phrase,
                "prev": prev_count,
                "curr": curr_count,
                "change": curr_count - prev_count,
                "direction": "added" if curr_count > prev_count else "removed" if curr_count < prev_count else "changed",
            })

    if json_output:
        result = {
            "current_meeting": current_meeting["date"],
            "previous_meeting": previous_meeting["date"],
            "current_sentiment": current_sent,
            "previous_sentiment": previous_sent,
            "stance_shift": {
                "from": previous_sent["stance"],
                "to": current_sent["stance"],
                "hawkish_score_change": current_sent["hawkish_score"] - previous_sent["hawkish_score"],
                "dovish_score_change": current_sent["dovish_score"] - previous_sent["dovish_score"],
            },
            "phrase_changes": phrase_changes,
            "hawkish_term_changes": hawkish_changes,
            "dovish_term_changes": dovish_changes,
        }
        print(json_module.dumps(result, indent=2))
        return

    print("\n# 🔍 FOMC Sentiment Diff\n")
    print(f"**Previous:** {previous_meeting['date']} → {_format_sentiment_summary(previous_sent)}")
    print(f"**Current:**  {current_meeting['date']} → {_format_sentiment_summary(current_sent)}")

    # Stance shift
    hawk_delta = current_sent["hawkish_score"] - previous_sent["hawkish_score"]
    dove_delta = current_sent["dovish_score"] - previous_sent["dovish_score"]
    print("\n## Stance Shift")
    print(f"- Hawkish score: {previous_sent['hawkish_score']} → {current_sent['hawkish_score']} ({'+' if hawk_delta >= 0 else ''}{hawk_delta})")
    print(f"- Dovish score: {previous_sent['dovish_score']} → {current_sent['dovish_score']} ({'+' if dove_delta >= 0 else ''}{dove_delta})")
    print(f"- Stance: {previous_sent['stance']} → {current_sent['stance']}")

    # Key phrase changes
    if phrase_changes:
        print("\n## Key Phrase Changes\n")
        for pc in phrase_changes:
            direction_emoji = "🆕" if pc["change"] > 0 else "❌" if pc["change"] < 0 else "✏️"
            print(f"- {direction_emoji} \"{pc['phrase']}\" — {pc['prev']} → {pc['curr']} ({pc['direction']})")

    # New hawkish terms
    new_hawkish = [c for c in hawkish_changes if c["change"] > 0]
    removed_hawkish = [c for c in hawkish_changes if c["change"] < 0]
    new_dovish = [c for c in dovish_changes if c["change"] > 0]
    removed_dovish = [c for c in dovish_changes if c["change"] < 0]

    if new_hawkish:
        print("\n## New Hawkish Signals\n")
        for c in new_hawkish:
            print(f"- \"{c['term']}\" ({c['prev']} → {c['curr']})")

    if new_dovish:
        print("\n## New Dovish Signals\n")
        for c in new_dovish:
            print(f"- \"{c['term']}\" ({c['prev']} → {c['curr']})")

    if removed_hawkish:
        print("\n## Removed Hawkish Signals\n")
        for c in removed_hawkish:
            print(f"- \"{c['term']}\" ({c['prev']} → {c['curr']})")

    if removed_dovish:
        print("\n## Removed Dovish Signals\n")
        for c in removed_dovish:
            print(f"- \"{c['term']}\" ({c['prev']} → {c['curr']})")

    if not phrase_changes and not new_hawkish and not new_dovish and not removed_hawkish and not removed_dovish:
        print("\n*No significant language changes detected between meetings.*")

    print("\n---\n*Sentiment analysis: keyword-based, for informational purposes only*")
