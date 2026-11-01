"""Cálculo de señales. Funciones puras: no hacen llamadas de red."""

from __future__ import annotations

import math

import pandas as pd


def rsi(close: pd.Series, n: int = 14) -> float:
    """RSI de Wilder del último dato. Devuelve NaN si no hay datos suficientes."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean().iloc[-1]
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean().iloc[-1]
    if pd.isna(avg_gain) or pd.isna(avg_loss):
        return math.nan
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def compute_signals(symbol: str, df: pd.DataFrame) -> dict | None:
    """df debe tener columnas Close y Volume, ordenadas por fecha."""
    close = df["Close"].dropna()
    if len(close) < 30:
        return None

    returns = close.pct_change()
    last_ret = returns.iloc[-1]
    # Volatilidad de los 20 días anteriores (sin contar hoy)
    std20 = returns.iloc[-21:-1].std()
    if pd.isna(last_ret) or pd.isna(std20):
        return None

    vol_ratio = math.nan
    if "Volume" in df:
        vol = df["Volume"].reindex(close.index)
        avg_vol = vol.iloc[-21:-1].mean()
        if avg_vol and not pd.isna(avg_vol) and avg_vol > 0:
            vol_ratio = float(vol.iloc[-1] / avg_vol)

    window = close.tail(252)
    last = float(close.iloc[-1])
    return {
        "symbol": symbol,
        "date": close.index[-1],
        "close": last,
        "ret_pct": float(last_ret * 100),
        "std20_pct": float(std20 * 100),
        "z": float(last_ret / std20) if std20 > 0 else 0.0,
        "vol_ratio": vol_ratio,
        "rsi": float(rsi(close)),
        "dist_high_pct": float((last / window.max() - 1) * 100),
        "dist_low_pct": float((last / window.min() - 1) * 100),
    }


def _period_ret_pct(close: pd.Series, days: int) -> float:
    if len(close) <= days:
        return math.nan
    return float((close.iloc[-1] / close.iloc[-1 - days] - 1) * 100)


def sector_moves(closes: dict[str, pd.Series], sectors: list[dict], benchmark: str) -> list[dict]:
    """Variación de cada sector y su diferencia contra el índice, de mejor a peor en el día."""
    bench = closes.get(benchmark)
    if bench is None:
        return []
    bench_1d, bench_5d = _period_ret_pct(bench, 1), _period_ret_pct(bench, 5)
    rows = []
    for s in sectors:
        close = closes.get(s["symbol"])
        if close is None or len(close) < 6:
            continue
        ret_1d, ret_5d = _period_ret_pct(close, 1), _period_ret_pct(close, 5)
        rows.append(
            {
                "symbol": s["symbol"],
                "label": s["label"],
                "ret_1d": ret_1d,
                "ret_5d": ret_5d,
                "rel_1d": ret_1d - bench_1d,
                "rel_5d": ret_5d - bench_5d,
            }
        )
    return sorted(rows, key=lambda r: r["rel_1d"], reverse=True)


def detect_rotation(
    close_a: pd.Series,
    close_b: pd.Series,
    min_gap_pct: float,
    z_threshold: float,
) -> dict | None:
    """Detecta si hoy uno de los dos activos subió y el otro bajó con una brecha inusual.

    Devuelve qué activo ganó, la brecha del día, cuántas veces supera la brecha habitual
    de los 20 días anteriores y la brecha acumulada en 5 días. None si no hay señal.
    """
    aligned = pd.concat([close_a, close_b], axis=1, join="inner").dropna()
    if len(aligned) < 27:
        return None
    rets = aligned.pct_change() * 100
    ret_a, ret_b = float(rets.iloc[-1, 0]), float(rets.iloc[-1, 1])
    if ret_a * ret_b >= 0:  # si los dos van para el mismo lado no hay rotación
        return None
    spread = rets.iloc[:, 0] - rets.iloc[:, 1]
    gap = float(spread.iloc[-1])
    typical = float(spread.iloc[-21:-1].std())
    if pd.isna(typical) or typical <= 0:
        return None
    z = abs(gap) / typical
    if abs(gap) < min_gap_pct or z < z_threshold:
        return None
    gap_5d = _period_ret_pct(aligned.iloc[:, 0], 5) - _period_ret_pct(aligned.iloc[:, 1], 5)
    a_wins = gap > 0
    return {
        "winner_ret": ret_a if a_wins else ret_b,
        "loser_ret": ret_b if a_wins else ret_a,
        "a_wins": a_wins,
        "gap": abs(gap),
        "z": z,
        "gap_5d": gap_5d if a_wins else -gap_5d,  # positivo = el ganador de hoy también viene ganando
    }


def is_big_move(sig: dict, cfg: dict, group: str) -> bool:
    """Movimiento grande: supera el mínimo del grupo o z veces la volatilidad habitual."""
    min_move = cfg.get("min_move_pct_by_group", {}).get(group, cfg["min_move_pct"])
    threshold = max(min_move, cfg["z_threshold"] * sig["std20_pct"])
    return abs(sig["ret_pct"]) >= threshold


def opportunity_reasons(sig: dict, cfg: dict) -> list[str]:
    """Motivos por los que un activo merece una mirada. Lista vacía = no hay señal.

    Es una señal técnica para revisar, no una recomendación de compra.
    """
    if sig["dist_high_pct"] > -cfg["min_drawdown_pct"]:
        return []
    reasons = []
    if not math.isnan(sig["rsi"]) and sig["rsi"] <= cfg["rsi_oversold"]:
        reasons.append(f"RSI {sig['rsi']:.0f} (sobrevendido)")
    if sig["dist_low_pct"] <= cfg["near_52w_low_pct"]:
        reasons.append(f"a {sig['dist_low_pct']:.1f}% de su mínimo de 52 semanas")
    if reasons:
        reasons.append(f"{abs(sig['dist_high_pct']):.0f}% bajo su máximo anual")
    return reasons
