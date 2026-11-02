from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from bot import fundamentals as f

SESSION = pd.Timestamp("2026-10-30")


def earnings(when="2026-10-29 16:00", eps=0.52, estimate=0.40):
    idx = pd.DatetimeIndex(
        [pd.Timestamp("2027-01-28 16:00", tz="America/New_York"), pd.Timestamp(when, tz="America/New_York")]
    )
    return pd.DataFrame({"EPS Estimate": [0.25, estimate], "Reported EPS": [float("nan"), eps]}, index=idx)


def entry(ret=-28.6):
    return {"date": SESSION, "ret_pct": ret, "dist_high_pct": -53.0, "close": 65.76}


def test_parse_earnings_separates_last_and_next():
    last, upcoming = f.parse_earnings(earnings(), date(2026, 10, 30))
    assert last["eps"] == 0.52
    assert upcoming == date(2027, 1, 28)


def test_after_close_report_moves_next_session():
    when = pd.Timestamp("2026-10-29 16:00", tz="America/New_York")
    assert f.reacted_to_earnings(when, date(2026, 10, 30))
    assert not f.reacted_to_earnings(when, date(2026, 10, 29))


def test_beat_and_fall_is_flagged_without_inventing_a_cause():
    lines = f.explain(entry(), {"earnings_dates": earnings()}, [], {}, {}, [])
    text = "\n".join(lines)
    assert "0.52 vs 0.40 esperado" in text
    assert "Superó lo esperado y aun así cayó" in text
    assert "causa no confirmada" in text
    assert "próximos trimestres" in text


def test_old_earnings_are_not_the_trigger():
    data = earnings(when="2026-07-23 16:00")
    text = "\n".join(f.explain(entry(), {"earnings_dates": data}, [], {}, {}, []))
    assert "Sin balance en esta rueda" in text
    assert "Superó" not in text


def test_sector_explains_only_when_it_moves_similarly():
    rows = [{"symbol": "SMH", "label": "Semiconductores", "ret_1d": -7.0}]
    ctx = {"industry": "Semiconductors"}
    own, follows = f.sector_line(entry(-28.6), ctx, rows, {}, {"Semiconductors": "SMH"})
    assert "propio" in own and follows is False
    same, follows = f.sector_line(entry(-9.0), ctx, rows, {}, {"Semiconductors": "SMH"})
    assert "acompaña" in same and follows is True


def test_etf_without_fundamentals_still_explains():
    lines = f.explain(entry(), {}, [], {}, {}, [])
    assert any("bajo su máximo anual" in line for line in lines)
    assert not any(line.startswith("💼") for line in lines)


def test_miss_and_rise_is_flagged():
    data = earnings(eps=0.30)
    text = "\n".join(f.explain(entry(5.0), {"earnings_dates": data}, [], {}, {}, []))
    assert "No llegó a lo esperado y aun así subió" in text


def test_quiet_day_asks_about_the_accumulated_fall():
    rows = [{"symbol": "XLC", "label": "Comunicaciones", "ret_1d": -1.3}]
    lines = f.explain(entry(0.1), {"sector": "Comm"}, rows, {"Comm": "XLC"}, {}, [])
    text = "\n".join(lines)
    assert "se movió poco hoy" in text
    assert "baja acumulada" in text


def test_question_when_sector_explains_or_there_is_a_headline():
    rows = [{"symbol": "SMH", "label": "Semis", "ret_1d": -7.0}]
    ctx = {"industry": "Chips"}
    follows = f.explain(entry(-9.0), ctx, rows, {}, {"Chips": "SMH"}, [])
    assert "todo el sector" in follows[-1]
    own = f.explain(entry(-9.0), {}, [], {}, {}, [{"title": "Titular", "source": "CNBC"}])
    assert "📰 Titular (CNBC)" in own
    assert "puntual" in own[-1]


def test_business_and_price_lines_use_available_data():
    ctx = {
        "revenueGrowth": 0.209,
        "profitMargins": -0.2,
        "forwardPE": 35.5,
        "targetMeanPrice": 95.0,
        "numberOfAnalystOpinions": 43,
        "recommendationKey": "hold",
    }
    assert f.business_line(ctx) == "💼 Ventas +20.9% interanual, margen neto -20.0%."
    assert f.business_line({}) is None
    price = f.price_line(entry(), ctx)
    assert "P/E estimado 35.5" in price
    assert "43 analistas 95.0 (+44%, opinión media: mantener)" in price
    assert f.price_line(entry(), {"forwardPE": -3.0}) == "🏷️ 53% bajo su máximo anual."


def test_next_report_date_is_shown_when_no_earnings_today():
    last = {"when": pd.Timestamp("2026-07-23 16:00"), "eps": 1.0, "estimate": float("nan")}
    text, is_trigger = f.earnings_line(last, date(2026, 11, 4), -5.0, date(2026, 10, 30))
    assert "Próximo: 04/11" in text
    assert "esperado" not in text
    assert is_trigger is False


def test_parse_earnings_without_data():
    assert f.parse_earnings(None, date(2026, 10, 30)) == (None, None)


def test_fetch_context_keeps_available_data(monkeypatch):
    ticker = SimpleNamespace(info={"sector": "Technology", "otro": 1}, earnings_dates="fechas")
    monkeypatch.setattr(f.yf, "Ticker", lambda symbol: ticker)
    ctx = f.fetch_context("INTC")
    assert ctx["sector"] == "Technology"
    assert "otro" not in ctx
    assert ctx["earnings_dates"] == "fechas"


def test_fetch_context_survives_errors(monkeypatch, caplog):
    class Broken:
        @property
        def info(self):
            raise RuntimeError("sin datos")

        @property
        def earnings_dates(self):
            raise RuntimeError("sin fechas")

    monkeypatch.setattr(f.yf, "Ticker", lambda symbol: Broken())
    assert f.fetch_context("URA") == {}
    assert "URA" in caplog.text


def test_analyst_view_compares_target_with_price():
    ctx = {"targetMeanPrice": 120.0, "recommendationKey": "buy", "numberOfAnalystOpinions": 30}
    assert f.analyst_view(ctx, 100.0) == {
        "upside_pct": pytest.approx(20.0),
        "opinion": "buy",
        "opinion_label": "compra",
        "count": 30,
    }


def test_analyst_view_without_data_is_none():
    assert f.analyst_view({}, 100.0) is None
    assert f.analyst_view({"recommendationKey": "none"}, 100.0) is None
    assert f.analyst_view({"recommendationKey": "hold"}, 100.0)["upside_pct"] is None
