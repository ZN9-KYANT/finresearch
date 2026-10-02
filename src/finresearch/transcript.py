"""Earnings transcript lookup (pointer only: transcripts are not redistributable)."""

from .output import emit_json


def cmd_transcript(args):
    """Where to read the latest earnings call transcripts for a ticker."""
    ticker = args.ticker.upper()
    links = {
        "ticker": ticker,
        "transcripts_url": f"https://seekingalpha.com/symbol/{ticker}/earnings/transcripts",
        "symbol_url": f"https://seekingalpha.com/symbol/{ticker}",
        "scrape_hint": 'crwl crawl "<transcript_url>" -o md-fit',
    }
    if getattr(args, "json", False):
        emit_json(links)
        return
    print(f"\n# Earnings Call Transcripts for {ticker}\n")
    print(f"Browse transcripts: {links['transcripts_url']}\n")
    print("Use crawl4ai to scrape individual transcripts:")
    print(f"  {links['scrape_hint']}")
    print(f"\nSeeking Alpha symbol page: {links['symbol_url']}")
