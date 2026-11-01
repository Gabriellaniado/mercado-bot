"""Convierte precios en las secciones del informe. No hace llamadas de red."""

from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd

from bot import signals

log = logging.getLogger(__name__)

SP500_GROUP = "S&P 500"


def required_symbols(universe: list[dict], cfg: dict) -> list[str]:
    """Todos los tickers que hay que descargar para armar el informe."""
    market = cfg.get("market_analysis", {})
    symbols = {item["symbol"] for item in universe}
    symbols |= {item["symbol"] for item in cfg.get("panorama", [])}
    symbols |= {item["symbol"] for item in market.get("sectors", []) + market.get("styles", [])}
    symbols |= {item["symbol"] for item in cfg.get("local_market", {}).get("panel", [])}
    if market:
        symbols.add(market["benchmark"])
    return sorted(symbols)


def build_panorama(
    prices: dict[str, pd.DataFrame], panorama_cfg: list[dict]
) -> tuple[list[tuple[str, float]], pd.Timestamp | None]:
    """Devuelve [(etiqueta, variación del día)] y la fecha de la última rueda."""
    panorama, last_date = [], None
    for item in panorama_cfg:
        frame = prices.get(item["symbol"])
        sig = signals.compute_signals(item["symbol"], frame) if frame is not None else None
        if sig:
            panorama.append((item["label"], sig["ret_pct"]))
            last_date = sig["date"]
    return panorama, last_date


def market_analysis(prices: dict[str, pd.DataFrame], cfg: dict) -> tuple[list[dict], list[dict]]:
    """Sectores contra el índice y posibles rotaciones entre los pares configurados."""
    if not cfg:
        return [], []
    closes = {symbol: frame["Close"] for symbol, frame in prices.items()}
    sectors = signals.sector_moves(closes, cfg.get("sectors", []), cfg["benchmark"])
    labels = {item["symbol"]: item["label"] for item in cfg.get("sectors", []) + cfg.get("styles", [])}
    rotations = []
    for first, second in cfg.get("rotation_pairs", []):
        if first not in closes or second not in closes:
            log.warning("Sin precios para el par %s/%s, lo salto.", first, second)
            continue
        found = signals.detect_rotation(
            closes[first], closes[second], cfg["rotation_min_gap_pct"], cfg["rotation_z"]
        )
        if found:
            winner, loser = (first, second) if found["a_wins"] else (second, first)
            rotations.append({**found, "winner": labels[winner], "loser": labels[loser]})
    rotations.sort(key=lambda rotation: rotation["z"], reverse=True)
    return sectors, rotations


def _take_important(entries: list[dict], limit: int, is_important: Callable[[dict], bool]) -> list[dict]:
    """Recorre en orden y frena al llegar al límite, para consultar la menor cantidad posible."""
    picked: list[dict] = []
    for entry in entries:
        if len(picked) == limit:
            break
        if is_important(entry):
            picked.append(entry)
    return picked


def classify_assets(
    universe: list[dict],
    prices: dict[str, pd.DataFrame],
    signals_cfg: dict,
    cedears: set[str],
    get_market_cap: Callable[[str], float | None] = lambda symbol: None,
) -> tuple[list[dict], list[dict]]:
    """Separa los grandes movimientos y los activos con CEDEAR a revisar, ya ordenados y recortados.

    Las empresas del S&P 500 por debajo de la capitalización mínima quedan afuera. Si Yahoo no
    informa el dato se mantienen, para que una falla no vacíe el informe.
    """
    min_cap = signals_cfg.get("min_market_cap_usd_bn", 0) * 1e9
    caps: dict[str, float | None] = {}

    def is_important(entry: dict) -> bool:
        if entry["group"] != SP500_GROUP or not min_cap:
            return True
        symbol = entry["symbol"]
        if symbol not in caps:
            caps[symbol] = get_market_cap(symbol)
        return caps[symbol] is None or caps[symbol] >= min_cap

    movers, opportunities = [], []
    for item in universe:
        symbol = item["symbol"]
        frame = prices.get(symbol)
        sig = signals.compute_signals(symbol, frame) if frame is not None else None
        if not sig:
            continue
        entry = {**item, **sig, "tag": "[CEDEAR]" if symbol in cedears else ""}
        if signals.is_big_move(sig, signals_cfg, item["group"]):
            movers.append(entry)
        if symbol in cedears:
            reasons = signals.opportunity_reasons(sig, signals_cfg)
            if reasons:
                opportunities.append({**entry, "reasons": reasons})

    # Primero lo que se puede operar con CEDEAR; dentro de cada grupo, lo más inusual.
    movers.sort(key=lambda m: (m["symbol"] in cedears, abs(m["z"])), reverse=True)
    opportunities.sort(key=lambda o: o["dist_high_pct"])
    return (
        _take_important(movers, signals_cfg["max_movers"], is_important),
        _take_important(opportunities, signals_cfg["max_opportunities"], is_important),
    )


def unique_flagged(movers: list[dict], opportunities: list[dict], limit: int) -> list[dict]:
    """Activos marcados sin repetir, para no buscar dos veces sus noticias y su contexto."""
    by_symbol: dict[str, dict] = {}
    for entry in movers + opportunities:
        by_symbol.setdefault(entry["symbol"], entry)
    return list(by_symbol.values())[:limit]
