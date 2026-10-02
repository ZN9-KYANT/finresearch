"""Technical indicators for ticker data — RSI, MACD, Bollinger Bands, S/R levels.

Uses yfinance history data (no external deps beyond yfinance + pandas).
"""

import numpy as np
import pandas as pd

from .formatting import fmt_num, print_table


def _compute_rsi(series, period=14):
    """Compute RSI (Relative Strength Index) for a price series."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    # Wilder's smoothing
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if len(rsi) > 0 else None


def _compute_macd(series, fast=12, slow=26, signal=9):
    """Compute MACD line, signal line, and histogram."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]


def _compute_bollinger(series, period=20, std_dev=2):
    """Compute Bollinger Bands."""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper.iloc[-1], sma.iloc[-1], lower.iloc[-1]


def _find_support_resistance(high, low, close, window=20):
    """Find recent support and resistance levels using local extrema."""
    # Use recent window of data
    recent_high = high.tail(window)
    recent_low = low.tail(window)
    current = close.iloc[-1]

    # Simple approach: find recent swing highs and lows
    resistance = recent_high.max()
    support = recent_low.min()

    # Find the nearest resistance above and support below
    highs_above = recent_high[recent_high > current]
    lows_below = recent_low[recent_low < current]

    if len(highs_above) > 0:
        resistance = highs_above.min()  # Nearest resistance above
    if len(lows_below) > 0:
        support = lows_below.max()  # Nearest support below

    return support, resistance


def _compute_atr(high, low, close, period=14):
    """Compute Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr.iloc[-1] if len(atr) > period else None


def compute_technicals(ticker_obj, json_output=False):
    """Compute all technical indicators for a yfinance Ticker object.

    Returns dict (for JSON) or prints tables (for markdown).
    """
    # 1y of daily bars: a true 52-week range and a computable 200-day MA
    hist = ticker_obj.history(period="1y")
    if hist is None or len(hist) < 30:
        if json_output:
            return {"error": "Insufficient history data (< 30 bars)"}
        print("\n## Technicals\n\n*Insufficient history data (< 30 bars)*\n")
        return None

    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]
    volume = hist["Volume"]
    current = close.iloc[-1]
    try:  # listing currency (JP tickers: JPY); info is cached on the Ticker
        cur = ticker_obj.info.get("currency") or "USD"
    except Exception:
        cur = "USD"

    # RSI
    rsi = _compute_rsi(close, 14)

    # MACD
    macd_line, signal_line, histogram = _compute_macd(close)

    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = _compute_bollinger(close, 20, 2)

    # Support/Resistance
    support, resistance = _find_support_resistance(high, low, close, 20)

    # ATR
    atr = _compute_atr(high, low, close, 14)

    # Moving averages
    ma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
    ma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
    ma_20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
    if ma_200 is None:
        # a young listing (< 200 bars) can't fill the window; Yahoo's own
        # 200d average is the right fallback
        try:
            ma_200 = ticker_obj.info.get("twoHundredDayAverage")
        except Exception:
            ma_200 = None

    # Volume trend
    vol_avg_20 = volume.rolling(20).mean().iloc[-1] if len(volume) >= 20 else None
    current_vol = volume.iloc[-1]

    # 52-week range position
    high_52w = high.max()
    low_52w = low.min()
    range_position = ((current - low_52w) / (high_52w - low_52w) * 100) if high_52w != low_52w else 50

    # Price change
    pct_1d = ((current - close.iloc[-2]) / close.iloc[-2] * 100) if len(close) >= 2 else None
    pct_1w = ((current - close.iloc[-6]) / close.iloc[-6] * 100) if len(close) >= 6 else None
    pct_1m = ((current - close.iloc[-22]) / close.iloc[-22] * 100) if len(close) >= 22 else None

    # Signals
    signals = []
    if rsi is not None:
        if rsi > 70:
            signals.append("🔴 RSI >70: Overbought")
        elif rsi < 30:
            signals.append("🟢 RSI <30: Oversold")
        elif rsi > 55:
            signals.append("🟡 RSI bullish zone (55-70)")
        elif rsi < 45:
            signals.append("🟡 RSI bearish zone (30-45)")
    if ma_50 and ma_200:
        if ma_50 > ma_200:
            signals.append("🟢 Golden cross (50d > 200d)")
        else:
            signals.append("🔴 Death cross (50d < 200d)")
    if current > bb_upper:
        signals.append("🟡 Price above upper Bollinger Band (extended)")
    elif current < bb_lower:
        signals.append("🟡 Price below lower Bollinger Band (oversold)")
    if macd_line > signal_line:
        signals.append("🟢 MACD bullish (MACD > signal)")
    else:
        signals.append("🔴 MACD bearish (MACD < signal)")

    if json_output:
        return {
            "current_price": round(current, 2),
            "rsi_14": round(rsi, 1) if rsi and not np.isnan(rsi) else None,
            "macd": {
                "macd_line": round(macd_line, 4) if macd_line and not np.isnan(macd_line) else None,
                "signal_line": round(signal_line, 4) if signal_line and not np.isnan(signal_line) else None,
                "histogram": round(histogram, 4) if histogram and not np.isnan(histogram) else None,
            },
            "bollinger": {
                "upper": round(bb_upper, 2) if bb_upper and not np.isnan(bb_upper) else None,
                "middle": round(bb_middle, 2) if bb_middle and not np.isnan(bb_middle) else None,
                "lower": round(bb_lower, 2) if bb_lower and not np.isnan(bb_lower) else None,
            },
            "support": round(support, 2) if support and not np.isnan(support) else None,
            "resistance": round(resistance, 2) if resistance and not np.isnan(resistance) else None,
            "atr_14": round(atr, 2) if atr and not np.isnan(atr) else None,
            "moving_averages": {
                "ma_20": round(ma_20, 2) if ma_20 and not np.isnan(ma_20) else None,
                "ma_50": round(ma_50, 2) if ma_50 and not np.isnan(ma_50) else None,
                "ma_200": round(ma_200, 2) if ma_200 and not np.isnan(ma_200) else None,
            },
            "price_changes": {
                "1d_pct": round(pct_1d, 2) if pct_1d is not None else None,
                "1w_pct": round(pct_1w, 2) if pct_1w is not None else None,
                "1m_pct": round(pct_1m, 2) if pct_1m is not None else None,
            },
            "range_52w": {
                "high": round(high_52w, 2),
                "low": round(low_52w, 2),
                "position_pct": round(range_position, 1),
            },
            "volume": {
                "current": int(current_vol),
                "avg_20d": int(vol_avg_20) if vol_avg_20 and not np.isnan(vol_avg_20) else None,
            },
            "signals": signals,
        }

    # Markdown output
    print_table(
        ["Metric", "Value", "Signal"],
        [
            ["RSI (14)", f"{rsi:.1f}" if rsi and not np.isnan(rsi) else "N/A",
             "Overbought >70" if rsi and rsi > 70 else ("Oversold <30" if rsi and rsi < 30 else "Neutral")],
            ["MACD Line", f"{macd_line:.4f}" if macd_line and not np.isnan(macd_line) else "N/A", ""],
            ["Signal Line", f"{signal_line:.4f}" if signal_line and not np.isnan(signal_line) else "N/A", ""],
            ["MACD Hist", f"{histogram:.4f}" if histogram and not np.isnan(histogram) else "N/A",
             "🟢 Bullish" if histogram and histogram > 0 else "🔴 Bearish"],
        ],
        title="Momentum Indicators",
    )

    print_table(
        ["Metric", "Value"],
        [
            ["BB Upper (20,2)", fmt_num(bb_upper, cur)],
            ["BB Middle (20)", fmt_num(bb_middle, cur)],
            ["BB Lower (20,2)", fmt_num(bb_lower, cur)],
            ["ATR (14)", fmt_num(atr, cur)],
        ],
        title="Volatility",
    )

    print_table(
        ["Level", "Value", "vs Current"],
        [
            ["Resistance", fmt_num(resistance, cur), f"+{((resistance - current) / current * 100):.1f}%" if resistance and current else "N/A"],
            ["Current Price", fmt_num(current, cur), "—"],
            ["Support", fmt_num(support, cur), f"{((support - current) / current * 100):.1f}%" if support and current else "N/A"],
        ],
        title="Support / Resistance (20-bar)",
    )

    print_table(
        ["MA", "Value", "Trend"],
        [
            ["20-day", fmt_num(ma_20, cur), "Above ↑" if ma_20 and current > ma_20 else ("Below ↓" if ma_20 else "N/A")],
            ["50-day", fmt_num(ma_50, cur), "Above ↑" if ma_50 and current > ma_50 else ("Below ↓" if ma_50 else "N/A")],
            ["200-day", fmt_num(ma_200, cur), "Above ↑" if ma_200 and current > ma_200 else ("Below ↓" if ma_200 else "N/A")],
        ],
        title="Moving Averages",
    )

    print_table(
        ["Period", "Change %"],
        [
            ["1 Day", f"{pct_1d:+.2f}%" if pct_1d is not None else "N/A"],
            ["1 Week", f"{pct_1w:+.2f}%" if pct_1w is not None else "N/A"],
            ["1 Month", f"{pct_1m:+.2f}%" if pct_1m is not None else "N/A"],
        ],
        title="Price Changes",
    )

    print_table(
        ["Metric", "Value"],
        [
            ["52w High", fmt_num(high_52w, cur)],
            ["52w Low", fmt_num(low_52w, cur)],
            ["Range Position", f"{range_position:.1f}%"],
            ["Current Volume", fmt_num(int(current_vol), "shares")],
            ["Avg Volume (20d)", fmt_num(int(vol_avg_20), "shares") if vol_avg_20 and not np.isnan(vol_avg_20) else "N/A"],
        ],
        title="Range & Volume",
    )

    if signals:
        print("\n## Signals\n")
        for s in signals:
            print(f"- {s}")
