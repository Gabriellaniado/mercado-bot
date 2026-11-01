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
