"""
CSP Scanner V1.5 - Scoring Engine
Changes from V1.0:
- Expected move validation (1 SD check on every strike)
- Down-day bonus for CSP scoring
- Short-term KC top exception (8-day trades with heavy protection)
- CoC% sweet spot warnings
- Trade checklist (3 checkboxes, A-F grade)
"""

import math
from config import SCORE_WEIGHTS, WATCHLIST


def expected_move(price, iv, dte):
    """Calculate expected 1 SD move. JohnG's core strike selection tool."""
    if dte <= 0 or iv <= 0 or price <= 0:
        return 0
    return price * iv * math.sqrt(dte / 365)


def validate_strike_vs_expected_move(price, strike, iv, dte):
    """
    Check if strike is within or beyond the expected downside move.
    SAFE = beyond 1 SD, MODERATE = near 1 SD, AGGRESSIVE = within expected move.
    """
    move = expected_move(price, iv, dte)
    downside_1sd = price - move

    if strike <= downside_1sd * 0.98:
        return "VERY_SAFE", downside_1sd
    elif strike <= downside_1sd:
        return "SAFE", downside_1sd
    elif strike <= downside_1sd * 1.03:
        return "MODERATE", downside_1sd
    else:
        return "AGGRESSIVE", downside_1sd


def coc_sweet_spot(coc_pct, dte_class):
    """
    V2.0 CORRECTED from 37 real email trades:
    Real CoC% range: 1.17% to 5.59% (excluding outliers MSTX 17.75% and SMCX 11.88%)
    Real center of gravity: 2.0-2.5% weekly
    Real average: 2.46% weekly across typical trades
    JohnG targets 1.7-1.8% as a floor but real trades cluster around 2.0-2.5%.
    He goes 3.5-5.6% on higher-IV tickers (SOXL, DPST, LABU) in favorable conditions.
    Anything above 5% on a weekly is AGGRESSIVE (strike too close to current price).
    """
    if dte_class == "weekly":
        if coc_pct < 1.0:
            return "TOO_LOW"
        elif coc_pct < 1.2:
            return "FLOOR"          # Absolute minimum
        elif coc_pct <= 1.7:
            return "LOW_SWEET"      # Acceptable, conservative
        elif coc_pct <= 2.5:
            return "SWEET_SPOT"     # Real-world center (2.0-2.5% confirmed from 37 trades)
        elif coc_pct <= 4.0:
            return "GOOD"           # Above average, reasonable for high-IV tickers
        elif coc_pct <= 5.5:
            return "AGGRESSIVE"     # High premium = strike close to price
        else:
            return "GREEDY"         # Strike too close, assignment likely
    else:  # monthly
        if coc_pct < 2.5:
            return "TOO_LOW"
        elif coc_pct <= 5.0:
            return "SWEET_SPOT"
        elif coc_pct <= 8.0:
            return "GOOD"
        elif coc_pct <= 12.0:
            return "AGGRESSIVE"
        else:
            return "GREEDY"


def is_down_day(opp):
    """Check if current price is below the open (red candle = better CSP premiums)."""
    # We check if the current price data suggests a down move
    # This is approximated; with IBKR live data we'd have today's open
    return opp.get("is_down_day", False)


def trade_checklist(opp):
    """
    JohnG's 3 checkboxes:
    1. Diversified product (index/sector/Mag7)
    2. Great entry point (bottom of range)
    3. Downside protection (sufficient cushion)
    """
    ticker = opp["ticker"]
    checks = []
    passed = 0

    # 1. Diversified?
    info = WATCHLIST.get(ticker, {})
    leverage = info.get("leverage", "1x")
    is_diversified = leverage in ("2x", "3x") or ticker in ("IREN",)
    if is_diversified:
        checks.append("DIV:PASS")
        passed += 1
    else:
        checks.append("DIV:WARN")

    # 2. Great entry?
    zone = opp.get("sandbox_zone", "KC_MIDDLE")
    if zone in ("BELOW_KC", "KC_BOTTOM"):
        checks.append("ENTRY:PASS")
        passed += 1
    elif zone == "KC_MIDDLE":
        checks.append("ENTRY:OK")
        passed += 0.5
    else:
        checks.append("ENTRY:FAIL")

    # 3. Downside protection?
    dp = opp.get("distance_below_price_pct", 0)
    if dp >= 7:
        checks.append("PROT:PASS")
        passed += 1
    elif dp >= 4:
        checks.append("PROT:OK")
        passed += 0.5
    elif dp >= 2:
        checks.append("PROT:WARN")
    else:
        checks.append("PROT:FAIL")

    if passed >= 2.5:
        grade = "A"
    elif passed >= 2:
        grade = "B"
    elif passed >= 1:
        grade = "C"
    else:
        grade = "F"

    return {"checks": checks, "grade": grade, "passed": passed}


def score_opportunity(opp):
    """
    V1.5 Scoring: 0-100 scale + expected move validation + checklist.

    Breakdown:
    - KC Position: 25 pts
    - RSI Confirmation: 15 pts
    - Support Level: 20 pts
    - Premium Quality: 20 pts (now with sweet spot check)
    - Liquidity: 10 pts
    - DTE Sweet Spot: 10 pts
    + Down-day bonus: up to 3 pts
    + Expected move bonus: up to 5 pts
    """
    scores = {}

    # ── Sandbox zone & KC top exception ──
    sandbox = opp.get("sandbox_zone", "KC_MIDDLE")
    dte = opp.get("dte", 30)
    dp = opp.get("distance_below_price_pct", 0)

    # V1.5: Short-term exception for KC top
    # JohnG does enter near KC top IF: DTE <= 8, downside protection > 3%, strong conviction
    short_term_exception = False
    if sandbox in ("KC_UPPER", "DANGER_ZONE") and dte <= 8 and dp >= 3:
        short_term_exception = True

    if sandbox == "DANGER_ZONE" and not short_term_exception:
        return _reject(opp, "DANGER_ZONE: near KC top")

    # RSI rejection
    rsi_zone = opp.get("rsi_zone", "NEUTRAL")
    if rsi_zone in ("OVERBOUGHT", "VERY_OVERBOUGHT") and not short_term_exception:
        return _reject(opp, "RSI overbought")

    # ── 1. KC POSITION (25 pts) ──
    dist = opp.get("distance_to_kc_bottom_pct", 50)
    if short_term_exception:
        scores["kc_position"] = 8  # Reduced score but not rejected
    elif sandbox == "BELOW_KC":
        scores["kc_position"] = 25
    elif sandbox == "KC_BOTTOM":
        scores["kc_position"] = 22
    elif dist <= 2:
        scores["kc_position"] = 19
    elif dist <= 3:
        scores["kc_position"] = 15
    elif sandbox == "KC_MIDDLE":
        scores["kc_position"] = 10
    elif sandbox == "KC_UPPER":
        scores["kc_position"] = 4
    else:
        scores["kc_position"] = 0

    # ── 2. RSI CONFIRMATION (15 pts) ──
    rsi = opp.get("rsi", 50)
    if rsi_zone == "VERY_OVERSOLD":
        scores["rsi_confirmation"] = 15
    elif rsi_zone == "OVERSOLD":
        scores["rsi_confirmation"] = 12
    elif rsi <= 40:
        scores["rsi_confirmation"] = 8
    elif rsi <= 50:
        scores["rsi_confirmation"] = 5
    elif rsi <= 56:  # V1.5: Goldilocks zone for mid entries
        scores["rsi_confirmation"] = 4
    else:
        scores["rsi_confirmation"] = 2

    # ── 3. SUPPORT LEVEL (20 pts) ── V1.5: multi-tap + gap + candle top
    if opp.get("near_support"):
        strength = opp["support_match"]["strength"] if opp.get("support_match") else 1
        stype = opp["support_match"].get("type", "pivot_low") if opp.get("support_match") else "pivot_low"
        taps = opp["support_match"].get("taps", 1) if opp.get("support_match") else 1

        # Base score by type
        if stype == "resistance_turned_support":
            base = 16  # JohnG: "never trades below that breakout point again"
        elif stype == "candle_top":
            base = 13  # JohnG: "top of this candle right here"
        else:
            base = 12  # Standard pivot low

        # V1.5: Multi-tap bonus (JohnG: "5 times it's tapped the 33 strike")
        if taps >= 5:
            base = min(20, base + 4)
        elif taps >= 3:
            base = min(20, base + 2)

        scores["support_level"] = min(20, base + (strength * 1))
    else:
        # Check if strike aligns with a gap fill target
        strike = opp.get("strike", 0)
        gap_strikes = opp.get("gap_strikes", [])
        near_gap = any(abs(strike - gs) / gs < 0.02 for gs in gap_strikes) if gap_strikes else False

        if near_gap:
            scores["support_level"] = 14  # Gap fill target = strong support
            opp["near_gap_fill"] = True
        # V2.0: DSP range corrected from 37 real trades: avg 8.4%, range 2.2-14.85%
        # Do not penalize deep protection - JohnG regularly uses 8-15% DSP
        elif dp >= 10:
            scores["support_level"] = 10  # Deep DSP - conservative, good in volatile markets
        elif dp >= 7:
            scores["support_level"] = 9   # Above avg DSP (his real avg is 8.4%)
        elif dp >= 5:
            scores["support_level"] = 8   # Solid DSP
        elif dp >= 3:
            scores["support_level"] = 5   # Minimum acceptable
        elif dp >= 1:
            scores["support_level"] = 3
        else:
            scores["support_level"] = 0

    # ── 4. PREMIUM QUALITY (20 pts) ── V1.5: with sweet spot check
    coc = opp.get("coc_pct", 0)
    target = opp.get("target_coc", 2.0)
    dte_class = opp.get("dte_class", "weekly")
    sweet = coc_sweet_spot(coc, dte_class)
    opp["coc_sweet_spot"] = sweet

    if target > 0:
        ratio = coc / target
        if sweet == "GREEDY":
            scores["premium_quality"] = 10  # V1.5: penalize greedy strikes
        elif sweet == "SWEET_SPOT":
            scores["premium_quality"] = 20  # Perfect range
        elif ratio >= 1.5:
            scores["premium_quality"] = 18
        elif ratio >= 1.0:
            scores["premium_quality"] = 16
        elif ratio >= 0.8:
            scores["premium_quality"] = 12
        elif ratio >= 0.6:
            scores["premium_quality"] = 8
        else:
            scores["premium_quality"] = 4
    else:
        scores["premium_quality"] = 0

    # ── 5. LIQUIDITY (10 pts) ──
    oi = opp.get("open_interest", 0)
    vol = opp.get("volume", 0)
    data_source = opp.get("data_source", "YAHOO")
    if data_source == "IBKR_LIVE":
        # More lenient for IBKR since data is reliable
        scores["liquidity"] = 8 if (opp.get("bid", 0) > 0 and opp.get("ask", 0) > 0) else 4
    elif oi >= 500 and vol >= 100:
        scores["liquidity"] = 10
    elif oi >= 200 and vol >= 50:
        scores["liquidity"] = 8
    elif oi >= 50 and vol >= 10:
        scores["liquidity"] = 6
    elif oi >= 10 or vol >= 5:
        scores["liquidity"] = 3
    else:
        scores["liquidity"] = 1

    # ── 6. DTE SWEET SPOT (10 pts) ── V1.5: monthly-only option handling
    has_weekly = opp.get("has_weekly_options", True)
    if not has_weekly:
        # Monthly only: JohnG: "lead in 2 weeks before expiration"
        opp["monthly_only"] = True
        if 14 <= dte <= 22:
            scores["dte_sweet_spot"] = 10  # Best window for monthly-only
        elif 10 <= dte <= 13:
            scores["dte_sweet_spot"] = 7
        elif 23 <= dte <= 35:
            scores["dte_sweet_spot"] = 6
        else:
            scores["dte_sweet_spot"] = 3
    else:
        if 4 <= dte <= 8:
            scores["dte_sweet_spot"] = 10
        elif 2 <= dte <= 3:
            scores["dte_sweet_spot"] = 7
        elif 14 <= dte <= 22:
            scores["dte_sweet_spot"] = 9
        elif 9 <= dte <= 13:
            scores["dte_sweet_spot"] = 6
        elif 23 <= dte <= 30:
            scores["dte_sweet_spot"] = 5
        else:
            scores["dte_sweet_spot"] = 2

    total = sum(scores.values())

    # ── V1.5 BONUSES ──

    # Down-day bonus (up to +3)
    if is_down_day(opp) and opp.get("better_approach") == "CSP":
        bonus_dd = 3
        total += bonus_dd
        opp["down_day_bonus"] = bonus_dd

    # Expected move validation bonus (up to +5)
    iv = opp.get("implied_volatility", 0) / 100  # Convert back to decimal
    if iv > 0 and dte > 0:
        strike = opp.get("strike", 0)
        price = opp.get("current_price", 0)
        safety, downside_1sd = validate_strike_vs_expected_move(price, strike, iv, dte)
        opp["expected_move_safety"] = safety
        opp["expected_downside_1sd"] = round(downside_1sd, 2)

        if safety == "VERY_SAFE":
            total += 5
        elif safety == "SAFE":
            total += 3
        elif safety == "MODERATE":
            total += 1
        # AGGRESSIVE gets no bonus

    # Trade checklist
    checklist = trade_checklist(opp)
    opp["checklist"] = checklist

    # Short-term exception flag
    if short_term_exception:
        opp["short_term_exception"] = True
        total = min(total, 65)  # Cap score for exception trades

    # Signal classification
    if total >= 75:
        signal = "STRONG"
    elif total >= 55:
        signal = "MODERATE"
    elif total >= 40:
        signal = "WEAK"
    else:
        signal = "PASS"

    opp["scores"] = scores
    opp["total_score"] = total
    opp["signal"] = signal
    opp["reject_reason"] = None
    opp["version"] = "1.5"

    return opp


def _reject(opp, reason):
    opp["scores"] = {}
    opp["total_score"] = 0
    opp["signal"] = "REJECTED"
    opp["reject_reason"] = reason
    return opp


def rank_opportunities(opportunities):
    scored = [score_opportunity(opp) for opp in opportunities]
    scored = [s for s in scored if s["signal"] != "REJECTED"]
    scored.sort(key=lambda x: x["total_score"], reverse=True)
    return scored


def filter_top_opportunities(opportunities, min_signal="MODERATE", max_results=15):
    signal_order = {"STRONG": 3, "MODERATE": 2, "WEAK": 1, "PASS": 0, "REJECTED": -1}
    min_level = signal_order.get(min_signal, 0)
    return [o for o in opportunities if signal_order.get(o["signal"], 0) >= min_level][:max_results]


def suggest_havsy_strike(current_price, ideal_support, kc_lower):
    """
    JohnG's "Havsy Game": when the ideal support strike is too far OTM
    to get premium, pick the midpoint between current price and support.
    Then plan for assignment + CC at cost basis.

    "I know I'm not going to get a 56 strike when it's trading at 65.
     But if I think it falls to 56... I pick 60."
    """
    midpoint = round((current_price + ideal_support) / 2, 2)

    # Round to nearest 0.50 for standard strikes
    midpoint = round(midpoint * 2) / 2

    return {
        "current_price": current_price,
        "ideal_support": ideal_support,
        "havsy_strike": midpoint,
        "downside_from_price": round((current_price - midpoint) / current_price * 100, 2),
        "note": f"Havsy: midpoint between ${current_price} and support ${ideal_support}. "
                f"If assigned at ${midpoint}, write CC at ${midpoint} strike.",
    }


def csp_vs_pmcc_recommendation(sandbox_zone, kc_position):
    """
    JohnG's rule:
    - CSP: at the bottom of the range (weekly, full capital)
    - PMCC: bottom area but not at the very bottom (30-day, less capital)
    """
    if sandbox_zone in ("BELOW_KC", "KC_BOTTOM"):
        return "CSP"
    elif kc_position <= 0.35:
        return "EITHER"
    elif kc_position <= 0.50:
        return "PMCC"
    else:
        return "WAIT"


def flexible_buyback_threshold(premium_collected, current_option_price, dte_remaining):
    """
    V2.0 CORRECTED: Buy back based on option DECAY, not profit %.
    From 79 real JohnG email trade alerts:
    - IREN roll: "option is down -89% ... use TIME to our advantage, close this trade"
    - IREN roll: "option is down -80.41% ... close, taking risk off the table"

    He waits until the option has almost fully decayed (80-90% gone),
    THEN closes it and immediately opens a new trade for next week.
    This is different from the 50-72% profit rule discussed in videos.

    Decay % = how much of the original premium has been lost by the option seller
    (i.e. how much the option price has fallen from what you sold it for)
    decay_pct = (premium_collected - current_option_price) / premium_collected * 100

    Rules (from email data):
    - decay >= 89%: BUY BACK NOW (confirmed from rolled trades)
    - decay >= 80%: BUY BACK (confirmed from rolled trades)
    - decay >= 72%: CONSIDER (good threshold for DTE <= 3)
    - decay < 72%: HOLD

    Also: if time value < $0.05, buy back regardless (early buyback rule).
    """
    if premium_collected <= 0:
        return {"should_buyback": False, "reason": "No premium data"}

    decay_pct = ((premium_collected - current_option_price) / premium_collected) * 100

    if decay_pct >= 89:
        action = "BUY BACK NOW"
        should_buyback = True
        note = f"Option decayed {decay_pct:.0f}% - nearly worthless. Roll to next trade."
    elif decay_pct >= 80:
        action = "BUY BACK"
        should_buyback = True
        note = f"Option decayed {decay_pct:.0f}% - take profit, redeploy capital."
    elif decay_pct >= 72 and dte_remaining <= 3:
        action = "BUY BACK"
        should_buyback = True
        note = f"Option decayed {decay_pct:.0f}% with only {dte_remaining}d left. Close it."
    else:
        action = "HOLD"
        should_buyback = False
        note = f"Option decayed {decay_pct:.0f}% - wait for 80-90% decay before closing."

    return {
        "should_buyback": should_buyback,
        "action": action,
        "decay_pct": round(decay_pct, 1),
        "current_value": round(current_option_price, 2),
        "premium_collected": round(premium_collected, 2),
        "dte_remaining": dte_remaining,
        "reason": note,
    }


def early_buyback_check(option_price, intrinsic_value, premium_collected, dte_remaining):
    """
    V1.5: Early buyback when time value is nearly zero.
    JohnG: bought back TNA option for $1.50 when intrinsic was $1.46.
    Only 4 cents of time value remained. He gained 2.5 trading days.

    Rule: if time_value_remaining < $0.05, buy back immediately.
    You lose pennies but gain days to write covered calls.
    """
    time_value_remaining = max(0, option_price - intrinsic_value)

    if time_value_remaining < 0.05:
        days_gained = dte_remaining
        return {
            "action": "BUY_BACK_NOW",
            "time_value_cost": round(time_value_remaining, 2),
            "days_gained": days_gained,
            "premium_preserved": round(premium_collected - time_value_remaining, 2),
            "reason": f"Only ${time_value_remaining:.2f} time value left. Buy back to gain {days_gained} trading day(s) for covered call writing.",
        }
    elif time_value_remaining < 0.15:
        return {
            "action": "CONSIDER",
            "time_value_cost": round(time_value_remaining, 2),
            "days_gained": dte_remaining,
            "premium_preserved": round(premium_collected - time_value_remaining, 2),
            "reason": f"${time_value_remaining:.2f} time value remaining. Consider buying back if you want extra days.",
        }
    else:
        return {
            "action": "HOLD",
            "time_value_cost": round(time_value_remaining, 2),
            "days_gained": 0,
            "premium_preserved": premium_collected,
            "reason": f"${time_value_remaining:.2f} time value still in option. Hold for now.",
        }


def suggest_kc_half_strike(current_price, kc_mid, kc_lower, kc_upper, kc_half):
    """
    V1.5: Suggest strike based on KC half position.
    JohnG: "Once a stock is in and around its mid, break it up."

    Upper half (trading between mid and top): plant flag at KC mid
    Lower half (trading between bottom and mid): plant flag at KC bottom
    """
    if kc_half == "UPPER_HALF":
        target = round(kc_mid, 2)
        note = "Upper half of KC. Target: KC mid ($" + str(target) + "). JohnG plants flag at mid when stock is in upper range."
    elif kc_half == "LOWER_HALF":
        target = round(kc_lower, 2)
        note = "Lower half of KC. Target: KC bottom ($" + str(target) + "). More conservative, deeper downside protection."
    else:
        target = round(kc_lower, 2)
        note = "Below KC channel. Target: KC bottom ($" + str(target) + "). Strongest entry zone."

    downside_from_price = round((current_price - target) / current_price * 100, 2)

    return {
        "target_strike": target,
        "kc_half": kc_half,
        "downside_from_price_pct": downside_from_price,
        "note": note,
    }
