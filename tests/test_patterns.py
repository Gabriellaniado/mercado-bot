import math

from bot import patterns


def ramp(start, end, n):
    return [start + (end - start) * i / (n - 1) for i in range(n)]


def cut_at_first_cross(close, up):
    """Recorta la serie en la primera rueda en que la media de 50 pasa a la de 200."""
    for end in range(201, len(close) + 1):
        fast, slow = patterns.sma(close, 50, end), patterns.sma(close, 200, end)
        if (fast > slow) == up and (
            patterns.sma(close, 50, end - 1) > patterns.sma(close, 200, end - 1)
        ) != up:
            return close[:end]
    raise AssertionError("la serie de prueba no cruza")


def labels(signals):
    return {(s["side"], s["label"]) for s in signals}


def test_sma_needs_enough_data():
    assert patterns.sma([1, 2, 3], 5) is None
    assert patterns.sma([1, 2, 3, 4], 2) == 3.5
    assert patterns.sma([1, 2, 3, 4], 2, end=3) == 2.5


def test_golden_cross_detected_right_after_it_happens():
    # Cae un año y recién en las últimas ruedas rebota con fuerza: la media de 50 pasa la de 200
    close = cut_at_first_cross(ramp(200, 100, 230) + ramp(100, 300, 120), up=True)
    assert patterns.ma_cross(close, 50, 200) == 1
    # Mucho después el cruce ya no es noticia
    assert patterns.ma_cross(close + [close[-1]] * 40, 50, 200) == 0


def test_death_cross_is_a_sell_signal():
    close = cut_at_first_cross(ramp(100, 200, 230) + ramp(200, 40, 120), up=False)
    assert patterns.ma_cross(close, 50, 200) == -1


def test_no_cross_without_history_or_in_a_steady_trend():
    assert patterns.ma_cross([1.0] * 30, 50, 200) == 0
    assert patterns.ma_cross(ramp(100, 200, 260), 50, 200) == 0


def test_moving_average_signals_labels_golden_cross():
    close = cut_at_first_cross(ramp(200, 100, 230) + ramp(100, 300, 120), up=True)
    found = patterns.moving_average_signals(close)
    assert ("compra", "cruce dorado (media de 50 sobre la de 200)") in labels(found)


def test_pivots_find_peak_and_trough():
    values = ramp(0, 10, 11) + ramp(10, 0, 11)[1:] + ramp(0, 10, 11)[1:]
    highs, lows = patterns.pivots(values, order=3)
    assert highs == [10]
    assert lows == [20]


def test_double_top_confirmed_on_neckline_break():
    close = ramp(80, 100, 20) + ramp(100, 90, 8)[1:] + ramp(90, 99, 8)[1:] + ramp(99, 89, 10)[1:]
    # 100 -> 90 -> 99 -> 89: dos techos, piso en 90, hoy cierra en 89 (rompió hace una rueda)
    assert patterns.double_top(close)["side"] == "venta"


def test_double_top_not_confirmed_while_price_holds_the_neckline():
    close = ramp(80, 100, 20) + ramp(100, 90, 8)[1:] + ramp(90, 99, 8)[1:] + ramp(99, 93, 6)[1:]
    assert patterns.double_top(close) is None


def test_double_bottom_confirmed_on_neckline_break():
    close = ramp(120, 100, 20) + ramp(100, 110, 8)[1:] + ramp(110, 101, 8)[1:] + ramp(101, 111, 10)[1:]
    assert patterns.double_bottom(close)["side"] == "compra"


def test_old_double_top_is_ignored():
    close = ramp(80, 100, 20) + ramp(100, 90, 8)[1:] + ramp(90, 99, 8)[1:] + ramp(99, 89, 10)[1:]
    assert patterns.double_top(close + [88.0] * 10) is None


def test_range_breakout_up_and_down():
    flat = [100.0 + (i % 3) for i in range(30)]
    assert patterns.range_breakout(flat + [106.0])["side"] == "compra"
    assert patterns.range_breakout(flat + [95.0])["side"] == "venta"
    assert patterns.range_breakout(flat + [101.0]) is None


def test_wide_range_is_not_a_consolidation():
    wide = ramp(80, 120, 30)
    assert patterns.range_breakout(wide + [130.0]) is None


def test_chart_signals_collects_everything():
    flat = [100.0 + (i % 3) for i in range(30)]
    found = patterns.chart_signals(flat + [106.0])
    assert any(s["side"] == "compra" for s in found)


def test_non_positive_prices_are_skipped():
    assert patterns.chart_signals([100.0] * 40 + [-5.0]) == []


def wave(i):
    """Onda de 20 ruedas, entre 0 y 6, que toca su mínimo en i = 0, 20, 40..."""
    return 3 * (1 - math.cos(2 * math.pi * i / 20))


UPTREND = [100 + 0.4 * i + wave(i) for i in range(140)]
DOWNTREND = [300 - 0.4 * i - wave(i) + 6 for i in range(140)]


def test_bounce_on_rising_support_is_a_buy():
    found = patterns.trendline_signals(UPTREND[:104])
    assert [s["side"] for s in found] == ["compra"]
    assert "rebota en su soporte de tendencia alcista (~142" in found[0]["label"]


def test_losing_the_rising_support_is_a_sell():
    close = UPTREND[:104] + [UPTREND[103] - 4, UPTREND[103] - 8, UPTREND[103] - 9]
    found = patterns.trendline_signals(close)
    assert [s["side"] for s in found] == ["venta"]
    assert "rompe su soporte" in found[0]["label"]


def test_rejection_at_falling_resistance_is_a_sell():
    sides = {s["side"] for n in range(100, 125) for s in patterns.trendline_signals(DOWNTREND[:n])}
    assert "venta" in sides


def test_breaking_falling_resistance_is_a_buy():
    close = DOWNTREND[:104] + [DOWNTREND[103] + 4, DOWNTREND[103] + 8, DOWNTREND[103] + 9]
    found = patterns.trendline_signals(close)
    assert [s["side"] for s in found] == ["compra"]
    assert "rompe su resistencia" in found[0]["label"]


def test_no_trendline_without_enough_touches():
    assert patterns.trendline_signals(ramp(100, 140, 120)) == []
    assert patterns.trendline_signals([100.0] * 120) == []
