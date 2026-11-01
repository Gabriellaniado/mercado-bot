"""Resumen opcional con IA. Si no hay API key, el informe sale solo con titulares."""

from __future__ import annotations

import logging
import os

import anthropic

log = logging.getLogger(__name__)

SYSTEM = (
    "Sos un analista que redacta un informe diario de mercado en español rioplatense, "
    "breve y claro. Usá SOLO los datos y titulares que te paso. Si para un activo no hay "
    "titulares, escribí 'sin noticias confirmadas de fuentes confiables' y no especules "
    "sobre la causa del movimiento. No recomiendes comprar ni vender: describí qué pasó y "
    "qué conviene mirar. Máximo 2 líneas por activo y citá la fuente entre paréntesis."
)


def build_prompt(entries: list[dict], news: dict[str, list[dict]]) -> str:
    lines = []
    for e in entries:
        lines.append(f"- {e['symbol']} ({e['name']}): {e['ret_pct']:+.1f}% en el día. {e['tag']}")
        headlines = news.get(e["symbol"], [])
        if not headlines:
            lines.append("    (sin titulares de fuentes confiables)")
        for h in headlines:
            lines.append(f"    * {h['title']} ({h['source']})")
    return "Activos a comentar:\n" + "\n".join(lines)


def summarize(entries: list[dict], news: dict[str, list[dict]], cfg: dict) -> str | None:
    """Devuelve el resumen, o None si no hay API key o falla la llamada."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not entries:
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=cfg["model"],
            max_tokens=cfg["max_tokens"],
            system=SYSTEM,
            messages=[{"role": "user", "content": build_prompt(entries, news)}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("Falló el resumen con IA (%s). Sigo solo con titulares.", exc)
        return None
