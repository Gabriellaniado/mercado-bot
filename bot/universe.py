"""Arma la lista de activos a monitorear."""

from __future__ import annotations

import io
import logging

import pandas as pd
import requests

log = logging.getLogger(__name__)

WIKI_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def fetch_sp500() -> list[dict]:
    """Descarga los componentes actuales del S&P 500 desde Wikipedia."""
    resp = requests.get(WIKI_SP500, headers={"User-Agent": "mercado-bot/1.0"}, timeout=20)
    resp.raise_for_status()
    table = pd.read_html(io.StringIO(resp.text))[0]
    return [
        {
            "symbol": str(row["Symbol"]).replace(".", "-"),  # BRK.B -> BRK-B (formato Yahoo)
            "name": str(row["Security"]),
            "group": "S&P 500",
            "keywords": [],
        }
        for _, row in table.iterrows()
    ]


def build_universe(cfg: dict) -> list[dict]:
    items: list[dict] = []
    try:
        items += fetch_sp500()
        log.info("S&P 500: %d activos", len(items))
    except Exception as exc:  # noqa: BLE001 - queremos seguir con la lista de respaldo
        log.warning("No se pudo bajar el S&P 500 (%s). Uso la lista de respaldo.", exc)
        items += [
            {"symbol": e["symbol"], "name": e["name"], "group": "S&P 500", "keywords": []}
            for e in cfg.get("sp500_fallback", [])
        ]

    for group, entries in cfg.get("groups", {}).items():
        for e in entries:
            items.append(
                {
                    "symbol": e["symbol"],
                    "name": e.get("name", e["symbol"]),
                    "group": group,
                    "keywords": e.get("keywords", []),
                }
            )

    seen: set[str] = set()
    unique = []
    for it in items:
        if it["symbol"] not in seen:
            seen.add(it["symbol"])
            unique.append(it)
    return unique
