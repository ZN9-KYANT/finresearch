"""Earnings transcript lookup."""


def cmd_transcript(args):
    """Get latest earnings transcript URL from Seeking Alpha."""
    ticker = args.ticker.upper()
    url = f"https://seekingalpha.com/symbol/{ticker}/earnings/transcripts"
    print(f"\n# Earnings Call Transcripts for {ticker}\n")
    print(f"Browse transcripts: {url}\n")
    print("Use crawl4ai to scrape individual transcripts:")
    print('  crwl crawl "<transcript_url>" -o md-fit')
    print(f"\nSeeking Alpha symbol page: https://seekingalpha.com/symbol/{ticker}")
