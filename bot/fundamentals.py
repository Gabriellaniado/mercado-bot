"""Contexto de cada activo: resultados, negocio y valuación, para explicar el movimiento.

Solo describe datos. No decide si algo está caro o barato ni recomienda operar.
"""

from __future__ import annotations

import logging
import math
import time

import numpy as np
import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

QUIET_MOVE_PCT = 2.0  # por debajo de esto, el nivel no se explica por lo que pasó hoy
INFO_KEYS = (
    "sector",
    "industry",
    "forwardPE",
    "revenueGrowth",
    "profitMargins",
    "targetMeanPrice",
    "numberOfAnalystOpinions",
    "recommendationKey",
)
RECOMMENDATIONS = {
    "strong_buy": "compra fuerte",
    "buy": "compra",
    "hold": "mantener",
    "underperform": "por debajo del mercado",
    "sell": "venta",
    "strong_sell": "venta fuerte",
}


def _with_retries(call, what: str, attempts: int = 3, pause: float = 2.0):
    """Yahoo corta con 401/429 desde IPs de la nube: se reintenta con pausas crecientes."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001
            if attempt == attempts:
                raise
            log.info("%s falló (%s), reintento %d/%d", what, type(exc).__name__, attempt, attempts - 1)
            time.sleep(pause * attempt)


def fetch_context(symbol: str) -> dict:
    """Baja datos de Yahoo. Si algo falla devuelve lo que haya: los ETF no tienen balances.

    `complete` queda en False si algún pedido falló, para no guardar en caché un contexto a medias.
    """
    ticker = yf.Ticker(symbol)
    ctx: dict = {"complete": True}
    try:
        info = _with_retries(lambda: ticker.info, f"datos de {symbol}") or {}
        ctx.update({k: info.get(k) for k in INFO_KEYS})
    except Exception as exc:  # noqa: BLE001
        ctx["complete"] = False
        log.warning("Sin datos de empresa para %s: %s", symbol, exc)
    try:
        ctx["earnings_dates"] = _with_retries(lambda: ticker.earnings_dates, f"resultados de {symbol}")
    except Exception as exc:  # noqa: BLE001
        ctx["complete"] = False
        log.warning("Sin fechas de resultados para %s: %s", symbol, exc)
    return ctx


def analyst_view(ctx: dict, close: float) -> dict | None:
    """Opinión de los analistas: precio objetivo medio contra el precio actual y recomendación.

    Devuelve None si Yahoo no informa el precio objetivo ni la recomendación.
    """
    target = ctx.get("targetMeanPrice")
    key = ctx.get("recommendationKey")
    upside = (target / close - 1) * 100 if _is_number(target) and close else None
    if upside is None and key not in RECOMMENDATIONS:
        return None
    count = ctx.get("numberOfAnalystOpinions")
    return {
        "upside_pct": upside,
        "opinion": key if key in RECOMMENDATIONS else None,
        "opinion_label": RECOMMENDATIONS.get(key),
        "count": int(count) if _is_number(count) else 0,
    }


def parse_earnings(dates: pd.DataFrame | None, as_of) -> tuple[dict | None, object | None]:
    """Devuelve el último resultado publicado y la fecha del próximo."""
    if dates is None or len(dates) == 0:
        return None, None
    last, upcoming = None, None
    for when, row in dates.sort_index().iterrows():
        eps = row.get("Reported EPS")
        if pd.notna(eps) and when.date() <= as_of:
            last = {"when": when, "eps": float(eps), "estimate": row.get("EPS Estimate")}
        elif pd.isna(eps) and when.date() > as_of and upcoming is None:
            upcoming = when.date()
    return last, upcoming


def reacted_to_earnings(when: pd.Timestamp, session_date) -> bool:
    """True si la rueda es la primera en la que el precio pudo reaccionar a los resultados."""
    roll_days = 1 if when.hour >= 16 else 0  # después del cierre reacciona la rueda siguiente
    first_session = np.busday_offset(when.date(), roll_days, roll="forward")
    return first_session == np.datetime64(session_date)


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not math.isnan(x)


def earnings_line(last: dict | None, upcoming, ret_pct: float, session_date) -> tuple[str | None, bool]:
    """Devuelve la línea de resultados y si esos resultados son el posible detonante."""
    if not last:
        return None, False
    when = last["when"].strftime("%d/%m")
    estimate = last["estimate"]
    has_estimate = pd.notna(estimate)
    versus = f" vs {float(estimate):.2f} esperado" if has_estimate else ""
    detail = f"ganancia por acción {last['eps']:.2f}{versus}"
    if not reacted_to_earnings(last["when"], session_date):
        text = f"🧾 Sin balance en esta rueda. Último ({when}): {detail}."
        if upcoming:
            text += f" Próximo: {upcoming.strftime('%d/%m')}."
        return text, False

    text = f"🧾 Balance del {when}: {detail}."
    if has_estimate and last["eps"] != float(estimate):
        beat = last["eps"] > float(estimate)
        if beat and ret_pct < 0:
            text += (
                " Superó lo esperado y aun así cayó: "
                "el precio pudo reaccionar a otra cosa, como las previsiones."
            )
        elif not beat and ret_pct > 0:
            text += " No llegó a lo esperado y aun así subió."
    return text, True


def sector_line(
    entry: dict, ctx: dict, sector_rows: list[dict], sector_map: dict, industry_map: dict
) -> tuple[str | None, bool]:
    """Compara el activo con su sector. Devuelve la línea y si el sector explica la mayor parte."""
    etf = industry_map.get(ctx.get("industry")) or sector_map.get(ctx.get("sector"))
    row = next((r for r in sector_rows if r["symbol"] == etf), None)
    if not row:
        return None, False
    ret, sector_ret = entry["ret_pct"], row["ret_1d"]
    if abs(ret) < QUIET_MOVE_PCT:
        return f"🏭 {row['label']} {sector_ret:+.1f}%: la acción se movió poco hoy ({ret:+.1f}%).", False
    same_way = ret * sector_ret > 0
    if same_way and abs(sector_ret) >= abs(ret) / 2:
        reading = "el movimiento acompaña al sector"
        return f"🏭 {row['label']} {sector_ret:+.1f}%: {reading}.", True
    reading = "el movimiento es sobre todo propio de la empresa"
    return f"🏭 {row['label']} {sector_ret:+.1f}%: {reading}.", False


def business_line(ctx: dict) -> str | None:
    parts = []
    if _is_number(ctx.get("revenueGrowth")):
        parts.append(f"ventas {ctx['revenueGrowth'] * 100:+.1f}% interanual")
    if _is_number(ctx.get("profitMargins")):
        parts.append(f"margen neto {ctx['profitMargins'] * 100:.1f}%")
    return "💼 " + ", ".join(parts).capitalize() + "." if parts else None


def price_line(entry: dict, ctx: dict) -> str | None:
    parts = [f"{abs(entry['dist_high_pct']):.0f}% bajo su máximo anual"]
    if _is_number(ctx.get("forwardPE")) and ctx["forwardPE"] > 0:
        parts.append(f"P/E estimado {ctx['forwardPE']:.1f}")
    target = ctx.get("targetMeanPrice")
    if _is_number(target) and entry.get("close"):
        upside = (target / entry["close"] - 1) * 100
        analysts = ctx.get("numberOfAnalystOpinions")
        count = f"{analysts} analistas" if analysts else "analistas"
        opinion = RECOMMENDATIONS.get(ctx.get("recommendationKey"))
        opinion_text = f", opinión media: {opinion}" if opinion else ""
        parts.append(f"precio objetivo de {count} {target:.1f} ({upside:+.0f}%{opinion_text})")
    return "🏷️ " + ", ".join(parts) + "."


def explain(
    entry: dict,
    ctx: dict,
    sector_rows: list[dict],
    sector_map: dict,
    industry_map: dict,
    headlines: list[dict],
) -> list[str]:
    """Arma las líneas que explican el nivel del activo y qué falta confirmar."""
    session_date = entry["date"].date()
    last, upcoming = parse_earnings(ctx.get("earnings_dates"), session_date)
    earnings, is_earnings = earnings_line(last, upcoming, entry["ret_pct"], session_date)
    sector, follows_sector = sector_line(entry, ctx, sector_rows, sector_map, industry_map)

    lines = [earnings, sector]
    if headlines:
        lines.append(f"📰 {headlines[0]['title']} ({headlines[0]['source']})")
    else:
        lines.append("📰 Sin titulares de fuentes confiables: causa no confirmada.")
    lines += [business_line(ctx), price_line(entry, ctx)]

    if is_earnings:
        question = "qué dijo la empresa sobre los próximos trimestres y si cambia la tendencia."
    elif abs(entry["ret_pct"]) < QUIET_MOVE_PCT:
        question = "si la baja acumulada responde al negocio o al clima general del mercado."
    elif follows_sector:
        question = "qué está moviendo a todo el sector."
    elif not headlines:
        question = "el motivo del movimiento, antes de sacar conclusiones."
    else:
        question = "si el motivo es puntual o afecta al negocio a largo plazo."
    lines.append(f"❓ A confirmar: {question}")
    return [line for line in lines if line]
