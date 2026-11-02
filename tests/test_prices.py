import numpy as np
import pandas as pd

from bot import prices


def test_multiple_tickers_keep_only_those_with_enough_history(monkeypatch, price_frame, caplog):
    good = price_frame()
    empty = price_frame()
    empty["Close"] = np.nan
    data = pd.concat({"AAPL": good, "ERJ": empty}, axis=1)
    monkeypatch.setattr(prices.yf, "download", lambda chunk, **kwargs: data)
    result = prices.download_prices(["AAPL", "ERJ"])
    assert list(result) == ["AAPL"]
    assert "Sin precios suficientes para: ERJ" in caplog.text


def test_single_ticker_has_flat_columns(monkeypatch, price_frame):
    monkeypatch.setattr(prices.yf, "download", lambda chunk, **kwargs: price_frame())
    assert list(prices.download_prices(["AAPL"])) == ["AAPL"]


def test_missing_columns_are_skipped(monkeypatch):
    monkeypatch.setattr(prices.yf, "download", lambda chunk, **kwargs: pd.DataFrame())
    assert prices.download_prices(["AAPL"]) == {}


def test_downloads_in_batches(monkeypatch, price_frame):
    calls = []

    def fake_download(chunk, **kwargs):
        calls.append(chunk)
        return price_frame()

    monkeypatch.setattr(prices.yf, "download", fake_download)
    prices.download_prices(["A", "B", "C"], batch=2)
    assert calls == [["A", "B"], ["C"]]


def test_market_cap_reads_yahoo_and_survives_errors(monkeypatch):
    class Ticker:
        def __init__(self, symbol):
            self.fast_info = {"marketCap": 5.0} if symbol == "OK" else {}

    monkeypatch.setattr(prices.yf, "Ticker", Ticker)
    assert prices.market_cap("OK") == 5.0
    assert prices.market_cap("MAL") is None


def test_drop_stale_removes_only_old_prices(price_frame, caplog):
    old = price_frame()
    old.index = old.index - pd.Timedelta(days=14)
    result = prices.drop_stale({"NUEVO": price_frame(), "VIEJO": old})
    assert list(result) == ["NUEVO"]
    assert "VIEJO" in caplog.text
    assert prices.drop_stale({}) == {}


def test_drop_stale_tolerates_a_long_weekend(price_frame):
    recent = price_frame()
    recent.index = recent.index - pd.Timedelta(days=4)
    assert set(prices.drop_stale({"A": price_frame(), "B": recent})) == {"A", "B"}


def test_market_cap_retries_before_giving_up(monkeypatch):
    calls = []

    class Ticker:
        def __init__(self, symbol):
            calls.append(symbol)
            self.fast_info = {"marketCap": 7.0} if len(calls) == 3 else {}

    monkeypatch.setattr(prices.yf, "Ticker", Ticker)
    monkeypatch.setattr(prices.time, "sleep", lambda s: None)
    assert prices.market_cap("X") == 7.0
    assert len(calls) == 3
