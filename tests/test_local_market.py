from datetime import date

import pandas as pd
import pytest
import requests

from bot import local_market as lm
from bot.report import build_local_section

AS_OF = date(2026, 10, 30)
ROWS = [
    {"fecha": "2026-10-28", "venta": 1600.0},
    {"fecha": "2026-10-29", "venta": 1665.0},
    {"fecha": "2026-10-30", "venta": 1650.0},
    {"fecha": "2026-10-31", "venta": 1700.0},
]
DOLLARS = [{"casa": "contadoconliqui", "label": "CCL"}]


def test_last_two_ignores_later_dates_and_missing_values():
    assert lm.last_two(ROWS, "venta", AS_OF) == (1650.0, 1665.0)
    assert lm.last_two([{"fecha": "2026-10-30", "venta": None}, ROWS[0]], "venta", AS_OF) is None


def test_fetch_dollars_calculates_change(monkeypatch):
    monkeypatch.setattr(lm, "_fetch_rows", lambda path: ROWS)
    result = lm.fetch_dollars(DOLLARS, AS_OF)
    assert result[0]["value"] == 1650.0
    assert round(result[0]["change_pct"], 1) == -0.9


def test_fetch_failure_is_skipped(monkeypatch, caplog):
    def fail(path):
        raise requests.ConnectionError("sin red")

    monkeypatch.setattr(lm, "_fetch_rows", fail)
    assert lm.fetch_dollars(DOLLARS, AS_OF) == []
    assert lm.fetch_country_risk(AS_OF) is None
    assert "riesgo país" in caplog.text


def test_country_risk_change(monkeypatch):
    rows = [{"fecha": "2026-10-29", "valor": 800}, {"fecha": "2026-10-30", "valor": 787}]
    monkeypatch.setattr(lm, "_fetch_rows", lambda path: rows)
    assert lm.fetch_country_risk(AS_OF) == {"value": 787.0, "change": -13.0}
    monkeypatch.setattr(lm, "_fetch_rows", lambda path: rows[:1])
    assert lm.fetch_country_risk(AS_OF) is None


def test_fetch_rows_calls_the_api(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return ROWS

    urls = []

    def fake_get(url, headers, timeout):
        urls.append(url)
        return Response()

    monkeypatch.setattr(lm.requests, "get", fake_get)
    assert lm._fetch_rows("finanzas/x") == ROWS
    assert urls == [f"{lm.API_URL}/finanzas/x"]


def test_panel_is_sorted_and_skips_missing(price_frame):
    prices = {"A.BA": price_frame(-0.02), "B.BA": price_frame(0.03, seed=1)}
    panel = [{"symbol": s, "label": s} for s in ["A.BA", "B.BA", "FALTA.BA"]]
    assert [m["label"] for m in lm.panel_moves(prices, panel)] == ["B.BA", "A.BA"]


class BymaResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": self.data}


def test_fetch_merval_prefers_sp_merval(monkeypatch):
    rows = [
        {"symbol": "M", "price": 990.0, "previousClosingPrice": 1000.0},
        {"symbol": "MMSCI", "price": 5.0, "previousClosingPrice": 5.0},
    ]
    monkeypatch.setattr(lm.requests, "post", lambda *a, **k: BymaResponse(rows))
    merval = lm.fetch_merval()
    assert merval["label"] == "Merval"
    assert round(merval["ret_pct"], 1) == -1.0


def test_fetch_merval_uses_msci_when_sp_is_zero(monkeypatch):
    rows = [
        {"symbol": "M", "price": 0, "previousClosingPrice": 0},
        {"symbol": "MMSCI", "price": 92079.66, "previousClosingPrice": 94529.98},
    ]
    monkeypatch.setattr(lm.requests, "post", lambda *a, **k: BymaResponse(rows))
    merval = lm.fetch_merval()
    assert merval["label"] == "MSCI Merval"
    assert round(merval["ret_pct"], 1) == -2.6


@pytest.mark.parametrize(
    "rows",
    [
        [{"symbol": "G", "price": 1, "previousClosingPrice": 1}],
        [{"symbol": "M", "price": 0, "previousClosingPrice": 0}],
        [{"symbol": "M"}],
        [{"symbol": "M", "price": "x", "previousClosingPrice": 1}],
    ],
)
def test_fetch_merval_without_usable_data(monkeypatch, rows):
    monkeypatch.setattr(lm.requests, "post", lambda *a, **k: BymaResponse(rows))
    assert lm.fetch_merval() is None


def test_fetch_merval_survives_network_errors(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("sin red")

    monkeypatch.setattr(lm.requests, "post", fail)
    assert lm.fetch_merval() is None


def test_merval_in_dollars():
    dollars = [{"label": "CCL", "value": 1000, "change_pct": 1.0}]
    summary = lm.merval_summary({"value": 1.0, "ret_pct": 2.0}, dollars, "CCL")
    assert round(summary["usd_ret_pct"], 2) == 0.99
    assert lm.merval_summary({"value": 1.0, "ret_pct": 2.0}, [], "CCL")["usd_ret_pct"] is None
    assert lm.merval_summary(None, dollars, "CCL") is None


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(lm, "fetch_dollars", lambda cfg, as_of: [])
    monkeypatch.setattr(lm, "fetch_country_risk", lambda as_of: None)
    monkeypatch.setattr(lm, "fetch_merval", lambda: {"value": 1.0, "ret_pct": 1.0})


def test_build_uses_the_panel_session_date(offline, price_frame):
    cfg = {"panel": [{"symbol": "A.BA", "label": "A"}]}
    fallback = pd.Timestamp("2026-11-02")
    local = lm.build_local_market({"A.BA": price_frame()}, cfg, fallback)
    assert local["date"].date() == AS_OF
    assert local["merval"]["ret_pct"] == 1.0


def test_build_falls_back_to_report_date(offline):
    fallback = pd.Timestamp("2026-11-02")
    assert lm.build_local_market({}, {"panel": []}, fallback)["date"] == fallback


def test_build_without_config_or_date(offline):
    assert lm.build_local_market({}, {}, pd.Timestamp("2026-11-02")) is None
    assert lm.build_local_market({}, {"panel": []}, None) is None


def test_local_section_with_all_data():
    local = {
        "date": pd.Timestamp("2026-10-30"),
        "merval": {"ret_pct": -0.4, "usd_ret_pct": 0.5},
        "country_risk": {"value": 787.0, "change": -13.0},
        "dollars": [{"label": "CCL", "value": 1650.3, "change_pct": -0.9}],
        "panel": [
            {"label": "YPF", "ret_pct": 2.0},
            {"label": "Pampa", "ret_pct": 0.0},
            {"label": "Galicia", "ret_pct": -3.0},
        ],
        "top": 2,
    }
    text = "\n".join(build_local_section(local))
    assert "rueda del 30/10" in text
    assert "🔴 Merval -0.4% (en dólares CCL +0.5%)" in text
    assert "Riesgo país 787 (-13 puntos)" in text
    assert "CCL $1.650 (-0.9%)" in text
    assert "🟢 Suben: YPF +2.0%" in text
    assert "🔴 Bajan: Galicia -3.0%" in text


def test_local_section_without_data_says_so():
    assert "🟢 MSCI Merval +1.0%" in "\n".join(
        build_local_section(
            {"date": pd.Timestamp("2026-10-30"), "merval": {"label": "MSCI Merval", "ret_pct": 1.0}}
        )
    )
    text = "\n".join(build_local_section({"date": pd.Timestamp("2026-10-30")}))
    assert "Merval sin datos" in text
    assert "Riesgo" not in text
