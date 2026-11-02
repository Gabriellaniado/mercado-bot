import math

import numpy as np
import pandas as pd

from bot import signals

CFG = {
    "min_move_pct": 4.0,
    "z_threshold": 2.5,
    "min_move_pct_by_group": {"Materias primas": 2.5},
    "rsi_oversold": 30,
    "near_52w_low_pct": 5.0,
    "min_drawdown_pct": 20.0,
    "breakout_volume_ratio": 1.5,
    "rsi_overbought": 70,
    "near_52w_high_pct": 5.0,
}


def make_df(prices, volume=1_000):
    idx = pd.bdate_range("2026-01-01", periods=len(prices))
    return pd.DataFrame({"Close": prices, "Volume": [volume] * len(prices)}, index=idx)


def calm_series(n=60, last_move=0.0):
    rng = np.random.default_rng(0)
    steps = 1 + rng.normal(0, 0.002, n - 1)
    prices = list(100 * np.cumprod(steps))
    prices.append(prices[-1] * (1 + last_move))
    return prices


def test_rsi_all_gains_is_100():
    assert signals.rsi(pd.Series(range(1, 40), dtype=float)) == 100.0


def test_rsi_falling_prices_is_low():
    assert signals.rsi(pd.Series(range(100, 40, -1), dtype=float)) < 5


def test_rsi_short_series_is_nan():
    assert math.isnan(signals.rsi(pd.Series([1.0, 2.0, 3.0])))


def test_compute_signals_needs_enough_data():
    assert signals.compute_signals("X", make_df([100.0] * 10)) is None


def test_big_move_detected():
    sig = signals.compute_signals("X", make_df(calm_series(last_move=0.07)))
    assert sig["ret_pct"] > 6.9
    assert signals.is_big_move(sig, CFG, "S&P 500")


def test_calm_day_is_not_big_move():
    sig = signals.compute_signals("X", make_df(calm_series(last_move=0.001)))
    assert not signals.is_big_move(sig, CFG, "S&P 500")


def test_group_threshold_is_lower_for_commodities():
    sig = signals.compute_signals("GC=F", make_df(calm_series(last_move=0.03)))
    assert not signals.is_big_move(sig, CFG, "S&P 500")  # 3% < 4%
    assert signals.is_big_move(sig, CFG, "Materias primas")  # 3% >= 2.5%


def test_buy_signal_on_deep_drawdown_and_oversold():
    # Sube hasta 100 y luego cae sostenidamente: RSI bajo, cerca del mínimo, -35% del máximo
    prices = list(np.linspace(60, 100, 40)) + list(np.linspace(100, 65, 30))
    sig = signals.compute_signals("X", make_df(prices))
    found = signals.opportunity_signal(sig, CFG)
    assert found["side"] == "compra"
    assert any("sobrevendido" in r for r in found["reasons"])
    assert any("bajo su máximo" in r for r in found["reasons"])


def test_no_signal_for_calm_flat_series():
    sig = signals.compute_signals("X", make_df(calm_series()))
    assert signals.opportunity_signal({**sig, "rsi": 50.0, "dist_high_pct": -10.0}, CFG) is None


def test_sell_signal_when_overbought_near_high():
    prices = list(np.linspace(60, 100, 70))  # sube sin pausa: RSI ~100, en su máximo
    sig = signals.compute_signals("X", make_df(prices))
    found = signals.opportunity_signal(sig, CFG)
    assert found["side"] == "venta"
    assert any("sobrecomprado" in r for r in found["reasons"])


def test_breakout_buy_needs_high_volume():
    base = {"rsi": 60.0, "dist_high_pct": 0.0, "dist_low_pct": 50.0, "ret_pct": 2.0, "vol_ratio": 2.0}
    found = signals.opportunity_signal(base, CFG)
    assert found["side"] == "compra"
    assert "rompe su máximo de 52 semanas" in found["reasons"]
    assert signals.opportunity_signal({**base, "vol_ratio": 1.0}, CFG) is None


def test_sell_and_breakout_can_be_disabled():
    cfg = {**CFG, "breakout_volume_ratio": 0, "rsi_overbought": 0}
    sig = {"rsi": 90.0, "dist_high_pct": 0.0, "dist_low_pct": 50.0, "ret_pct": 2.0, "vol_ratio": 3.0}
    assert signals.opportunity_signal(sig, cfg) is None


def test_chart_signals_are_ignored_unless_enabled():
    sig = {
        "rsi": 50.0,
        "dist_high_pct": -10.0,
        "dist_low_pct": 30.0,
        "ret_pct": 1.0,
        "chart": [{"side": "venta", "label": "doble techo confirmado", "score": 35.0}],
    }
    assert signals.opportunity_signal(sig, CFG) is None
    found = signals.opportunity_signal(sig, {**CFG, "chart_signals": True})
    assert found["side"] == "venta"
    assert found["reasons"] == ["doble techo confirmado"]


def test_agreeing_signals_add_up_and_the_stronger_side_wins():
    sig = {
        "rsi": 75.0,
        "dist_high_pct": -2.0,
        "dist_low_pct": 60.0,
        "ret_pct": 1.0,
        "chart": [
            {"side": "venta", "label": "doble techo confirmado", "score": 35.0},
            {"side": "compra", "label": "media de 20 cruza sobre la de 50", "score": 20.0},
        ],
    }
    found = signals.opportunity_signal(sig, {**CFG, "chart_signals": True})
    assert found["side"] == "venta"
    assert found["score"] == 75.0 + 35.0
    assert "media de 20 cruza sobre la de 50" not in found["reasons"]
    assert any("sobrecomprado" in r for r in found["reasons"])


ANALYST_CFG = {"analyst_min_upside_pct": 15.0, "analyst_min_count": 5, "analyst_weight": 20}
BUY = {"side": "compra", "reasons": ["RSI 25 (sobrevendido)"], "score": 50.0}


def view(upside, opinion, count=20, label=None):
    return {"upside_pct": upside, "opinion": opinion, "opinion_label": label or opinion, "count": count}


def test_bullish_analysts_back_a_buy_and_raise_it():
    out = signals.apply_analyst_view(BUY, view(40.0, "buy", label="compra"), ANALYST_CFG)
    assert out["score"] == 70.0
    assert out["analysts"] == "favor"
    assert out["reasons"][-1] == "analistas a favor (compra, objetivo +40%)"


def test_bullish_analysts_contradict_a_sell():
    sell = {"side": "venta", "reasons": ["RSI 78 (sobrecomprado)"], "score": 78.0}
    out = signals.apply_analyst_view(sell, view(30.0, "strong_buy"), ANALYST_CFG)
    assert out["score"] == 58.0
    assert out["analysts"] == "contra"
    assert "analistas en contra" in out["reasons"][-1]


def test_bearish_analysts_back_a_sell_and_contradict_a_buy():
    sell = {"side": "venta", "reasons": ["x"], "score": 70.0}
    assert signals.apply_analyst_view(sell, view(-8.0, "hold"), ANALYST_CFG)["analysts"] == "favor"
    assert signals.apply_analyst_view(BUY, view(5.0, "sell"), ANALYST_CFG)["analysts"] == "contra"


def test_mixed_or_thin_analyst_opinion_changes_nothing():
    assert (
        signals.apply_analyst_view(BUY, view(-1.0, "buy"), ANALYST_CFG) == BUY
    )  # objetivo bajo, pero compra
    assert signals.apply_analyst_view(BUY, view(8.0, "hold"), ANALYST_CFG) == BUY
    assert signals.apply_analyst_view(BUY, view(50.0, "buy", count=2), ANALYST_CFG) == BUY
    assert signals.apply_analyst_view(BUY, None, ANALYST_CFG) == BUY
