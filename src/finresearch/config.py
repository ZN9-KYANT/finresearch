"""User-side configuration: config dir, watchlist, and the HTTP User-Agent.

Everything user-specific lives OUTSIDE the repo under ~/.config/finresearch/
(override the directory with FINRESEARCH_CONFIG_DIR). Nothing personal is
ever hard-coded here.
"""

import os
from pathlib import Path

from . import __version__

DEMO_WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META"]


def config_dir():
    """~/.config/finresearch, or $FINRESEARCH_CONFIG_DIR."""
    return Path(os.environ.get("FINRESEARCH_CONFIG_DIR")
                or Path.home() / ".config" / "finresearch")


def cache_dir():
    """~/.cache/finresearch (downloaded reference data, saved scan output)."""
    return Path.home() / ".cache" / "finresearch"


def watchlist_path():
    """User watchlist file (one ticker per line, # comments allowed)."""
    return config_dir() / "watchlist.txt"


def load_watchlist():
    """Tickers from the watchlist file, else a neutral demo list."""
    try:
        with open(watchlist_path()) as fh:
            tickers = [ln.strip().upper() for ln in fh
                       if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError:
        tickers = []
    return tickers or list(DEMO_WATCHLIST)


# Declared tool UA for official APIs (SEC, FINRA, FRED, Polymarket). SEC
# EDGAR 403s a UA whose final token is not a deliverable-looking email, so the
# default ends in one; set FINRESEARCH_SEC_UA="your-tool/1.0 you@domain" when
# running heavily so SEC can reach you.
DEFAULT_USER_AGENT = f"finresearch/{__version__} contact@example.com"


def user_agent():
    return os.getenv("FINRESEARCH_SEC_UA") or DEFAULT_USER_AGENT
