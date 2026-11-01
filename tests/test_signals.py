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


def test_opportunity_needs_deep_drawdown_and_oversold():
    # Sube hasta 100 y luego cae sostenidamente: RSI bajo, cerca del mínimo, -35% del máximo
    prices = list(np.linspace(60, 100, 40)) + list(np.linspace(100, 65, 30))
    sig = signals.compute_signals("X", make_df(prices))
    reasons = signals.opportunity_reasons(sig, CFG)
    assert any("sobrevendido" in r for r in reasons)
    assert any("máximo anual" in r for r in reasons)


def test_no_opportunity_when_price_near_high():
    sig = signals.compute_signals("X", make_df(calm_series()))
    assert signals.opportunity_reasons(sig, CFG) == []
