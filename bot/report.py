"""Armado del texto del informe. Funciones puras."""

from __future__ import annotations

DISCLAIMER = "⚠️ Son señales automáticas para revisar, no una recomendación de inversión."


DISCLAIMER_WITH_OPINIONS = (
    "⚠️ Las recomendaciones y los precios objetivo son opiniones generadas por IA y pueden tener errores. "
    "Verificalos antes de operar."
)
BRIEF_OMITS = ("🏭", "📰", "❓")


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


def build_local_section(local: dict) -> list[str]:
    out = [f"🇦🇷 Mercado local (rueda del {local['date'].strftime('%d/%m')})"]
    merval = local.get("merval")
    if merval:
        usd = merval.get("usd_ret_pct")
        in_usd = f" (en dólares CCL {fmt_pct(usd)})" if usd is not None else ""
        out.append(
            f"{trend(merval['ret_pct'])} {merval.get('label', 'Merval')} {fmt_pct(merval['ret_pct'])}{in_usd}"
        )
    else:
        out.append("⚪ Merval sin datos.")
    risk = local.get("country_risk")
    if risk:
        out.append(f"🌡️ Riesgo país {risk['value']:.0f} ({risk['change']:+.0f} puntos)")
    if local.get("dollars"):
        parts = [f"{d['label']} ${d['value']:,.0f} ({fmt_pct(d['change_pct'])})" for d in local["dollars"]]
        out.append("💵 " + " | ".join(parts).replace(",", "."))
    panel, top = local.get("panel", []), local.get("top", 3)
    if panel:
        best = [f"{m['label']} {fmt_pct(m['ret_pct'])}" for m in panel[:top] if m["ret_pct"] > 0]
        worst = [f"{m['label']} {fmt_pct(m['ret_pct'])}" for m in reversed(panel[-top:]) if m["ret_pct"] < 0]
        if best:
            out.append("🟢 Suben: " + ", ".join(best))
        if worst:
            out.append("🔴 Bajan: " + ", ".join(worst))
    return out


def keep_context_line(line: str, brief: bool) -> bool:
    """En el informe breve, el resumen ya explica las causas y cita las fuentes."""
    return not (brief and line.startswith(BRIEF_OMITS))


def build_report(
    date_str: str,
    panorama: list[tuple[str, float]],
    movers: list[dict],
    opportunities: list[dict],
    narrative: str | None,
    news: dict[str, list[dict]],
    sectors: list[dict] | None = None,
    rotations: list[dict] | None = None,
    local: dict | None = None,
    brief: bool = False,
) -> str:
    out = [f"📊 Informe de mercado - {date_str}", ""]

    if panorama:
        out.append("🌎 Panorama")
        out += [f"{trend(ret)} {label} {fmt_pct(ret)}" for label, ret in panorama]
        out.append("")

    if sectors:
        out += build_market_analysis(sectors, rotations or [])
        out.append("")

    if local:
        out += build_local_section(local)
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
            out += [line for line in m.get("why", []) if keep_context_line(line, brief)]
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
                out += [line for line in o.get("why", []) if keep_context_line(line, brief)]
            out.append("")
    else:
        out += ["Ninguna señal hoy.", ""]

    sources = [(sym, n) for sym, items in news.items() for n in items[:1] if n.get("url")]
    if sources and not brief:
        out.append("🔗 Fuentes")
        out += [f"{sym} ({n['source']}): {n['url']}" for sym, n in sources]
        out.append("")

    out.append(DISCLAIMER_WITH_OPINIONS if brief else DISCLAIMER)
    return "\n".join(out)
