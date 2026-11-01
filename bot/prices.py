"""Descarga de precios desde Yahoo Finance."""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

MIN_HISTORY_DAYS = 30


def download_prices(symbols: list[str], batch: int = 100) -> dict[str, pd.DataFrame]:
    """Devuelve {ticker: DataFrame con Close y Volume} para los que tienen historia suficiente."""
    prices: dict[str, pd.DataFrame] = {}
    for start in range(0, len(symbols), batch):
        chunk = symbols[start : start + batch]
        data = yf.download(
            chunk,
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        for symbol in chunk:
            frame = data[symbol] if isinstance(data.columns, pd.MultiIndex) and symbol in data else data
            try:
                frame = frame[["Close", "Volume"]].dropna(subset=["Close"])
            except KeyError:
                continue
            if len(frame) >= MIN_HISTORY_DAYS:
                prices[symbol] = frame

    missing = sorted(set(symbols) - set(prices))
    if missing:
        log.warning("Sin precios suficientes para: %s", ", ".join(missing))
    return prices
