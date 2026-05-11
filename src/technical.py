"""
CSP Scanner V1.5 - Technical Analysis Module
Keltner Channel + RSI + Support Detection + Gap Detection

Changes from V1.0:
- KC range subdivision: upper half (mid-to-top) and lower half (mid-to-bottom)
- Prior candle top as support level
- Gap detection (unfilled gaps = strike targets)
- Multi-tap support counting (3+ taps = elevated trust)
- Resistance breakout = permanent support floor
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from typing import Optional
from config import (
    KC_EMA_PERIOD, KC_ATR_PERIOD, KC_MULTIPLIER,
    RSI_PERIOD, RSI_OVERSOLD, RSI_VERY_OVERSOLD, RSI_OVERBOUGHT, RSI_VERY_OVERBOUGHT,
    KC_BOTTOM_ZONE, KC_MID_ZONE, KC_DANGER_ZONE,
    SUPPORT_LOOKBACK_DAYS, KC_PROXIMITY_THRESHOLD,
)


def fetch_price_data(ticker, period="6mo", interval="1d"):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval)
        if df.empty:
            return None
        return df
    except Exception as e:
        print(f"  [ERROR] Fetching {ticker}: {e}")
        return None


def calculate_keltner_channel(df):
    df["kc_mid"] = df["Close"].ewm(span=KC_EMA_PERIOD, adjust=False).mean()
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(window=KC_ATR_PERIOD).mean()
    df["kc_upper"] = df["kc_mid"] + (KC_MULTIPLIER * df["atr"])
    df["kc_lower"] = df["kc_mid"] - (KC_MULTIPLIER * df["atr"])
    channel_width = df["kc_upper"] - df["kc_lower"]
    df["kc_position"] = (df["Close"] - df["kc_lower"]) / channel_width
    return df


def calculate_rsi(df, period=RSI_PERIOD):
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


def classify_sandbox_zone(kc_position):
    if kc_position <= 0:
        return "BELOW_KC"
    elif kc_position <= KC_BOTTOM_ZONE:
        return "KC_BOTTOM"
    elif kc_position <= KC_MID_ZONE:
        return "KC_MIDDLE"
    elif kc_position <= KC_DANGER_ZONE:
        return "KC_UPPER"
    else:
        return "DANGER_ZONE"


def classify_kc_half(kc_position):
    """
    V1.5: KC range subdivision.
    JohnG: "Once a stock is in and around its mid, we break it up.
    New top line, new bottom line, and the mid acts as the center."

    Upper half (mid to top): strike target = KC mid
    Lower half (bottom to mid): strike target = KC bottom
    """
    if kc_position <= 0:
        return "BELOW_CHANNEL"
    elif kc_position <= 0.5:
        return "LOWER_HALF"
    else:
        return "UPPER_HALF"


def classify_rsi(rsi):
    if rsi <= RSI_VERY_OVERSOLD:
        return "VERY_OVERSOLD"
    elif rsi <= RSI_OVERSOLD:
        return "OVERSOLD"
    elif rsi >= RSI_VERY_OVERBOUGHT:
        return "VERY_OVERBOUGHT"
    elif rsi >= RSI_OVERBOUGHT:
        return "OVERBOUGHT"
    else:
        return "NEUTRAL"


def find_support_levels(df, lookback_days=SUPPORT_LOOKBACK_DAYS):
    """Enhanced support detection with multi-tap counting and resistance-turned-support."""
    if len(df) < lookback_days:
        lookback_days = len(df)

    recent = df.tail(lookback_days).copy()
    lows = recent["Low"].values
    highs = recent["High"].values
    supports = []

    # Method 1: Pivot lows
    window = 5
    for i in range(window, len(lows) - window):
        if lows[i] == min(lows[i - window:i + window + 1]):
            supports.append({
                "price": round(float(lows[i]), 2),
                "date": recent.index[i].strftime("%Y-%m-%d"),
                "strength": 1,
                "type": "pivot_low",
                "taps": 1,
            })

    # Method 2: Resistance-turned-support
    for i in range(window, len(highs) - window * 2):
        if highs[i] == max(highs[i - window:i + window + 1]):
            resistance_level = float(highs[i])
            future_lows = lows[i + window:]
            for fl in future_lows:
                if abs(fl - resistance_level) / resistance_level < 0.02:
                    supports.append({
                        "price": round(resistance_level, 2),
                        "date": recent.index[i].strftime("%Y-%m-%d"),
                        "strength": 2,
                        "type": "resistance_turned_support",
                        "taps": 1,
                    })
                    break

    # Method 3: Prior candle top as support (V1.5)
    # JohnG: "I'm thinking if it's going to peel back, it's going to find
    # itself at the top of this candle right here"
    candle_tops = find_candle_top_supports(recent)
    supports.extend(candle_tops)

    # Merge nearby levels and count multi-taps
    merged = merge_and_count_taps(supports, recent)

    merged.sort(key=lambda x: x["strength"], reverse=True)
    return merged[:8]


def find_candle_top_supports(df):
    """
    V1.5: Find tops of significant prior candles as support levels.
    JohnG uses the high of reversal candles as targets.
    """
    supports = []
    closes = df["Close"].values
    highs = df["High"].values
    opens = df["Open"].values

    for i in range(2, len(df) - 2):
        # Look for significant green candles followed by a red candle
        body = closes[i] - opens[i]
        body_pct = abs(body) / closes[i] * 100 if closes[i] > 0 else 0

        is_green = closes[i] > opens[i]
        followed_by_red = i + 1 < len(closes) and closes[i + 1] < opens[i + 1]

        if is_green and body_pct >= 2.0 and followed_by_red:
            supports.append({
                "price": round(float(highs[i]), 2),
                "date": df.index[i].strftime("%Y-%m-%d"),
                "strength": 1,
                "type": "candle_top",
                "taps": 1,
            })

    return supports


def merge_and_count_taps(supports, df):
    """
    Merge nearby support levels and count how many times price has tested them.
    V1.5: Multi-tap counting. JohnG trusts levels tested 3+ times more.
    "One, two, three, four, five times it's tapped the 33 strike."
    """
    if not supports:
        return []

    lows = df["Low"].values

    # Sort by price
    sorted_supports = sorted(supports, key=lambda x: x["price"])

    merged = []
    for s in sorted_supports:
        if merged and abs(s["price"] - merged[-1]["price"]) / merged[-1]["price"] < 0.02:
            merged[-1]["strength"] += s["strength"]
            merged[-1]["price"] = round((merged[-1]["price"] + s["price"]) / 2, 2)
            if s["type"] == "resistance_turned_support":
                merged[-1]["type"] = "resistance_turned_support"
        else:
            merged.append(s.copy())

    # Count taps: how many times price has touched this level (within 1.5%)
    for level in merged:
        tap_count = 0
        for low in lows:
            if abs(low - level["price"]) / level["price"] < 0.015:
                tap_count += 1
        level["taps"] = max(tap_count, 1)

        # Boost strength for multi-tap levels
        if tap_count >= 5:
            level["strength"] += 4
        elif tap_count >= 3:
            level["strength"] += 2
        elif tap_count >= 2:
            level["strength"] += 1

    return merged


def detect_gaps(df, min_gap_pct=1.0):
    """
    V1.5: Detect unfilled price gaps.
    JohnG: "It would fill this gap right here. That would put you in and around 29.27."

    A gap up: today's low > yesterday's high (unfilled if price hasn't come back)
    A gap down: today's high < yesterday's low
    Returns unfilled gaps as potential strike targets.
    """
    gaps = []
    closes = df["Close"].values
    highs = df["High"].values
    lows = df["Low"].values
    opens = df["Open"].values

    for i in range(1, len(df)):
        # Gap up: today's low is above yesterday's high
        if lows[i] > highs[i - 1]:
            gap_size = lows[i] - highs[i - 1]
            gap_pct = (gap_size / highs[i - 1]) * 100

            if gap_pct >= min_gap_pct:
                gap_bottom = round(float(highs[i - 1]), 2)
                gap_top = round(float(lows[i]), 2)

                # Check if gap has been filled (price came back to gap_bottom)
                filled = False
                for j in range(i + 1, len(df)):
                    if lows[j] <= gap_bottom:
                        filled = True
                        break

                if not filled:
                    gaps.append({
                        "type": "gap_up",
                        "gap_bottom": gap_bottom,
                        "gap_top": gap_top,
                        "gap_pct": round(gap_pct, 2),
                        "date": df.index[i].strftime("%Y-%m-%d"),
                        "filled": False,
                        "strike_target": gap_bottom,
                    })

        # Gap down: today's high is below yesterday's low
        if highs[i] < lows[i - 1]:
            gap_size = lows[i - 1] - highs[i]
            gap_pct = (gap_size / lows[i - 1]) * 100

            if gap_pct >= min_gap_pct:
                gap_bottom = round(float(highs[i]), 2)
                gap_top = round(float(lows[i - 1]), 2)

                filled = False
                for j in range(i + 1, len(df)):
                    if highs[j] >= gap_top:
                        filled = True
                        break

                if not filled:
                    gaps.append({
                        "type": "gap_down",
                        "gap_bottom": gap_bottom,
                        "gap_top": gap_top,
                        "gap_pct": round(gap_pct, 2),
                        "date": df.index[i].strftime("%Y-%m-%d"),
                        "filled": False,
                        "strike_target": gap_top,
                    })

    return gaps[-5:]  # Return last 5 unfilled gaps


def check_has_weekly_options(ticker):
    """
    V1.5: Check if a ticker has weekly options or monthly only.
    JohnG: "They only have monthly cash secure puts. So, we lead in
    two weeks into the expiration."

    For monthly-only tickers, also identifies the optimal entry window
    (14 days before expiration).
    """
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations or len(expirations) < 2:
            return False, expirations or [], None

        from datetime import datetime, timedelta
        today = datetime.now().date()
        dates = [datetime.strptime(e, "%Y-%m-%d").date() for e in expirations]

        # Filter to next 60 days
        near_term = [d for d in dates if 0 < (d - today).days <= 60]

        if len(near_term) < 3:
            # Monthly only: find the ideal 14-day lead-in window
            lead_in = None
            for d in near_term:
                dte = (d - today).days
                if 10 <= dte <= 18:
                    lead_in = {
                        "expiration": d.strftime("%Y-%m-%d"),
                        "dte": dte,
                        "in_window": True,
                        "note": f"Monthly-only. Ideal entry window: {dte} days to expiration.",
                    }
                    break
            if lead_in is None and near_term:
                closest = near_term[0]
                dte = (closest - today).days
                lead_in = {
                    "expiration": closest.strftime("%Y-%m-%d"),
                    "dte": dte,
                    "in_window": 10 <= dte <= 18,
                    "note": f"Monthly-only. Next expiration: {dte} days. {'In window.' if 10 <= dte <= 18 else 'Outside ideal 10-18 day window.'}",
                }
            return False, expirations, lead_in

        # Check if there are expirations within 7 days of each other
        for i in range(1, len(near_term)):
            gap = (near_term[i] - near_term[i - 1]).days
            if gap <= 8:
                return True, expirations, None  # Has weeklies

        return False, expirations, None  # Monthly only

    except Exception:
        return True, [], None  # Assume weekly if can't check


def detect_down_day(df):
    """V1.5: Check if today is a down day (red candle = juicier put premiums)."""
    if len(df) < 1:
        return False, 0
    latest = df.iloc[-1]
    is_down = float(latest["Close"]) < float(latest["Open"])
    change_pct = ((float(latest["Close"]) - float(latest["Open"])) / float(latest["Open"])) * 100
    return is_down, round(change_pct, 2)


def analyze_ticker(ticker):
    df = fetch_price_data(ticker)
    if df is None or len(df) < KC_EMA_PERIOD + KC_ATR_PERIOD:
        return None

    df = calculate_keltner_channel(df)
    df = calculate_rsi(df)
    supports = find_support_levels(df)
    gaps = detect_gaps(df)
    has_weekly, expirations, monthly_lead_in = check_has_weekly_options(ticker)
    is_down_day, day_change_pct = detect_down_day(df)

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    current_price = float(latest["Close"])
    kc_lower = float(latest["kc_lower"])
    kc_mid = float(latest["kc_mid"])
    kc_upper = float(latest["kc_upper"])
    kc_position = float(latest["kc_position"])
    rsi = float(latest["rsi"]) if pd.notna(latest["rsi"]) else 50.0

    distance_to_kc_bottom = (current_price - kc_lower) / current_price
    near_kc_bottom = distance_to_kc_bottom <= KC_PROXIMITY_THRESHOLD

    sandbox_zone = classify_sandbox_zone(kc_position)
    kc_half = classify_kc_half(kc_position)
    rsi_zone = classify_rsi(rsi)

    in_danger_zone = sandbox_zone == "DANGER_ZONE"
    rsi_reject = rsi_zone in ("OVERBOUGHT", "VERY_OVERBOUGHT")
    trending_down = float(prev["kc_position"]) > kc_position

    # V1.5: Determine strike target based on KC half
    if kc_half == "UPPER_HALF":
        kc_strike_target = round(kc_mid, 2)
        kc_strike_note = "Upper half: target KC mid"
    elif kc_half == "LOWER_HALF":
        kc_strike_target = round(kc_lower, 2)
        kc_strike_note = "Lower half: target KC bottom"
    else:
        kc_strike_target = round(kc_lower, 2)
        kc_strike_note = "Below channel: at KC bottom"

    nearest_support = None
    for s in supports:
        if s["price"] <= current_price:
            nearest_support = s
            break

    # Find multi-tap levels (3+ taps)
    multi_tap_levels = [s for s in supports if s.get("taps", 0) >= 3]

    # Find gap-based strike targets
    gap_strikes = [g["strike_target"] for g in gaps if g["strike_target"] < current_price]

    return {
        "ticker": ticker,
        "current_price": round(current_price, 2),
        "kc_lower": round(kc_lower, 2),
        "kc_mid": round(kc_mid, 2),
        "kc_upper": round(kc_upper, 2),
        "kc_position": round(kc_position, 4),
        "sandbox_zone": sandbox_zone,
        "kc_half": kc_half,
        "kc_strike_target": kc_strike_target,
        "kc_strike_note": kc_strike_note,
        "distance_to_kc_bottom_pct": round(distance_to_kc_bottom * 100, 2),
        "near_kc_bottom": near_kc_bottom,
        "in_danger_zone": in_danger_zone,
        "rsi": round(rsi, 1),
        "rsi_zone": rsi_zone,
        "rsi_reject": rsi_reject,
        "trending_down": trending_down,
        "support_levels": supports,
        "nearest_support": nearest_support,
        "multi_tap_levels": multi_tap_levels,
        "gaps": gaps,
        "gap_strikes": gap_strikes,
        "has_weekly_options": has_weekly,
        "monthly_lead_in": monthly_lead_in,
        "is_down_day": is_down_day,
        "day_change_pct": day_change_pct,
        "atr": round(float(latest["atr"]), 2),
        "timestamp": datetime.now().isoformat(),
        "version": "1.5",
    }


def screen_all_tickers(watchlist):
    results = []
    for ticker in watchlist:
        print(f"  Analyzing {ticker}...")
        analysis = analyze_ticker(ticker)
        if analysis:
            results.append(analysis)
    return results
