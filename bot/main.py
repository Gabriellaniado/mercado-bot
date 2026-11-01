"""Punto de entrada: python -m bot.main [--dry-run]"""

from __future__ import annotations

import argparse
import logging
import sys

import yaml
from dotenv import load_dotenv

from bot import analysis, fundamentals, news, report, summarize, telegram
from bot.prices import download_prices
from bot.universe import build_universe

log = logging.getLogger("mercado-bot")


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file)


def read_feeds(feeds: list[dict]) -> list[dict]:
    """Un problema con los feeds no debe frenar el informe."""
    try:
        return news.fetch_feed_items(feeds)
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudieron leer los feeds: %s", exc)
        return []


def add_explanations(
    movers: list[dict],
    opportunities: list[dict],
    flagged: list[dict],
    headlines: dict[str, list[dict]],
    sectors: list[dict],
    market_cfg: dict,
) -> None:
    """Agrega a cada activo las líneas que explican por qué está en ese nivel."""
    why_by_symbol = {
        entry["symbol"]: fundamentals.explain(
            entry,
            fundamentals.fetch_context(entry["symbol"]),
            sectors,
            market_cfg.get("sector_map", {}),
            market_cfg.get("industry_map", {}),
            headlines.get(entry["symbol"], []),
        )
        for entry in flagged
    }
    for entry in movers + opportunities:
        entry["why"] = why_by_symbol.get(entry["symbol"], [])


def build_text(cfg: dict) -> str:
    """Corre el análisis completo y devuelve el texto del informe."""
    signals_cfg = cfg["signals"]
    market_cfg = cfg.get("market_analysis", {})

    universe = build_universe(cfg)
    symbols = analysis.required_symbols(universe, cfg)
    log.info("Descargando precios de %d activos...", len(symbols))
    prices = download_prices(symbols)

    panorama, last_date = analysis.build_panorama(prices, cfg.get("panorama", []))
    sectors, rotations = analysis.market_analysis(prices, market_cfg)
    movers, opportunities = analysis.classify_assets(
        universe, prices, signals_cfg, set(cfg.get("cedears", []))
    )
    flagged = analysis.unique_flagged(movers, opportunities, signals_cfg["max_news_symbols"])

    headlines = news.collect_news(flagged, read_feeds(cfg.get("feeds", [])), cfg["trusted_sources"])
    add_explanations(movers, opportunities, flagged, headlines, sectors, market_cfg)
    narrative = summarize.summarize(flagged, headlines, cfg["summary"])

    date_str = last_date.strftime("%d/%m/%Y") if last_date is not None else "sin fecha"
    return report.build_report(
        date_str, panorama, movers, opportunities, narrative, headlines, sectors, rotations
    )


def run(cfg_path: str = "config.yaml", dry_run: bool = False) -> str:
    text = build_text(load_config(cfg_path))
    if dry_run:
        print(text)
    else:
        telegram.send(text)
        log.info("Informe enviado por Telegram.")
    return text


def send_file(path: str) -> None:
    """Envía un informe ya redactado, por ejemplo con el resumen de la rutina diaria."""
    with open(path, encoding="utf-8") as file:
        text = file.read().strip()
    if not text:
        raise ValueError(f"El archivo está vacío: {path}")
    telegram.send(text)
    log.info("Informe enviado por Telegram.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Informe diario de mercado")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="imprime el informe sin enviarlo")
    parser.add_argument("--send-file", help="envía por Telegram un informe ya redactado y termina")
    args = parser.parse_args()

    # La consola de Windows puede no soportar los emojis del informe.
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.send_file:
        send_file(args.send_file)
    else:
        run(args.config, args.dry_run)


if __name__ == "__main__":
    main()
