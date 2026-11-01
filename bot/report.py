"""Armado del texto del informe. Funciones puras."""

from __future__ import annotations

DISCLAIMER = "⚠️ Son señales automáticas para revisar, no una recomendación de inversión."


def fmt_pct(x: float) -> str:
    return f"{x:+.1f}%"


def trend(x: float) -> str:
    return "🟢" if x >= 0 else "🔴"


def build_market_analysis(sectors: list[dict], rotations: list[dict], top: int = 3) -> list[str]:
    def row(s: dict) -> str:
        return f"{s['label']} {fmt_pct(s['ret_1d'])} (5 días {fmt_pct(s['ret_5d'])})"

    out = ["🔎 Análisis de mercado", "Mejor que el S&P 500:"]
    out += [f"🟢 {row(s)}" for s in sectors[:top] if s["rel_1d"] > 0] or ["- Ninguno."]
    out.append("Peor que el S&P 500:")
    out += [f"🔴 {row(s)}" for s in reversed(sectors[-top:]) if s["rel_1d"] < 0] or ["- Ninguno."]
    for r in rotations:
        persistence = (
            f"ya venía a favor en 5 días ({r['gap_5d']:+.1f}%)"
            if r["gap_5d"] > 0
            else f"contra la tendencia de 5 días ({r['gap_5d']:+.1f}%)"
        )
        out.append(
            f"🔀 Posible rotación: de {r['loser']} ({fmt_pct(r['loser_ret'])}) a {r['winner']} "
            f"({fmt_pct(r['winner_ret'])}). Brecha {r['z']:.1f} veces la habitual; {persistence}."
        )
    if not rotations:
        out.append("🔀 Sin señales claras de rotación hoy.")
    return out


def build_report(
    date_str: str,
    panorama: list[tuple[str, float]],
    movers: list[dict],
    opportunities: list[dict],
    narrative: str | None,
    news: dict[str, list[dict]],
    sectors: list[dict] | None = None,
    rotations: list[dict] | None = None,
) -> str:
    out = [f"📊 Informe de mercado - {date_str}", ""]

    if panorama:
        out.append("🌎 Panorama")
        out += [f"{trend(ret)} {label} {fmt_pct(ret)}" for label, ret in panorama]
        out.append("")

    if sectors:
        out += build_market_analysis(sectors, rotations or [])
        out.append("")

    if narrative:
        out += ["📝 Resumen", narrative, ""]

    out.append("🚨 Grandes movimientos")
    if movers:
        for m in movers:
            ratio = m.get("vol_ratio")
            # Solo mostramos el volumen cuando es claramente más alto que lo habitual
            vol = f", volumen x{ratio:.1f}" if ratio is not None and ratio >= 1.5 else ""
            title = f"{m['symbol']} ({m['name']}) {fmt_pct(m['ret_pct'])}{vol} {m['tag']}".rstrip()
            out.append(f"{trend(m['ret_pct'])} {title}")
            out += m.get("why", [])
            out.append("")
    else:
        out += ["Sin movimientos fuera de lo normal.", ""]

    mover_symbols = {m["symbol"] for m in movers}
    out.append("👀 A revisar (activos con CEDEAR)")
    if opportunities:
        for o in opportunities:
            out.append(f"🟡 {o['symbol']} ({o['name']}) {fmt_pct(o['ret_pct'])}: " + "; ".join(o["reasons"]))
            if o["symbol"] in mover_symbols:
                out.append("Contexto en Grandes movimientos.")
            else:
                out += o.get("why", [])
            out.append("")
    else:
        out += ["Ninguna señal hoy.", ""]

    sources = [(sym, n) for sym, items in news.items() for n in items[:1] if n.get("url")]
    if sources:
        out.append("🔗 Fuentes")
        out += [f"{sym} ({n['source']}): {n['url']}" for sym, n in sources]
        out.append("")

    out.append(DISCLAIMER)
    return "\n".join(out)
