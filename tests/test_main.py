import json
import sys

import pytest
import yaml

from bot import main


@pytest.fixture
def cfg():
    return {
        "signals": {
            "min_move_pct": 4.0,
            "z_threshold": 2.5,
            "min_move_pct_by_group": {},
            "rsi_oversold": 30,
            "near_52w_low_pct": 5.0,
            "min_drawdown_pct": 20.0,
            "max_movers": 3,
            "max_opportunities": 3,
            "max_news_symbols": 8,
        },
        "panorama": [{"symbol": "SPY", "label": "S&P 500"}],
        "market_analysis": {
            "benchmark": "SPY",
            "rotation_min_gap_pct": 1.5,
            "rotation_z": 2.0,
            "sectors": [{"symbol": "SMH", "label": "Semiconductores"}],
            "styles": [],
            "rotation_pairs": [],
            "industry_map": {"Semiconductors": "SMH"},
            "sector_map": {},
        },
        "local_market": {"panel": [{"symbol": "GGAL.BA", "label": "Galicia"}], "dollars": []},
        "cedears": ["INTC"],
        "feeds": [],
        "trusted_sources": ["cnbc"],
        "summary": {"model": "m", "max_tokens": 10},
    }


@pytest.fixture
def offline(monkeypatch, price_frame):
    """Reemplaza todo lo que usa internet por datos fijos."""
    prices = {
        "SPY": price_frame(-0.01),
        "SMH": price_frame(-0.02, seed=1),
        "INTC": price_frame(-0.20, seed=2),
        "GGAL.BA": price_frame(0.03, seed=4),
    }
    universe = [{"symbol": "INTC", "name": "Intel", "group": "S&P 500", "keywords": []}]
    monkeypatch.setattr(main, "build_universe", lambda cfg: universe)
    monkeypatch.setattr(main, "download_prices", lambda symbols: prices)
    monkeypatch.setattr(main, "market_cap", lambda symbol: 300e9)
    monkeypatch.setattr(main.local_market, "fetch_dollars", lambda cfg, as_of: [])
    monkeypatch.setattr(main.local_market, "fetch_country_risk", lambda as_of: None)
    monkeypatch.setattr(main.local_market, "fetch_merval", lambda: None)
    monkeypatch.setattr(main.news, "fetch_feed_items", lambda feeds: [])
    monkeypatch.setattr(
        main.news,
        "collect_news",
        lambda flagged, items, trusted: {
            "INTC": [{"title": "Intel se hunde", "source": "CNBC", "url": "https://cnbc.com/i"}]
        },
    )
    monkeypatch.setattr(main.fundamentals, "fetch_context", lambda symbol: {"industry": "Semiconductors"})
    monkeypatch.setattr(main.summarize, "summarize", lambda flagged, news, cfg: None)


def test_build_text_end_to_end(cfg, offline):
    text = main.build_text(cfg)
    assert "📊 Informe de mercado - 30/10/2026" in text
    assert "🔴 S&P 500 -1.0%" in text
    assert "🔴 INTC (Intel) -20.0%" in text
    assert "[CEDEAR]" in text
    assert "🏭 Semiconductores -2.0%: el movimiento es sobre todo propio" in text
    assert "📰 Intel se hunde (CNBC)" in text
    assert "🟢 Suben: Galicia +3.0%" in text


def test_build_text_without_prices_has_no_date(cfg, offline, monkeypatch):
    monkeypatch.setattr(main, "download_prices", lambda symbols: {})
    assert "sin fecha" in main.build_text(cfg)


def test_read_feeds_survives_errors(monkeypatch, caplog):
    def fail(feeds):
        raise RuntimeError("sin red")

    monkeypatch.setattr(main.news, "fetch_feed_items", fail)
    assert main.read_feeds([{"name": "x"}]) == []
    assert "No se pudieron leer los feeds" in caplog.text


def write_config(tmp_path, cfg):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return str(path)


def test_dry_run_prints_and_does_not_send(cfg, offline, monkeypatch, tmp_path, capsys):
    sent = []
    monkeypatch.setattr(main.telegram, "send", lambda text, html: sent.append(text))
    main.run(write_config(tmp_path, cfg), dry_run=True)
    assert sent == []
    assert "Informe de mercado" in capsys.readouterr().out


def test_run_sends_by_telegram(cfg, offline, monkeypatch, tmp_path, capsys):
    sent = []
    monkeypatch.setattr(main.telegram, "send", lambda text, html: sent.append((text, html)))
    text = main.run(write_config(tmp_path, cfg))
    assert sent == [(text, False)]
    assert capsys.readouterr().out == ""


def test_main_passes_command_line_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(main, "run", lambda path, dry_run, analysis: calls.append((path, dry_run, analysis)))
    monkeypatch.setattr(sys, "argv", ["bot", "--config", "otro.yaml", "--dry-run", "--analysis", "a.json"])
    main.main()
    assert calls == [("otro.yaml", True, "a.json")]


def test_real_config_is_consistent():
    cfg = main.load_config("config.yaml")
    market = cfg["market_analysis"]
    labeled = {item["symbol"] for item in market["sectors"] + market["styles"]}
    assert all(isinstance(symbol, str) for symbol in cfg["cedears"])
    assert len(cfg["cedears"]) == len(set(cfg["cedears"]))
    assert {symbol for pair in market["rotation_pairs"] for symbol in pair} <= labeled
    assert set(market["sector_map"].values()) | set(market["industry_map"].values()) <= labeled


def test_analysis_builds_the_final_html_report(cfg, offline, monkeypatch, tmp_path):
    analysis_file = tmp_path / "analisis.json"
    asset = {"recommendation": "vender", "confidence": "baja", "cause": "Caída", "source": "CNBC"}
    analysis_file.write_text(json.dumps({"assets": {"INTC": asset}}), encoding="utf-8")
    sent = []
    monkeypatch.setattr(main.telegram, "send", lambda text, html: sent.append((text, html)))
    text = main.run(write_config(tmp_path, cfg), analysis_path=str(analysis_file))
    assert sent == [(text, True)]
    assert "🔴 <b>VENDER</b> · confianza baja" in text
    assert "📰" not in text


def test_invalid_analysis_fails_before_downloading(cfg, monkeypatch, tmp_path):
    analysis_file = tmp_path / "analisis.json"
    analysis_file.write_text("{}", encoding="utf-8")

    def fail(symbols):
        raise AssertionError("no debería descargar precios")

    monkeypatch.setattr(main, "download_prices", fail)
    with pytest.raises(ValueError, match="assets"):
        main.run(write_config(tmp_path, cfg), analysis_path=str(analysis_file))
