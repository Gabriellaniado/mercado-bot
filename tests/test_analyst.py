import json

import pandas as pd
import pytest

from bot import analyst

ENTRY = {"symbol": "INTC", "ret_pct": -28.6, "tag": "[CEDEAR]"}
ASSET = {
    "recommendation": "mantener",
    "confidence": "media",
    "target": 72.5,
    "target_basis": "P/E de 30 sobre ganancia estimada",
    "cause": "Previsiones flojas & flujo negativo",
    "source": "Ámbito",
}
LOCAL = {
    "date": pd.Timestamp("2026-10-30"),
    "merval": {"label": "MSCI Merval", "ret_pct": -2.6, "usd_ret_pct": -1.7},
    "country_risk": {"value": 787.0, "change": 46.0},
    "dollars": [{"label": "CCL", "value": 1650.3}],
    "panel": [{"label": "YPF", "ret_pct": 1.0}, {"label": "TGS", "ret_pct": -5.5}],
    "top": 1,
}
SECTORS = [
    {"label": "Energía", "ret_1d": 1.9, "rel_1d": 3.7},
    {"label": "Semis", "ret_1d": -7.0, "rel_1d": -5.2},
]


def write(tmp_path, data):
    path = tmp_path / "analisis.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_load_valid_analysis(tmp_path):
    assert analyst.load_analysis(write(tmp_path, {"assets": {"INTC": ASSET}}))["assets"]["INTC"] == ASSET


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({}, "assets"),
        ({"assets": {"A": {"recommendation": "aguantar"}}}, "recomendación"),
        ({"assets": {"A": {"recommendation": "comprar"}}}, "confianza"),
        ({"assets": {"A": {**ASSET, "target": -1}}}, "precio objetivo"),
        ({"assets": {"A": {**ASSET, "target": "alto"}}}, "precio objetivo"),
        ({"assets": {"A": {**ASSET, "target_basis": ""}}}, "se calculó"),
    ],
)
def test_load_rejects_invalid_analysis(tmp_path, data, message):
    with pytest.raises(ValueError, match=message):
        analyst.load_analysis(write(tmp_path, data))


def build(**overrides):
    args = {
        "date_str": "30/10/2026",
        "panorama": [("S&P 500", -1.8), ("Petróleo", 2.1)],
        "sectors": SECTORS,
        "rotations": [{"loser": "Tecnología", "winner": "Energía"}],
        "local": LOCAL,
        "flagged": [ENTRY],
        "analysis": {"global": "Cae tecnología.", "local": "Baja en pesos.", "assets": {"INTC": ASSET}},
    }
    return analyst.build_final_report(**{**args, **overrides})


def test_final_report_has_clear_sections_and_recommendation():
    text = build()
    assert "📊 <b>INFORME DE MERCADO</b> · 30/10/2026" in text
    assert "🔴 S&amp;P 500 <b>-1,8%</b>" in text
    assert "<i>Cae tecnología.</i>" in text
    assert "🟢 Energía +1,9%" in text
    assert "🔀 Posible rotación: Tecnología → Energía" in text
    assert "🔴 MSCI Merval <b>-2,6%</b> · en USD -1,7%" in text
    assert "Riesgo país <b>787</b> (+46)" in text
    assert "CCL $1.650" in text
    assert "🟢 YPF +1,0%" in text
    assert "🔴 TGS -5,5%" in text
    assert "🔴 <b>INTC</b> -28,6% · CEDEAR" in text
    assert "🟡 <b>MANTENER</b> · confianza media" in text
    assert "🎯 Objetivo US$72,50 (estimación propia)" in text
    assert "Cálculo: P/E de 30" in text
    assert "generados por IA" in text


def test_external_text_is_escaped():
    text = build()
    assert "Previsiones flojas &amp; flujo negativo (Ámbito)" in text
    hostile = {**ASSET, "cause": "<script>x</script>"}
    assert "<script>" not in build(analysis={"assets": {"INTC": hostile}})


def test_asset_without_analysis_says_so():
    assert "Sin análisis para este activo" in build(analysis={"assets": {}})


def test_explicit_lack_of_recommendation():
    asset = {"recommendation": None, "cause": "Sin causa confirmada"}
    text = build(analysis={"assets": {"INTC": asset}})
    assert "⚪ <b>SIN RECOMENDACIÓN</b>" in text
    assert "confianza" not in text
    assert "🎯" not in text


def test_recommendation_without_target_or_cause():
    asset = {"recommendation": "comprar", "confidence": "baja"}
    text = build(analysis={"assets": {"INTC": asset}})
    assert "🟢 <b>COMPRAR</b> · confianza baja" in text
    assert "🎯" not in text
    assert "📌" not in text


def test_empty_sections_are_omitted():
    text = build(panorama=[], sectors=[], rotations=[], local=None, flagged=[])
    assert "GLOBAL" not in text
    assert "SECTORES" not in text
    assert "LOCAL" not in text
    assert "Sin movimientos ni activos" in text


def test_local_section_without_optional_data():
    text = build(local={"date": pd.Timestamp("2026-10-30")})
    assert "🇦🇷 <b>LOCAL</b> · 30/10" in text
    assert "Riesgo" not in text


def test_merval_without_dollars_and_blank_comment():
    local = {**LOCAL, "merval": {"ret_pct": 1.0, "usd_ret_pct": None}}
    text = build(local=local, analysis={"local": "  ", "assets": {}})
    assert "🟢 Merval <b>+1,0%</b>" in text
    assert "en USD" not in text
    assert "<i>  </i>" not in text


def test_no_sector_side_when_nothing_beats_the_index():
    flat = [{"label": "A", "ret_1d": 0.0, "rel_1d": 0.0}]
    text = build(sectors=flat, rotations=[])
    assert "🔎 <b>SECTORES</b>\n\n" in text


def test_signal_line_is_shown_for_flagged_asset():
    entry = {**ENTRY, "side": "venta", "reasons": ["RSI 78 (sobrecomprado)"]}
    text = build(flagged=[entry])
    assert "⚡ Señal de venta: RSI 78 (sobrecomprado)" in text


def test_actionable_recommendations_come_first():
    flagged = [
        {"symbol": "AAA", "ret_pct": 1.0, "tag": ""},
        {"symbol": "BBB", "ret_pct": 1.0, "tag": ""},
        {"symbol": "CCC", "ret_pct": 1.0, "tag": ""},
    ]
    assets = {
        "AAA": {"recommendation": "mantener", "confidence": "baja"},
        "CCC": {"recommendation": "comprar", "confidence": "alta"},
    }
    text = build(flagged=flagged, analysis={"assets": assets})
    assert text.index("<b>CCC</b>") < text.index("<b>AAA</b>") < text.index("<b>BBB</b>")
