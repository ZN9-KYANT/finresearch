"""Financial Research Toolkit — Free alternative to financialdatasets.ai."""

__version__ = "1.1.0"

# Public helpers resolve lazily (PEP 562) so `import finresearch` stays cheap:
# the CLI must not pay for pandas/yfinance on commands that never touch them.
_EXPORTS = {
    "cmd_compare": "yfinance_cmd",
    "cmd_ticker": "yfinance_cmd",
    "cmd_sec": "sec_edgar",
    "find_cik": "sec_edgar",
    "cmd_transcript": "transcript",
    "fmt_date": "formatting",
    "fmt_num": "formatting",
    "fmt_pct": "formatting",
    "print_table": "formatting",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    if name in _EXPORTS:
        import importlib
        return getattr(importlib.import_module(f".{_EXPORTS[name]}", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
