"""Informe final para Telegram: combina los datos del bot con el análisis de la rutina diaria."""

from __future__ import annotations

import json
from html import escape

RECOMMENDATIONS = {
    "comprar": "🟢 <b>COMPRAR</b>",
    "mantener": "🟡 <b>MANTENER</b>",
    "vender": "🔴 <b>VENDER</b>",
}
NO_RECOMMENDATION = "⚪ <b>SIN RECOMENDACIÓN</b>"
CONFIDENCE_LEVELS = ("alta", "media", "baja")
DIVIDER = "━━━━━━━━━━━━━━"
DISCLAIMER = (
    "⚠️ <i>Recomendaciones y precios objetivo generados por IA. Pueden tener errores: verificalos.</i>"
)


def load_analysis(path: str) -> dict:
    """Lee el análisis y falla con un mensaje claro si la ficha está mal completada."""
    with open(path, encoding="utf-8") as file:
        analysis = json.load(file)
    if not isinstance(analysis, dict) or not isinstance(analysis.get("assets"), dict):
        raise ValueError("El análisis debe tener un objeto 'assets'.")
    for symbol, asset in analysis["assets"].items():
        recommendation = asset.get("recommendation")
        if recommendation is not None and recommendation not in RECOMMENDATIONS:
            raise ValueError(f"{symbol}: recomendación inválida: {recommendation}")
        confidence = asset.get("confidence")
        if recommendation and confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"{symbol}: confianza inválida: {confidence}")
        target = asset.get("target")
        if target is not None and (not isinstance(target, (int, float)) or target <= 0):
            raise ValueError(f"{symbol}: precio objetivo inválido: {target}")
        if target is not None and not asset.get("target_basis"):
            raise ValueError(f"{symbol}: falta cómo se calculó el precio objetivo.")
    return analysis


def pct(value: float) -> str:
    return f"{value:+.1f}%".replace(".", ",")


def dot(value: float) -> str:
    return "🟢" if value >= 0 else "🔴"


def _money(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def _quote(text: str | None) -> list[str]:
    return [f"<i>{escape(text.strip())}</i>"] if text and text.strip() else []


def _panorama_section(panorama: list[tuple[str, float]], comment: str | None) -> list[str]:
    if not panorama:
        return []
    rows = [f"{dot(ret)} {escape(label)} <b>{pct(ret)}</b>" for label, ret in panorama]
    return ["🌎 <b>GLOBAL</b>", *rows, *_quote(comment), ""]


def _sectors_section(sectors: list[dict], rotations: list[dict], top: int = 2) -> list[str]:
    if not sectors:
        return []
    out = ["🔎 <b>SECTORES</b>"]
    best = [f"{escape(s['label'])} {pct(s['ret_1d'])}" for s in sectors[:top] if s["rel_1d"] > 0]
    worst = [f"{escape(s['label'])} {pct(s['ret_1d'])}" for s in reversed(sectors[-top:]) if s["rel_1d"] < 0]
    if best:
        out.append("🟢 " + " · ".join(best))
    if worst:
        out.append("🔴 " + " · ".join(worst))
    if rotations:
        first = rotations[0]
        out.append(f"🔀 Posible rotación: {escape(first['loser'])} → {escape(first['winner'])}")
    out.append("")
    return out


def _local_section(local: dict | None, comment: str | None) -> list[str]:
    if not local:
        return []
    out = [f"🇦🇷 <b>LOCAL</b> · {local['date'].strftime('%d/%m')}"]
    merval = local.get("merval")
    if merval:
        usd = merval.get("usd_ret_pct")
        in_usd = f" · en USD {pct(usd)}" if usd is not None else ""
        label = escape(merval.get("label", "Merval"))
        out.append(f"{dot(merval['ret_pct'])} {label} <b>{pct(merval['ret_pct'])}</b>{in_usd}")
    risk = local.get("country_risk")
    if risk:
        out.append(f"🌡️ Riesgo país <b>{risk['value']:.0f}</b> ({risk['change']:+.0f})")
    if local.get("dollars"):
        parts = [f"{escape(d['label'])} ${_money(d['value'])}" for d in local["dollars"]]
        out.append("💵 " + " · ".join(parts))
    panel, top = local.get("panel", []), local.get("top", 3)
    best = [f"{escape(m['label'])} {pct(m['ret_pct'])}" for m in panel[:top] if m["ret_pct"] > 0]
    worst = [f"{escape(m['label'])} {pct(m['ret_pct'])}" for m in reversed(panel[-top:]) if m["ret_pct"] < 0]
    if best:
        out.append("🟢 " + " · ".join(best))
    if worst:
        out.append("🔴 " + " · ".join(worst))
    out += _quote(comment)
    out.append("")
    return out


def _asset_block(entry: dict, asset: dict | None) -> list[str]:
    cedear = " · CEDEAR" if entry.get("tag") else ""
    title = f"{dot(entry['ret_pct'])} <b>{escape(entry['symbol'])}</b> {pct(entry['ret_pct'])}{cedear}"
    out = [title]
    if entry.get("side") and entry.get("reasons"):
        word = "compra" if entry["side"] == "compra" else "venta"
        out.append(f"⚡ Señal de {word}: " + escape("; ".join(entry["reasons"])))
    if not asset:
        return [*out, NO_RECOMMENDATION, "<i>Sin análisis para este activo.</i>", ""]

    verdict = RECOMMENDATIONS.get(asset.get("recommendation"), NO_RECOMMENDATION)
    if asset.get("recommendation"):
        verdict += f" · confianza {asset['confidence']}"
    out.append(verdict)
    if asset.get("target") is not None:
        out.append(f"🎯 Objetivo US${asset['target']:.2f}".replace(".", ",") + " (estimación propia)")
        out += _quote(f"Cálculo: {asset['target_basis']}")
    if asset.get("cause"):
        source = f" ({escape(asset['source'])})" if asset.get("source") else ""
        out.append(f"📌 {escape(asset['cause'])}{source}")
    out.append("")
    return out


def build_final_report(
    date_str: str,
    panorama: list[tuple[str, float]],
    sectors: list[dict],
    rotations: list[dict],
    local: dict | None,
    flagged: list[dict],
    analysis: dict,
) -> str:
    """Arma el mensaje en HTML de Telegram. Todo el texto externo queda escapado."""
    out = [f"📊 <b>INFORME DE MERCADO</b> · {escape(date_str)}", DIVIDER, ""]
    out += _panorama_section(panorama, analysis.get("global"))
    out += _sectors_section(sectors, rotations)
    out += _local_section(local, analysis.get("local"))
    out += ["💼 <b>EMPRESAS Y RECOMENDACIONES</b>", DIVIDER]
    if flagged:
        # Primero lo accionable (comprar/vender), después mantener y lo que no tiene análisis.
        order = {"comprar": 0, "vender": 0, "mantener": 1}

        def rank(entry: dict) -> int:
            asset = analysis["assets"].get(entry["symbol"]) or {}
            return order.get(asset.get("recommendation"), 2)

        for entry in sorted(flagged, key=rank):
            out += _asset_block(entry, analysis["assets"].get(entry["symbol"]))
    else:
        out += ["Sin movimientos ni activos para revisar hoy.", ""]
    out.append(DISCLAIMER)
    return "\n".join(out)
