"""
CSP Scanner V2.0 - Options Chain Scanner
Scans put options for CSP opportunities + ITM CC comparison + Trade 2 plan.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import Optional
from config import (
    MIN_WEEKLY_COC, TARGET_WEEKLY_COC,
    MIN_MONTHLY_COC, TARGET_MONTHLY_COC,
    WEEKLY_DTE_MIN, WEEKLY_DTE_MAX,
    MONTHLY_DTE_MIN, MONTHLY_DTE_MAX,
    MIN_OPEN_INTEREST, MIN_VOLUME,
)


def get_options_chain(ticker):
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return None
        chains = {}
        today = datetime.now().date()
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if dte < WEEKLY_DTE_MIN or dte > MONTHLY_DTE_MAX:
                continue
            try:
                chain = stock.option_chain(exp_str)
                if chain.puts.empty:
                    continue
                chains[exp_str] = {
                    "dte": dte, "puts": chain.puts,
                    "calls": chain.calls if not chain.calls.empty else None,
                    "exp_date": exp_date,
                }
            except Exception:
                continue
        return chains if chains else None
    except Exception as e:
        print(f"  [ERROR] Options for {ticker}: {e}")
        return None


def calculate_coc(strike, premium):
    if strike <= 0:
        return 0.0
    return (premium / strike) * 100


def classify_dte(dte):
    if WEEKLY_DTE_MIN <= dte <= WEEKLY_DTE_MAX:
        return "weekly"
    elif MONTHLY_DTE_MIN <= dte <= MONTHLY_DTE_MAX:
        return "monthly"
    return "unknown"


def get_min_coc(dte_class):
    return MIN_WEEKLY_COC if dte_class == "weekly" else MIN_MONTHLY_COC if dte_class == "monthly" else 0


def get_target_coc(dte_class):
    return TARGET_WEEKLY_COC if dte_class == "weekly" else TARGET_MONTHLY_COC if dte_class == "monthly" else 0


def find_itm_cc_premium(calls_df, current_price, strike):
    if calls_df is None:
        return None
    call_row = calls_df[calls_df["strike"] == strike]
    if call_row.empty:
        return None
    row = call_row.iloc[0]
    bid = float(row.get("bid", 0))
    ask = float(row.get("ask", 0))
    if bid > 0 and ask > 0:
        call_premium = round((bid + ask) / 2, 2)
    elif float(row.get("lastPrice", 0)) > 0:
        call_premium = float(row["lastPrice"])
    else:
        return None
    if strike >= current_price:
        return None
    intrinsic = round(current_price - strike, 2)
    time_value = round(call_premium - intrinsic, 2)
    if time_value <= 0:
        return None
    return {
        "call_premium": call_premium, "intrinsic_value": intrinsic,
        "time_value_profit": time_value, "downside_protection": intrinsic,
        "cc_coc_pct": round((time_value / strike) * 100, 2),
        "cost_basis": strike, "shares_cost": current_price,
    }


def build_trade2_plan(strike, ticker):
    return {
        "action": f"If assigned at ${strike:.2f}: sell CC at ${strike:.2f} strike",
        "cost_basis": strike, "cc_strike": strike,
        "note": "Use cost basis as CC strike. Extend time (30+ DTE) if premium is thin. Never roll higher.",
    }


def scan_csp_opportunities(
    ticker, current_price, kc_lower, support_levels, nearest_support,
    rsi=50.0, rsi_zone="NEUTRAL", sandbox_zone="KC_MIDDLE",
    in_danger_zone=False, rsi_reject=False,
):
    if in_danger_zone or rsi_reject:
        return []

    chains = get_options_chain(ticker)
    if not chains:
        return []

    opportunities = []

    for exp_str, chain_data in chains.items():
        dte = chain_data["dte"]
        puts = chain_data["puts"]
        calls_df = chain_data.get("calls")
        dte_class = classify_dte(dte)
        min_coc = get_min_coc(dte_class)
        target_coc = get_target_coc(dte_class)

        for _, row in puts.iterrows():
            strike = float(row["strike"])
            bid = float(row.get("bid", 0))
            ask = float(row.get("ask", 0))
            last_price = float(row.get("lastPrice", 0))
            oi = int(row.get("openInterest", 0)) if pd.notna(row.get("openInterest")) else 0
            volume = int(row.get("volume", 0)) if pd.notna(row.get("volume")) else 0
            iv = float(row.get("impliedVolatility", 0)) if pd.notna(row.get("impliedVolatility")) else 0

            if bid > 0 and ask > 0:
                premium = round((bid + ask) / 2, 2)
            elif last_price > 0:
                premium = last_price
            else:
                continue

            if strike > current_price or strike < current_price * 0.85:
                continue

            coc = calculate_coc(strike, premium)
            if coc < min_coc:
                continue
            if oi < MIN_OPEN_INTEREST and volume < MIN_VOLUME:
                continue

            put_intrinsic = max(0, strike - current_price)
            put_time_value = round(premium - put_intrinsic, 2)
            csp_downside_protection = round(current_price - strike, 2)

            itm_cc = find_itm_cc_premium(calls_df, current_price, strike)
            better_approach = "CSP"  # Always CSP - ITM CC shown for reference only

            trade2 = build_trade2_plan(strike, ticker)

            distance_to_kc_bottom = abs(strike - kc_lower) / kc_lower * 100
            distance_below_price = (current_price - strike) / current_price * 100

            near_support = False
            support_match = None
            for s in support_levels:
                if abs(strike - s["price"]) / s["price"] < 0.02:
                    near_support = True
                    support_match = s
                    break

            opp = {
                "ticker": ticker, "expiration": exp_str, "dte": dte,
                "dte_class": dte_class, "strike": strike, "premium": premium,
                "bid": bid, "ask": ask, "coc_pct": round(coc, 2),
                "target_coc": target_coc, "exceeds_target": coc >= target_coc,
                "cash_required_per_contract": strike * 100,
                "premium_per_contract": round(premium * 100, 2),
                "open_interest": oi, "volume": volume,
                "implied_volatility": round(iv * 100, 1),
                "current_price": current_price,
                "distance_below_price_pct": round(distance_below_price, 2),
                "kc_lower": round(kc_lower, 2),
                "near_kc_bottom": distance_to_kc_bottom < 3.0,
                "distance_to_kc_bottom_pct": round(distance_to_kc_bottom, 2),
                "sandbox_zone": sandbox_zone,
                "rsi": rsi, "rsi_zone": rsi_zone,
                "near_support": near_support, "support_match": support_match,
                "put_time_value": put_time_value, "put_intrinsic": put_intrinsic,
                "csp_downside_protection": csp_downside_protection,
                "itm_cc": itm_cc, "better_approach": better_approach,
                "trade2_plan": trade2,
            }
            opportunities.append(opp)

    opportunities.sort(key=lambda x: (
        -(x["near_kc_bottom"] and x["near_support"]),
        -x["near_kc_bottom"], -x["near_support"], -x["coc_pct"],
    ))
    return opportunities
