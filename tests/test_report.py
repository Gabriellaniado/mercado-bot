from bot.report import build_market_analysis, build_report


def asset(**overrides):
    base = {
        "symbol": "INTC",
        "name": "Intel",
        "ret_pct": -28.6,
        "vol_ratio": 4.6,
        "tag": "[CEDEAR]",
        "reasons": ["RSI 25 (sobrevendido)"],
        "why": ["🧾 Contexto único"],
    }
    return {**base, **overrides}


def test_report_without_signals_still_renders():
    text = build_report("01/11/2026", [("S&P 500", 0.4)], [], [], None, {})
    assert "🟢 S&P 500 +0.4%" in text
    assert "Sin movimientos" in text
    assert "Ninguna señal" in text
    assert "no una recomendación" in text


def test_report_does_not_repeat_context_of_a_mover():
    text = build_report("30/10/2026", [("S&P 500", -1.8)], [asset()], [asset()], None, {})
    assert text.count("🧾 Contexto único") == 1
    assert "🔴 S&P 500 -1.8%" in text
    assert "volumen x4.6" in text


def test_report_shows_context_of_opportunity_only_asset():
    text = build_report("30/10/2026", [], [], [asset()], None, {})
    assert "🧾 Contexto único" in text


def test_low_volume_is_hidden():
    assert "volumen" not in build_report("x", [], [asset(vol_ratio=1.1)], [], None, {})


def test_narrative_and_sources_are_included():
    news = {
        "INTC": [
            {"title": "T1", "source": "Ámbito", "url": "https://a"},
            {"title": "T2", "source": "CNBC", "url": "https://b"},
        ],
        "AMD": [{"title": "T3", "source": "CNBC", "url": ""}],
    }
    text = build_report("x", [], [], [], "Resumen del día", news)
    assert "📝 Resumen\nResumen del día" in text
    assert "INTC (Ámbito): https://a" in text
    assert "https://b" not in text  # solo la primera fuente por activo
    assert "AMD" not in text  # sin URL no hay nada que enlazar


def test_market_analysis_with_rotation_and_trend():
    sectors = [
        {"label": "Software", "ret_1d": 2.0, "ret_5d": 1.0, "rel_1d": 2.0},
        {"label": "Semis", "ret_1d": -3.0, "ret_5d": 1.0, "rel_1d": -3.0},
    ]
    rotation = {
        "winner": "Software",
        "loser": "Semis",
        "winner_ret": 2.0,
        "loser_ret": -3.0,
        "z": 2.5,
        "gap_5d": -1.0,
    }
    text = "\n".join(build_market_analysis(sectors, [rotation]))
    assert "🟢 Software +2.0%" in text
    assert "🔴 Semis -3.0%" in text
    assert "de Semis (-3.0%) a Software (+2.0%)" in text
    assert "contra la tendencia" in text
    assert "ya venía a favor" in "\n".join(build_market_analysis(sectors, [{**rotation, "gap_5d": 1.0}]))


def test_market_analysis_without_rotation_or_sides():
    flat = [{"label": "A", "ret_1d": 0.0, "ret_5d": 0.0, "rel_1d": 0.0}]
    text = "\n".join(build_market_analysis(flat, []))
    assert "Sin señales claras" in text
    assert text.count("- Ninguno.") == 2


def test_brief_report_warns_about_ai_opinions():
    text = build_report("x", [], [], [], None, {}, brief=True)
    assert "opiniones generadas por IA" in text
    assert "no una recomendación" not in text
