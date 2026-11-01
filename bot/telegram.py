"""Envío de mensajes por Telegram."""

from __future__ import annotations

import os
import re
from html import unescape

import requests

MESSAGE_LIMIT = 3900  # Telegram admite 4096; dejamos margen


class TelegramError(RuntimeError):
    """Falló el envío. El mensaje nunca incluye la URL, porque contiene el token."""


def split_message(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Corta en saltos de línea para no pasar el límite de Telegram."""
    chunks, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # línea gigante: la partimos igual
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def to_plain(text: str) -> str:
    """Quita el formato HTML, por si Telegram rechaza el mensaje con formato."""
    return unescape(re.sub(r"</?[bi]>", "", text))


def _post(token: str, chat_id: str, text: str, html: bool) -> None:
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if html:
        payload["parse_mode"] = "HTML"
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=20)
    response.raise_for_status()


def send(text: str, html: bool = False) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for chunk in split_message(text):
        try:
            try:
                _post(token, chat_id, chunk, html)
            except requests.HTTPError as exc:
                # 400: formato rechazado. Mejor un informe sin negritas que ninguno.
                if not html or exc.response is None or exc.response.status_code != 400:
                    raise
                _post(token, chat_id, to_plain(chunk), False)
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else "sin respuesta"
            # "from None" evita que la URL con el token aparezca en los logs.
            raise TelegramError(f"Telegram rechazó el envío ({status})") from None
