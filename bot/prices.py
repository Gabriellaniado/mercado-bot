"""Descarga de precios desde Yahoo Finance."""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

MIN_HISTORY_DAYS = 30
MAX_STALE_DAYS = 5


def market_cap(symbol: str) -> float | None:
    """Capitalización en dólares, o None si Yahoo no la informa."""
    try:
        return yf.Ticker(symbol).fast_info["marketCap"]
    except Exception as exc:  # noqa: BLE001
        log.warning("Sin capitalización para %s: %s", symbol, type(exc).__name__)
        return None


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


def drop_stale(prices: dict[str, pd.DataFrame], max_days: int = MAX_STALE_DAYS) -> dict[str, pd.DataFrame]:
    """Saca los activos cuyos precios quedaron atrás, para no mostrar datos viejos como de hoy."""
    if not prices:
        return {}
    newest = max(frame.index[-1] for frame in prices.values())
    fresh = {s: f for s, f in prices.items() if (newest - f.index[-1]).days <= max_days}
    stale = sorted(set(prices) - set(fresh))
    if stale:
        log.warning("Precios desactualizados, los descarto: %s", ", ".join(stale))
    return fresh
