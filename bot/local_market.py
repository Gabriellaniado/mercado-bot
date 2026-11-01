"""Mercado argentino: dólares, riesgo país, Merval y panel de acciones en pesos."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import requests

from bot import signals

log = logging.getLogger(__name__)

API_URL = "https://api.argentinadatos.com/v1"
BYMA_INDEX_URL = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/index-price"
# BYMA publica el S&P Merval en cero en su servicio gratuito; el MSCI Merval sí trae datos.
MERVAL_INDEXES = (("M", "Merval"), ("MMSCI", "MSCI Merval"))


def _fetch_rows(path: str) -> list[dict]:
    response = requests.get(f"{API_URL}/{path}", headers={"User-Agent": "mercado-bot/1.0"}, timeout=20)
    response.raise_for_status()
    return response.json()


def last_two(rows: list[dict], field: str, as_of: date) -> tuple[float, float] | None:
    """Último valor hasta la fecha de la rueda y el del día hábil anterior que tenga datos."""
    valid = sorted(
        (row["fecha"], float(row[field]))
        for row in rows
        if row.get(field) is not None and row["fecha"] <= as_of.isoformat()
    )
    if len(valid) < 2:
        return None
    return valid[-1][1], valid[-2][1]


def fetch_dollars(dollars_cfg: list[dict], as_of: date) -> list[dict]:
    """Cotización de venta de cada dólar y su variación. Si uno falla, sigue con los demás."""
    result = []
    for item in dollars_cfg:
        try:
            values = last_two(_fetch_rows(f"cotizaciones/dolares/{item['casa']}"), "venta", as_of)
        except (requests.RequestException, ValueError, KeyError) as exc:
            log.warning("Sin datos del dólar %s: %s", item["label"], type(exc).__name__)
            continue
        if values:
            last, previous = values
            result.append({"label": item["label"], "value": last, "change_pct": (last / previous - 1) * 100})
    return result


def fetch_country_risk(as_of: date) -> dict | None:
    try:
        values = last_two(_fetch_rows("finanzas/indices/riesgo-pais"), "valor", as_of)
    except (requests.RequestException, ValueError, KeyError) as exc:
        log.warning("Sin datos de riesgo país: %s", type(exc).__name__)
        return None
    if not values:
        return None
    return {"value": values[0], "change": values[0] - values[1]}


def panel_moves(prices: dict[str, pd.DataFrame], panel: list[dict]) -> list[dict]:
    """Variación de las acciones locales con datos, de mayor a menor."""
    moves = []
    for item in panel:
        frame = prices.get(item["symbol"])
        sig = signals.compute_signals(item["symbol"], frame) if frame is not None else None
        if sig:
            moves.append({"label": item["label"], "ret_pct": sig["ret_pct"], "date": sig["date"]})
    return sorted(moves, key=lambda move: move["ret_pct"], reverse=True)


def fetch_merval() -> dict | None:
    """Primer índice Merval con datos en BYMA. Yahoo lo tiene desactualizado."""
    try:
        response = requests.post(
            BYMA_INDEX_URL,
            json={},
            headers={"Content-Type": "application/json", "User-Agent": "mercado-bot/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        rows = {item["symbol"]: item for item in response.json()["data"]}
        for symbol, label in MERVAL_INDEXES:
            row = rows.get(symbol, {})
            price, previous = float(row.get("price") or 0), float(row.get("previousClosingPrice") or 0)
            if price > 0 and previous > 0:
                return {"label": label, "value": price, "ret_pct": (price / previous - 1) * 100}
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        log.warning("Sin datos del Merval: %s", type(exc).__name__)
        return None
    log.warning("BYMA no informó ningún índice Merval.")
    return None


def merval_summary(merval: dict | None, dollars: list[dict], ccl_label: str) -> dict | None:
    """Agrega al Merval en pesos su variación aproximada en dólares, si hay CCL."""
    if not merval:
        return None
    ccl = next((item for item in dollars if item["label"] == ccl_label), None)
    usd_ret = None
    if ccl:
        usd_ret = ((1 + merval["ret_pct"] / 100) / (1 + ccl["change_pct"] / 100) - 1) * 100
    return {**merval, "usd_ret_pct": usd_ret}


def build_local_market(prices: dict[str, pd.DataFrame], cfg: dict, fallback_date) -> dict | None:
    """Junta todos los datos locales usando la fecha de la última rueda argentina."""
    if not cfg:
        return None
    panel = panel_moves(prices, cfg.get("panel", []))
    session = max((move["date"] for move in panel), default=fallback_date)
    if session is None:
        return None

    as_of = session.date()
    dollars = fetch_dollars(cfg.get("dollars", []), as_of)
    return {
        "date": session,
        "merval": merval_summary(fetch_merval(), dollars, cfg.get("ccl_label", "CCL")),
        "dollars": dollars,
        "country_risk": fetch_country_risk(as_of),
        "panel": panel,
        "top": cfg.get("top", 3),
    }
