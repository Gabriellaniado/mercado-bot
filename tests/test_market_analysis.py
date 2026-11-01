import numpy as np
import pandas as pd

from bot import signals


def series(last_ret: float, n: int = 40, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0, 0.003, n)
    rets[-1] = last_ret
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.Series(100 * np.cumprod(1 + rets), index=idx)


def test_rotation_detected_with_winner():
    r = signals.detect_rotation(series(-0.03, seed=1), series(0.02, seed=2), 1.5, 2.0)
    assert r is not None
    assert r["a_wins"] is False
    assert round(r["gap"], 1) == 5.0
    assert r["winner_ret"] > 0 > r["loser_ret"]


def test_no_rotation_if_both_fall():
    assert signals.detect_rotation(series(-0.03, seed=1), series(-0.001, seed=2), 1.5, 2.0) is None


def test_no_rotation_if_gap_is_small():
    assert signals.detect_rotation(series(-0.002, seed=1), series(0.002, seed=2), 1.5, 2.0) is None


def test_sector_moves_sorted_against_benchmark():
    closes = {"SPY": series(0.0, seed=3), "A": series(-0.02, seed=1), "B": series(0.02, seed=2)}
    rows = signals.sector_moves(
        closes,
        [{"symbol": "A", "label": "A"}, {"symbol": "B", "label": "B"}, {"symbol": "X", "label": "X"}],
        "SPY",
    )
    assert [r["symbol"] for r in rows] == ["B", "A"]
    assert rows[0]["rel_1d"] > 0 > rows[1]["rel_1d"]


def test_sector_moves_without_benchmark_is_empty():
    assert signals.sector_moves({"A": series(0.01)}, [{"symbol": "A", "label": "A"}], "SPY") == []


def test_rotation_needs_enough_history():
    assert signals.detect_rotation(series(-0.03, n=20), series(0.02, n=20), 1.5, 2.0) is None
