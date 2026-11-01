"""Búsqueda de noticias y filtro por fuentes confiables."""

from __future__ import annotations

import logging
import re

import feedparser
import yfinance as yf

log = logging.getLogger(__name__)

_NOISE = re.compile(
    r"\b(inc|corp|corporation|co|company|ltd|plc|holdings|group|sa|nv|the|class [abc])\b\.?",
    re.IGNORECASE,
)


def is_trusted(source: str, url: str, trusted: list[str]) -> bool:
    haystack = f"{source} {url}".lower()
    return any(t.lower() in haystack for t in trusted)


def keywords_for(name: str, extra: list[str] | None = None) -> list[str]:
    base = _NOISE.sub("", name)
    base = re.sub(r"[^\w\s&-]", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    kws = [base] if len(base) >= 4 else []
    kws += extra or []
    return kws


def headline_matches(title: str, symbol: str, name: str, extra: list[str] | None = None) -> bool:
    """True si el titular menciona al activo (por nombre o por ticker)."""
    for kw in keywords_for(name, extra):
        if re.search(rf"\b{re.escape(kw)}\b", title, re.IGNORECASE):
            return True
    # El ticker solo cuenta si es una palabra en mayúsculas de 3+ letras o un $CASHTAG,
    # para evitar falsos positivos con tickers de 1-2 letras.
    clean = symbol.replace("=F", "")
    if clean.isalpha() and len(clean) >= 3 and re.search(rf"\b{re.escape(clean)}\b", title):
        return True
    return bool(re.search(rf"\${re.escape(clean)}\b", title))


def normalize_yahoo_item(item: dict) -> dict | None:
    """yfinance cambió el formato de .news; soportamos el viejo y el nuevo."""
    if "content" in item and isinstance(item["content"], dict):
        c = item["content"]
        title = c.get("title")
        source = (c.get("provider") or {}).get("displayName", "")
        url = (c.get("canonicalUrl") or c.get("clickThroughUrl") or {}).get("url", "")
    else:
        title = item.get("title")
        source = item.get("publisher", "")
        url = item.get("link", "")
    if not title:
        return None
    return {"title": title.strip(), "source": source, "url": url}


def yahoo_news(symbol: str) -> list[dict]:
    try:
        raw = yf.Ticker(symbol).news or []
    except Exception as exc:  # noqa: BLE001
        log.warning("Sin noticias de Yahoo para %s: %s", symbol, exc)
        return []
    return [n for n in (normalize_yahoo_item(i) for i in raw) if n]


def fetch_feed_items(feeds: list[dict]) -> list[dict]:
    items = []
    for feed in feeds:
        parsed = feedparser.parse(feed["url"], agent="mercado-bot/1.0")
        if not parsed.entries:  # incluye feeds que responden bien pero vienen vacíos
            log.warning("Feed sin noticias, lo salto: %s", feed["name"])
            continue
        for e in parsed.entries[:60]:
            title = getattr(e, "title", "").strip()
            if title:
                items.append({"title": title, "source": feed["name"], "url": getattr(e, "link", "")})
    return items


def collect_news(
    flagged: list[dict],
    feed_items: list[dict],
    trusted: list[str],
    per_symbol: int = 3,
    fetch_yahoo=yahoo_news,
) -> dict[str, list[dict]]:
    """Devuelve {ticker: [titulares]} usando solo fuentes confiables."""
    result: dict[str, list[dict]] = {}
    for item in flagged:
        sym = item["symbol"]
        candidates = list(fetch_yahoo(sym))
        candidates += [
            n for n in feed_items if headline_matches(n["title"], sym, item["name"], item.get("keywords"))
        ]
        picked, seen = [], set()
        for n in candidates:
            key = n["title"].lower()
            if key in seen or not is_trusted(n["source"], n["url"], trusted):
                continue
            seen.add(key)
            picked.append(n)
            if len(picked) >= per_symbol:
                break
        result[sym] = picked
    return result
