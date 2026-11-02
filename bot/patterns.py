"""Cruces de medias móviles y figuras chartistas simples. Funciones puras sobre listas de precios.

Son reglas mecánicas y aproximadas: sirven para marcar activos a revisar, no para confirmar
una figura. Cada detector devuelve None si no hay señal, o un dict con el lado ("compra" o
"venta"), un texto corto y un puntaje para ordenar.
"""

from __future__ import annotations

import math

Signal = dict  # {"side": "compra" | "venta", "label": str, "score": float}


def sma(values: list[float], n: int, end: int | None = None) -> float | None:
    """Media simple de las n ruedas que terminan en `end` (excluido). None si no hay datos."""
    end = len(values) if end is None else end
    if end < n or n <= 0:
        return None
    return sum(values[end - n : end]) / n


def ma_cross(close: list[float], fast: int, slow: int, lookback: int = 3) -> int:
    """+1 si la media rápida cruzó hacia arriba de la lenta en las últimas `lookback` ruedas,
    -1 si cruzó hacia abajo, 0 si no hubo cruce (o no hay historia suficiente)."""
    n = len(close)
    now_fast, now_slow = sma(close, fast), sma(close, slow)
    if now_fast is None or now_slow is None or now_fast == now_slow:
        return 0
    side = 1 if now_fast > now_slow else -1
    # Hubo cruce si en alguna de las ruedas previas la rápida estaba del otro lado.
    for back in range(1, lookback + 1):
        f, s = sma(close, fast, n - back), sma(close, slow, n - back)
        if f is None or s is None:
            return 0
        if (f - s) * side <= 0:
            return side
    return 0


def moving_average_signals(close: list[float], lookback: int = 3) -> list[Signal]:
    signals: list[Signal] = []
    golden = ma_cross(close, 50, 200, lookback)
    if golden:
        up = golden > 0
        signals.append(
            {
                "side": "compra" if up else "venta",
                "label": "cruce dorado (media de 50 sobre la de 200)"
                if up
                else "cruce de la muerte (media de 50 bajo la de 200)",
                "score": 40.0,
            }
        )
    short = ma_cross(close, 20, 50, lookback)
    if short:
        up = short > 0
        signals.append(
            {
                "side": "compra" if up else "venta",
                "label": "media de 20 cruza sobre la de 50" if up else "media de 20 cruza bajo la de 50",
                "score": 20.0,
            }
        )
    return signals


def pivots(values: list[float], order: int = 5) -> tuple[list[int], list[int]]:
    """Posiciones de máximos y mínimos locales: el mayor (o menor) de `order` ruedas a cada lado."""
    highs, lows = [], []
    for i in range(order, len(values) - order):
        window = values[i - order : i + order + 1]
        if values[i] == max(window) and window.count(values[i]) == 1:
            highs.append(i)
        elif values[i] == min(window) and window.count(values[i]) == 1:
            lows.append(i)
    return highs, lows


def _double_top(
    close: list[float], tolerance_pct: float, min_depth_pct: float, min_gap: int, recent: int
) -> bool:
    """Doble techo confirmado: dos máximos parecidos y el precio rompe hacia abajo el piso entre ambos."""
    highs, _ = pivots(close)
    if len(highs) < 2:
        return False
    p1, p2 = highs[-2], highs[-1]
    h1, h2 = close[p1], close[p2]
    if p2 - p1 < min_gap or abs(h2 / h1 - 1) * 100 > tolerance_pct:
        return False
    neckline = min(close[p1 : p2 + 1])
    if (min(h1, h2) / neckline - 1) * 100 < min_depth_pct:
        return False
    now = close[-1]
    if now >= neckline or now < neckline * 0.95:
        return False  # sin ruptura, o la ruptura ya no es reciente
    # La ruptura es nueva si hace poco el precio todavía estaba sobre el piso.
    return any(c >= neckline for c in close[-(recent + 1) : -1])


def double_top(close: list[float], lookback: int = 90, recent: int = 3) -> Signal | None:
    window = close[-lookback:]
    if _double_top(window, 3.0, 5.0, 8, recent):
        return {"side": "venta", "label": "doble techo confirmado", "score": 35.0}
    return None


def double_bottom(close: list[float], lookback: int = 90, recent: int = 3) -> Signal | None:
    window = close[-lookback:]
    if len(window) < 20:
        return None
    # Un doble piso es un doble techo del precio invertido: se reutiliza el mismo detector.
    if _double_top([1 / c for c in window], 3.0, 5.0, 8, recent):
        return {"side": "compra", "label": "doble piso confirmado", "score": 35.0}
    return None


def range_breakout(close: list[float], days: int = 20, max_width_pct: float = 10.0) -> Signal | None:
    """Rompe hacia arriba o hacia abajo un rango lateral angosto de las últimas `days` ruedas."""
    if len(close) < days + 1:
        return None
    prior = close[-days - 1 : -1]
    top, bottom = max(prior), min(prior)
    if (top / bottom - 1) * 100 > max_width_pct:
        return None
    now = close[-1]
    if now > top:
        return {"side": "compra", "label": f"rompe al alza su rango de {days} ruedas", "score": 25.0}
    if now < bottom:
        return {"side": "venta", "label": f"rompe a la baja su rango de {days} ruedas", "score": 25.0}
    return None


def _trend_event(
    y: list[float],
    lookback: int = 120,
    min_gap: int = 10,
    max_age: int = 40,
    tolerance: float = 0.015,
    touch: float = 0.01,
    min_touches: int = 3,
) -> tuple[str, float] | None:
    """Traza una línea de soporte que apoya en mínimos ascendentes de `y` y mira cómo está hoy.

    `y` son logaritmos de precios, así la recta vale para cualquier escala. La línea une el
    último mínimo con algún mínimo anterior y solo vale si toca al menos `min_touches` mínimos
    (a menos de `touch` de distancia) y el precio no la perdió entre toques. Devuelve
    ("rebote", nivel) si hoy el precio apoya en ella y gira, ("ruptura", nivel) si acaba de
    perderla, o None. El nivel está en la misma escala que `y`.
    """
    window = y[-lookback:]
    n = len(window)
    _, lows = pivots(window)
    if len(lows) < min_touches or n - 1 - lows[-1] > max_age:
        return None
    p2 = lows[-1]
    for p1 in reversed(lows[:-1]):
        if p2 - p1 < min_gap or window[p2] <= window[p1]:
            continue
        slope = (window[p2] - window[p1]) / (p2 - p1)

        def line(i: int, p1: int = p1, slope: float = slope) -> float:
            return window[p1] + slope * (i - p1)

        touches = sum(1 for q in lows if q >= p1 and abs(window[q] - line(q)) <= touch)
        if touches < min_touches:
            continue
        if any(window[i] < line(i) - tolerance for i in range(p1, n - 3)):
            continue
        gap_now = window[-1] - line(n - 1)
        recent = [window[n - 1 - k] - line(n - 1 - k) for k in range(4)]
        if min(recent) >= -0.01 and 0 <= gap_now <= 0.02 and window[-1] > window[-2]:
            return "rebote", line(n - 1)
        if gap_now < -0.01 and any(g >= 0 for g in recent[1:]):
            return "ruptura", line(n - 1)
        return None
    return None


def trendline_signals(close: list[float]) -> list[Signal]:
    """Soporte de tendencia alcista y resistencia de tendencia bajista, trazados con los pivotes."""
    logs = [math.log(c) for c in close]
    found: list[Signal] = []

    event = _trend_event(logs)  # soporte: mínimos cada vez más altos
    if event:
        kind, level = event
        price = f"~{math.exp(level):.2f}"
        if kind == "rebote":
            label, side = f"rebota en su soporte de tendencia alcista ({price})", "compra"
        else:
            label, side = f"rompe su soporte de tendencia alcista ({price})", "venta"
        found.append({"side": side, "label": label, "score": 30.0 if kind == "rebote" else 35.0})

    event = _trend_event([-x for x in logs])  # resistencia: máximos cada vez más bajos
    if event:
        kind, level = event
        price = f"~{math.exp(-level):.2f}"
        if kind == "rebote":
            label, side = f"rechazado en su resistencia de tendencia bajista ({price})", "venta"
        else:
            label, side = f"rompe su resistencia de tendencia bajista ({price})", "compra"
        found.append({"side": side, "label": label, "score": 30.0 if kind == "rebote" else 35.0})
    return found


def chart_signals(close: list[float], lookback: int = 3) -> list[Signal]:
    """Todas las señales de cruces y figuras que tiene el activo hoy."""
    if any(c <= 0 for c in close):  # los cocientes de las figuras no tienen sentido con precios <= 0
        return []
    found = moving_average_signals(close, lookback)
    for detector in (double_top, double_bottom, range_breakout):
        signal = detector(close)
        if signal:
            found.append(signal)
    return found + trendline_signals(close)
