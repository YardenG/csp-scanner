"""
Expected Stock Move Calculator
JohnG's quantitative tool for CSP strike selection.

"Plug in the stock, the expiration date, and the at-the-money IV.
It gives you an approximate move in the time frame."

Formula: Expected Move = Price x IV x sqrt(DTE / 365)

This gives the 1 standard deviation expected move.
- ~68% chance the stock stays within this range
- JohnG picks strikes AT or BEYOND the expected downside move
- If your strike is beyond the expected move, you have statistical edge

Usage:
    from expected_move import ExpectedMoveCalculator

    calc = ExpectedMoveCalculator()
    result = calc.calculate("TQQQ", strike=39.0, dte=7, iv=0.85)
    print(result)
"""

import math
from typing import Optional


class ExpectedMoveCalculator:
    """
    JohnG's Expected Stock Move Calculator.
    Used to validate strike selection for CSPs.
    """

    @staticmethod
    def expected_move(price: float, iv: float, dte: int) -> dict:
        """
        Calculate expected stock move for a given time frame.

        Args:
            price: Current stock price
            iv: Implied Volatility (as decimal, e.g., 0.85 for 85%)
            dte: Days to expiration

        Returns:
            Dict with expected move up/down and target prices
        """
        if dte <= 0 or iv <= 0 or price <= 0:
            return {"error": "Invalid inputs"}

        # 1 Standard Deviation move
        move_1sd = price * iv * math.sqrt(dte / 365)

        # 2 Standard Deviation move (for extreme scenarios)
        move_2sd = move_1sd * 2

        return {
            "price": round(price, 2),
            "iv": round(iv * 100, 1),
            "dte": dte,
            # 1 SD move (~68% probability range)
            "expected_move_1sd": round(move_1sd, 2),
            "upside_1sd": round(price + move_1sd, 2),
            "downside_1sd": round(price - move_1sd, 2),
            # 2 SD move (~95% probability range)
            "expected_move_2sd": round(move_2sd, 2),
            "upside_2sd": round(price + move_2sd, 2),
            "downside_2sd": round(price - move_2sd, 2),
        }

    @staticmethod
    def validate_strike(price: float, strike: float, iv: float, dte: int) -> dict:
        """
        Validate a CSP strike price against the expected move.

        JohnG picks strikes at or beyond the expected downside move.
        If the strike is within the expected move, it could get challenged.

        Returns:
            Dict with strike validation results
        """
        move = ExpectedMoveCalculator.expected_move(price, iv, dte)
        if "error" in move:
            return move

        downside_1sd = move["downside_1sd"]
        downside_2sd = move["downside_2sd"]

        # How does the strike compare to expected moves?
        strike_vs_1sd = strike - downside_1sd  # Negative = below 1SD (good)
        strike_vs_2sd = strike - downside_2sd  # Negative = below 2SD (very safe)

        # Downside protection as % of price
        downside_pct = round((price - strike) / price * 100, 2)

        # Classification
        if strike <= downside_2sd:
            safety = "VERY_SAFE"
            note = "Strike is beyond 2 SD. Only a 5% chance of being challenged."
        elif strike <= downside_1sd:
            safety = "SAFE"
            note = "Strike is beyond 1 SD. Only a 32% chance of being challenged."
        elif strike <= downside_1sd * 1.02:  # Within 2% of 1SD
            safety = "MODERATE"
            note = "Strike is near the 1 SD expected move. Could be challenged."
        else:
            safety = "AGGRESSIVE"
            note = "Strike is within the expected move. Higher chance of assignment."

        return {
            "strike": strike,
            "price": round(price, 2),
            "downside_protection_pct": downside_pct,
            "expected_downside_1sd": downside_1sd,
            "expected_downside_2sd": downside_2sd,
            "strike_vs_1sd": round(strike_vs_1sd, 2),
            "safety": safety,
            "note": note,
        }

    @staticmethod
    def coc_sweet_spot_check(coc_pct: float, dte_class: str) -> dict:
        """
        Check if CoC% is in JohnG's sweet spot.

        JohnG targets 1.2% weekly minimum, but warns against being greedy.
        Very high CoC% means the strike is too close to the money.

        "Take less upfront premium for more chance of a green trade."
        """
        if dte_class == "weekly":
            if coc_pct < 1.0:
                return {"zone": "TOO_LOW", "note": "Below 1% weekly. Not worth the capital tie-up."}
            elif coc_pct <= 2.0:
                return {"zone": "SWEET_SPOT", "note": "1-2% weekly. JohnG's ideal range."}
            elif coc_pct <= 3.5:
                return {"zone": "GOOD", "note": "2-3.5% weekly. Solid premium with decent protection."}
            elif coc_pct <= 5.0:
                return {"zone": "AGGRESSIVE", "note": "3.5-5% weekly. High premium but less downside protection."}
            else:
                return {"zone": "GREEDY", "note": "Over 5% weekly. Strike is too close. You'll get assigned."}
        else:  # monthly
            if coc_pct < 2.5:
                return {"zone": "TOO_LOW", "note": "Below 2.5% monthly. Not worth the capital tie-up."}
            elif coc_pct <= 5.0:
                return {"zone": "SWEET_SPOT", "note": "2.5-5% monthly. JohnG's ideal range."}
            elif coc_pct <= 8.0:
                return {"zone": "GOOD", "note": "5-8% monthly. Solid premium."}
            elif coc_pct <= 12.0:
                return {"zone": "AGGRESSIVE", "note": "8-12% monthly. High premium, less protection."}
            else:
                return {"zone": "GREEDY", "note": "Over 12% monthly. Way too close to the money."}

    @staticmethod
    def csp_vs_pmcc_recommendation(sandbox_zone: str, kc_position: float, dte_preference: str = "weekly") -> dict:
        """
        Recommend CSP vs PMCC based on where we are in the range.

        JohnG's rule:
        - CSP: When at the BOTTOM of the range. Weekly trades. Full capital.
        - PMCC: When in the bottom AREA but not at the very bottom. 30-day trades. Less capital.
        """
        if sandbox_zone in ("BELOW_KC", "KC_BOTTOM"):
            return {
                "recommendation": "CSP",
                "reason": "At the bottom of the range. CSP gives weekly flexibility and full premium.",
                "dte_suggestion": "Weekly (4-8 days)",
            }
        elif kc_position <= 0.35:
            return {
                "recommendation": "EITHER",
                "reason": "In the lower part of the range. CSP for weekly income, PMCC for less capital + stock movement.",
                "dte_suggestion": "CSP weekly or PMCC 30-day",
            }
        elif kc_position <= 0.50:
            return {
                "recommendation": "PMCC",
                "reason": "Middle of range. PMCC uses less capital and benefits from upward stock movement.",
                "dte_suggestion": "PMCC 30-day with 98 delta LEAPS",
            }
        else:
            return {
                "recommendation": "WAIT",
                "reason": "Upper range. Wait for a pullback before entering.",
                "dte_suggestion": "Do not enter. Wait for KC mid or lower.",
            }

    @staticmethod
    def trade_checklist(ticker: str, is_diversified: bool, entry_quality: str,
                        downside_protection_pct: float) -> dict:
        """
        JohnG's 3 Checkboxes for every trade:
        1. Diversified product (index/sector/Mag7)
        2. Great entry point
        3. Downside protection

        "These are checkboxes. Checkbox diversified investment.
         Checkbox downside protection. Checkbox where is it trading in the range."
        """
        checks = []
        passed = 0

        # Checkbox 1: Diversified
        if is_diversified:
            checks.append({"check": "Diversified Product", "status": "PASS", "note": "Index/sector/Mag7 ETF"})
            passed += 1
        else:
            checks.append({"check": "Diversified Product", "status": "WARN", "note": "Single stock risk. Be extra careful."})

        # Checkbox 2: Entry point
        if entry_quality in ("BELOW_KC", "KC_BOTTOM"):
            checks.append({"check": "Great Entry Point", "status": "PASS", "note": "At bottom of range"})
            passed += 1
        elif entry_quality == "KC_MIDDLE":
            checks.append({"check": "Great Entry Point", "status": "OK", "note": "Mid range. Acceptable with downside protection."})
            passed += 0.5
        else:
            checks.append({"check": "Great Entry Point", "status": "FAIL", "note": "Near top of range. High risk of becoming bag holder."})

        # Checkbox 3: Downside protection
        if downside_protection_pct >= 7:
            checks.append({"check": "Downside Protection", "status": "PASS", "note": f"{downside_protection_pct}% cushion. Excellent."})
            passed += 1
        elif downside_protection_pct >= 4:
            checks.append({"check": "Downside Protection", "status": "OK", "note": f"{downside_protection_pct}% cushion. Decent."})
            passed += 0.5
        elif downside_protection_pct >= 2:
            checks.append({"check": "Downside Protection", "status": "WARN", "note": f"{downside_protection_pct}% cushion. Thin."})
        else:
            checks.append({"check": "Downside Protection", "status": "FAIL", "note": f"{downside_protection_pct}% cushion. Not enough."})

        grade = "A" if passed >= 2.5 else "B" if passed >= 2 else "C" if passed >= 1 else "F"

        return {
            "ticker": ticker,
            "checklist": checks,
            "passed": passed,
            "total": 3,
            "grade": grade,
        }
