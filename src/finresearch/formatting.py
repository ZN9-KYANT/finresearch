"""Formatting helpers for financial data output."""

BILLION = 1_000_000_000
MILLION = 1_000_000
TRILLION = 1_000_000_000_000

CURRENCY_SYMBOLS = {"USD": "$", "JPY": "¥", "EUR": "€", "GBP": "£",
                    "GBp": "£", "ILS": "₪", "KRW": "₩", "CAD": "C$",
                    "AUD": "A$", "CHF": "CHF ", "HKD": "HK$", "INR": "₹"}


def _symbol_for(unit):
    """Currency code -> symbol (unknown code -> code + space)."""
    if unit in (None, "USD"):
        return "$"
    if unit in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[unit]
    return f"{unit} "


def fmt_num(val, unit="USD"):
    """Format large numbers with a currency/units prefix.

    unit: 'USD' (default), any Yahoo currency code ('JPY', 'EUR', ...),
    'USD/shares' / 'JPY/shares' style for per-share values, or 'shares'.
    """
    if val is None or (isinstance(val, float) and val != val):  # NaN check
        return "N/A"
    if isinstance(val, str):
        return val
    if unit == "shares":
        if abs(val) >= BILLION:
            return f"{val/BILLION:.2f}B"
        if abs(val) >= MILLION:
            return f"{val/MILLION:.1f}M"
        return f"{val:,.0f}"
    if unit and "/shares" in unit:
        sym = _symbol_for(unit.split("/")[0])
        return f"{sym}{val:,.2f}"
    sym = _symbol_for(unit)
    if abs(val) >= TRILLION:
        return f"{sym}{val/TRILLION:.2f}T"
    if abs(val) >= BILLION:
        return f"{sym}{val/BILLION:.2f}B"
    if abs(val) >= MILLION:
        return f"{sym}{val/MILLION:.1f}M"
    if abs(val) >= 1:
        return f"{sym}{val:,.0f}"
    return f"{sym}{val:.4f}"


def fmt_pct(val, percent_units=False):
    """Format a ratio as a percentage.

    Default: val is a FRACTION (0.115 -> 11.5%, 1.49 -> 149.0%) — Yahoo margins,
    growth, ROE, payout, holder %. percent_units=True: val is already in
    percent points (Yahoo dividendYield, screener regularMarketChangePercent).
    Units are explicit by design: guessing from magnitude mislabels ratios at
    or above 100% and moves under 1%.
    """
    if val is None or isinstance(val, str) or (isinstance(val, float) and val != val):
        return "N/A"
    return f"{val:.1f}%" if percent_units else f"{val * 100:.1f}%"


def fmt_date(dt):
    """Format datetime to YYYY-MM-DD."""
    if dt is None:
        return "N/A"
    return str(dt)[:10]


def fmt_shares(val):
    """Plain comma formatting for share counts (NOT currency)."""
    if val is None:
        return "-"
    try:
        n = float(str(val).replace(",", ""))
    except (TypeError, ValueError):
        return str(val)
    if n != n:  # NaN
        return "-"
    return f"{int(n):,}" if n == int(n) else f"{n:,.4f}".rstrip("0").rstrip(".")


def print_table(headers, rows, title=None):
    """Print a formatted markdown table."""
    if title:
        print(f"\n## {title}\n")
    if not rows:
        print("*No data available*\n")
        return
    col_widths = [
        max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]
    header_line = "| " + " | ".join(str(h).ljust(w) for h, w in zip(headers, col_widths)) + " |"
    sep_line = "| " + " | ".join("-" * w for w in col_widths) + " |"
    print(header_line)
    print(sep_line)
    for row in rows:
        row_line = "| " + " | ".join(str(r).ljust(w) for r, w in zip(row, col_widths)) + " |"
        print(row_line)
