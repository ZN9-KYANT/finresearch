"""CLI entry point for finresearch: argparse wiring + dispatch only.

Command modules are imported lazily on dispatch, so commands that never touch
pandas/yfinance (fomc, fred, edgar...) don't pay for importing them.
"""

import argparse
import importlib
import sys

from . import __version__

# command -> (module, handler)
COMMANDS = {
    "ticker": ("yfinance_cmd", "cmd_ticker"),
    "compare": ("yfinance_cmd", "cmd_compare"),
    "sec": ("sec_edgar", "cmd_sec"),
    "transcript": ("transcript", "cmd_transcript"),
    "gappers": ("premarket_gappers", "cmd_gappers"),
    "news": ("news", "cmd_news"),
    "screen": ("screener", "cmd_screen"),
    "fred": ("fred", "cmd_fred"),
    "fomc": ("fomc", "cmd_fomc"),
    "scan": ("market_scan", "cmd_market_scan"),
    "insider": ("insiders", "cmd_insider"),
    "13f": ("form13f", "cmd_13f"),
    "activist": ("activist", "cmd_activist"),
    "dilution": ("dilution", "cmd_dilution"),
    "buyback": ("buyback", "cmd_buyback"),
    "8k": ("events8k", "cmd_8k"),
    "options": ("options_flow", "cmd_options"),
    "ftd": ("ftd", "cmd_ftd"),
    "short": ("short_interest", "cmd_short"),
}


def main():
    parser = argparse.ArgumentParser(
        prog="finresearch",
        description="Financial Research Toolkit — Free alternative to financialdatasets.ai",
    )
    parser.add_argument("--version", action="version", version=f"finresearch {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ticker command
    t_parser = subparsers.add_parser("ticker", help="Get ticker data via yfinance")
    t_parser.add_argument("ticker", help="Ticker symbol (e.g. VST)")
    t_parser.add_argument(
        "--section",
        choices=["overview", "financials", "kpis", "earnings", "insiders", "holdings", "technicals", "all"],
        default="overview",
        help="Section to display (default: overview)",
    )
    t_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # sec command
    s_parser = subparsers.add_parser("sec", help="SEC EDGAR structured data")
    s_parser.add_argument("ticker", help="Ticker symbol (e.g. VST)")
    s_parser.add_argument("--type", help="Filing type filter (10-K, 10-Q, 8-K)")
    s_parser.add_argument("--concept", help="XBRL concept (e.g. revenue, net_income, eps, or raw tag)")

    # transcript command
    tr_parser = subparsers.add_parser("transcript", help="Earnings transcript info")
    tr_parser.add_argument("ticker", help="Ticker symbol")

    # compare command
    c_parser = subparsers.add_parser("compare", help="Compare multiple tickers")
    c_parser.add_argument("tickers", nargs="+", help="Ticker symbols to compare")

    # gappers command
    g_parser = subparsers.add_parser("gappers", help="Premarket gappers scanner")
    g_parser.add_argument("--min-gap", type=float, default=5.0,
                          help="Minimum gap %% (default: 5)")
    g_parser.add_argument("--min-price", type=float, default=3.0,
                          help="Minimum price $ (default: 3)")
    g_parser.add_argument("--min-volume", type=int, default=50000,
                          help="Minimum volume (default: 50000)")
    g_parser.add_argument("--max-results", type=int, default=10,
                          help="Max results (default: 10)")
    g_parser.add_argument("--no-catalyst", action="store_true",
                          help="Skip catalyst/news lookup (equivalent to --catalyst none)")
    g_parser.add_argument("--catalyst",
                          choices=["google_finance", "crawl4ai", "none"],
                          default=None,
                          help="Catalyst source (default: google_finance). "
                               "crawl4ai requires 'pip install crawl4ai'")
    g_parser.add_argument("--source", choices=["auto", "tradingview", "stockanalysis"],
                          default="auto",
                          help="Data source (default: auto = TV then SA)")
    g_parser.add_argument("--format", choices=["markdown", "json"], default="markdown",
                          dest="output_format",
                          help="Output format (default: markdown)")
    g_parser.add_argument("--output-dir", type=str, default=None,
                          help="Output directory for JSON file")

    # news command
    n_parser = subparsers.add_parser("news", help="News headlines for a ticker (Google Finance SSR)")
    n_parser.add_argument("ticker", help="Ticker symbol (e.g. CBRS)")
    n_parser.add_argument("--max-items", type=int, default=15,
                          help="Max headlines to show (default: 15)")
    n_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # screen command
    sc_parser = subparsers.add_parser("screen", help="Screen stocks by fundamental metrics")
    sc_parser.add_argument("--tickers", type=str, default=None,
                           help="Comma-separated tickers to screen")
    sc_parser.add_argument("--watchlist", action="store_true",
                           help="Use tickers from ~/.config/finresearch/watchlist.txt")
    sc_parser.add_argument("--sector", type=str, default=None,
                           help="Filter by sector (substring match, e.g. 'Technology')")
    sc_parser.add_argument("--industry", type=str, default=None,
                           help="Filter by industry (substring match)")
    sc_parser.add_argument("--min-pe", type=float, default=None, help="Min trailing P/E")
    sc_parser.add_argument("--max-pe", type=float, default=None, help="Max trailing P/E")
    sc_parser.add_argument("--min-fwd-pe", type=float, default=None, help="Min forward P/E")
    sc_parser.add_argument("--max-fwd-pe", type=float, default=None, help="Max forward P/E")
    sc_parser.add_argument("--min-peg", type=float, default=None, help="Min PEG ratio")
    sc_parser.add_argument("--max-peg", type=float, default=None, help="Max PEG ratio")
    sc_parser.add_argument("--min-revgrowth", type=float, default=None,
                           help="Min revenue growth %% YoY (e.g. 50 for 50%%)")
    sc_parser.add_argument("--min-margin", type=float, default=None,
                           help="Min operating margin %% (e.g. 20 for 20%%)")
    sc_parser.add_argument("--max-debt-equity", type=float, default=None, help="Max debt/equity")
    sc_parser.add_argument("--min-mktcap", type=float, default=None, help="Min market cap (in LISTING currency: JPY-capped names compare in JPY)")
    sc_parser.add_argument("--max-mktcap", type=float, default=None, help="Max market cap (in LISTING currency)")
    sc_parser.add_argument("--min-beta", type=float, default=None, help="Min beta")
    sc_parser.add_argument("--max-beta", type=float, default=None, help="Max beta")
    sc_parser.add_argument("--sort", choices=["mktcap", "pe", "fwd_pe", "peg", "growth", "price"],
                           default="mktcap", help="Sort field (default: mktcap)")
    sc_parser.add_argument("--ascending", action="store_true", help="Sort ascending (default: descending)")
    sc_parser.add_argument("--quiet", action="store_true", help="Hide excluded tickers")
    sc_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # fred command (FRED macro data)
    fr_parser = subparsers.add_parser("fred", help="FRED macroeconomic data (Fed Reserve)")
    fr_sub = fr_parser.add_subparsers(dest="subcommand", help="FRED subcommand")

    # fred series
    fr_series = fr_sub.add_parser("series", help="Fetch a specific FRED series")
    fr_series.add_argument("series_name", help="Series alias (e.g. fed_funds) or raw FRED ID (e.g. DGS10)")
    fr_series.add_argument("--days", type=int, default=None,
                            help="Lookback N days")
    fr_series.add_argument("--years", type=float, default=None,
                            help="Lookback N years")
    fr_series.add_argument("--start-date", type=str, default=None,
                            help="Start date YYYY-MM-DD")
    fr_series.add_argument("--end-date", type=str, default=None,
                            help="End date YYYY-MM-DD")
    fr_series.add_argument("--last", type=int, default=5,
                            help="Show last N observations (default: 5)")
    fr_series.add_argument("--json", action="store_true", help="Output as JSON")

    # fred dashboard
    fr_dash = fr_sub.add_parser("dashboard", help="Macro dashboard (all key indicators)")
    from .fred import DASHBOARD_GROUPS
    fr_dash.add_argument("--group", choices=list(DASHBOARD_GROUPS), default=None,
                         help="Show only one group")

    # fred search
    fr_search = fr_sub.add_parser("search", help="Search FRED series by keyword")
    fr_search.add_argument("query", help="Search text (e.g. 'unemployment', 'GDP')")
    fr_search.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
    fr_search.add_argument("--json", action="store_true", help="Output as JSON")

    # fred list
    fr_sub.add_parser("list", help="List all available series aliases")

    # fred yield_curve
    fr_sub.add_parser("yield_curve", help="Current Treasury yield curve + spreads")

    # fomc command (FOMC statements, minutes, sentiment)
    fc_parser = subparsers.add_parser("fomc", help="FOMC statements, minutes, and sentiment analysis")
    fc_sub = fc_parser.add_subparsers(dest="subcommand", help="FOMC subcommand")

    # fomc calendar
    fc_sub.add_parser("calendar", help="Show FOMC meeting calendar (2022-2027)")

    # fomc statement
    fc_stmt = fc_sub.add_parser("statement", help="Fetch latest (or specific) FOMC statement")
    fc_stmt.add_argument("date", nargs="?", default=None,
                          help="Meeting date YYYY-MM-DD (default: most recent)")
    fc_stmt.add_argument("--json", action="store_true", help="Output as JSON")

    # fomc minutes
    fc_min = fc_sub.add_parser("minutes", help="Fetch latest (or specific) FOMC minutes")
    fc_min.add_argument("date", nargs="?", default=None,
                         help="Meeting date YYYY-MM-DD (default: most recent with minutes)")
    fc_min.add_argument("--full", action="store_true", help="Show full text (default: truncated)")
    fc_min.add_argument("--json", action="store_true", help="Output as JSON")

    # fomc sentiment
    fc_sub.add_parser("sentiment", help="Compare sentiment between last two FOMC statements")

    # fomc odds (Polymarket-implied probabilities)
    from .fomc_odds import register as _register_odds
    _register_odds(fc_sub)

    # full-market scan (Yahoo server-side screener engine)
    from .market_scan import register as _register_scan
    _register_scan(subparsers)

    # insider command (SEC EDGAR Form 4)
    in_parser = subparsers.add_parser("insider", help="Insider trading from SEC EDGAR Form 4 filings")
    in_sub = in_parser.add_subparsers(dest="insider_cmd")

    in_scan = in_sub.add_parser("scan", help="Scan open-market insider buys/sells for tickers")
    in_scan.add_argument("--tickers", type=str, default=None,
                         help="Comma-separated tickers (default: ~/.config/finresearch/watchlist.txt)")
    in_scan.add_argument("--days", type=int, default=7, help="Lookback days (default: 7)")
    in_scan.add_argument("--min-value", type=float, default=None,
                         help="Min transaction value in $ (e.g. 100000)")
    in_scan.add_argument("--json", action="store_true", help="Output as JSON")

    in_detail = in_sub.add_parser("detail", help="All Form 4 transactions for one ticker")
    in_detail.add_argument("ticker", help="Ticker symbol (e.g. META)")
    in_detail.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    in_detail.add_argument("--json", action="store_true", help="Output as JSON")

    # 13f command (institutional holdings via SEC Form 13F-HR)
    tf_parser = subparsers.add_parser("13f", help="Institutional holdings (SEC Form 13F-HR)")
    tf_sub = tf_parser.add_subparsers(dest="subcommand")

    tf_holder = tf_sub.add_parser("holder", help="One filer's latest holdings")
    tf_holder.add_argument("holder", help="Filer ticker (e.g. BRK-B) or 10-digit CIK")
    tf_holder.add_argument("--top", type=int, default=15,
                           help="Show top N positions by reported value (default: 15)")
    tf_holder.add_argument("--json", action="store_true", help="Output as JSON")

    tf_who = tf_sub.add_parser("who", help="Which 13F filers hold an issuer")
    tf_who.add_argument("issuer_words", nargs="+", help="Issuer name words, e.g.: NVIDIA CORP")
    tf_who.add_argument("--limit", type=int, default=25, help="Max filers shown (default: 25)")

    tf_diff = tf_sub.add_parser("diff", help="Quarter-over-quarter adds/drops for an issuer")
    tf_diff.add_argument("issuer_words", nargs="+", help="Issuer name words, e.g.: NOKIA CORP")
    tf_diff.add_argument("--limit", type=int, default=15, help="Max filers analyzed (default: 15)")
    tf_diff.add_argument("--min-shares", type=int, default=None,
                         help="Ignore positions below this share count")

    # activist command (SC 13D/G)
    ac_parser = subparsers.add_parser("activist", help="SC 13D/G stakes (SEC EDGAR)")
    ac_parser.add_argument("tickers", help="Comma-separated tickers (e.g. NOK,INTC)")
    ac_parser.add_argument("--days", type=int, default=400, help="Lookback days (default: 400)")
    ac_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # dilution command (S-3 / 424B)
    dl_parser = subparsers.add_parser("dilution", help="Shelf + offering pipeline (S-3/424B)")
    dl_parser.add_argument("tickers", help="Comma-separated tickers")
    dl_parser.add_argument("--days", type=int, default=365, help="Lookback days (default: 365)")
    dl_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # buyback command
    bb_parser = subparsers.add_parser("buyback", help="Repurchase programs + XBRL spend")
    bb_parser.add_argument("tickers", help="Comma-separated tickers")
    bb_parser.add_argument("--days", type=int, default=400, help="8-K lookback days (default: 400)")
    bb_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # 8k command
    ek_parser = subparsers.add_parser("8k", help="Recent 8-K events by item code")
    ek_parser.add_argument("tickers", help="Comma-separated tickers")
    ek_parser.add_argument("--days", type=int, default=60, help="Lookback days (default: 60)")
    ek_parser.add_argument("--has", type=str, default=None,
                           help="Only filings containing these items, e.g. 2.02,4.02")
    ek_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # options command (yfinance chains)
    op_parser = subparsers.add_parser("options", help="Unusual options activity + P/C ratios")
    op_parser.add_argument("ticker", help="Ticker symbol")
    op_parser.add_argument("--vol-oi", type=float, default=1.0,
                           help="Volume/OI threshold for 'unusual' (default: 1.0)")
    op_parser.add_argument("--min-volume", type=int, default=100,
                           help="Minimum option volume (default: 100)")
    op_parser.add_argument("--expiries", type=int, default=2,
                           help="Front expiries to scan (default: 2)")
    op_parser.add_argument("--top", type=int, default=12, help="Strikes shown (default: 12)")
    op_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # ftd command (SEC fails-to-deliver)
    ft_parser = subparsers.add_parser("ftd", help="SEC Fails-to-Deliver aggregates")
    ft_sub = ft_parser.add_subparsers(dest="ftd_cmd")
    ft_top = ft_sub.add_parser("top", help="Largest fails in the latest file")
    ft_top.add_argument("--top", type=int, default=15, help="Symbols shown (default: 15)")
    ft_top.add_argument("--by", choices=["value", "quantity"], default="value",
                        help="Rank by fails$ or share count (default: value)")
    ft_top.add_argument("--min-quantity", type=int, default=None,
                        help="Ignore rows below this fail quantity")
    ft_top.add_argument("--json", action="store_true", help="Output as JSON")
    ft_sym = ft_sub.add_parser("sym", help="One symbol's fails history")
    ft_sym.add_argument("symbol", help="Ticker symbol (e.g. GME)")
    ft_sym.add_argument("--files", type=int, default=3,
                        help="Number of recent FTD files (default: 3)")
    ft_sym.add_argument("--json", action="store_true", help="Output as JSON")

    # short command (FINRA short interest)
    sh_parser = subparsers.add_parser("short", help="FINRA consolidated short interest")
    sh_parser.add_argument("--by", choices=["dtc", "si"], default="dtc",
                           help="Rank by days-to-cover or short interest (default: dtc)")
    sh_parser.add_argument("--top", type=int, default=15, help="Symbols shown (default: 15)")
    sh_parser.add_argument("--limit", type=int, default=1000, help="Rows parsed (default: 1000)")
    sh_parser.add_argument("--min-si", type=int, default=None,
                           help="Minimum short interest")
    sh_parser.add_argument("--settlement", type=str, default=None,
                           help="Settlement date YYYY-MM-DD (keyed API)")
    sh_parser.add_argument("--free", action="store_true",
                           help="Force the free keyless historical slice")
    sh_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # subcommand families with no default action print their own help
    family_parsers = {"insider": (in_parser, "insider_cmd"), "13f": (tf_parser, "subcommand"),
                      "ftd": (ft_parser, "ftd_cmd")}
    if args.command in family_parsers:
        fam_parser, dest = family_parsers[args.command]
        if not getattr(args, dest, None):
            fam_parser.print_help()
            sys.exit(1)

    if args.command not in COMMANDS:
        parser.print_help()
        sys.exit(1)
    module, handler = COMMANDS[args.command]
    getattr(importlib.import_module(f".{module}", __package__), handler)(args)


if __name__ == "__main__":
    main()
