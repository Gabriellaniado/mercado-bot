"""Caché en disco de una corrida: precios, capitalizaciones y contexto de cada activo.

La rutina diaria corre el bot varias veces seguidas (datos, prueba y envío). Con esta caché las
corridas siguientes reusan lo que ya bajó Yahoo en vez de pedirlo de nuevo. Vence a las pocas
horas, así que un día nunca usa datos de otro. Está desactivada si config no define `cache`.
"""

from __future__ import annotations

import logging
import os
import pickle
import time
from pathlib import Path

log = logging.getLogger(__name__)

SECTIONS = ("prices", "caps", "contexts")


class RunCache:
    def __init__(self, path: str | None = None, ttl_minutes: float = 180):
        self.path = Path(path) if path else None
        self.ttl = ttl_minutes * 60
        self.data: dict = {name: None for name in SECTIONS}
        if self.path:
            self._load()

    def _load(self) -> None:
        try:
            info = self.path.stat()
            if info.st_uid != os.getuid() or time.time() - info.st_mtime > self.ttl:
                return  # ajeno o vencido
            with open(self.path, "rb") as file:
                loaded = pickle.load(file)  # noqa: S301 - archivo propio, verificado arriba
            self.data.update({k: loaded.get(k) for k in SECTIONS})
        except FileNotFoundError:
            pass
        except Exception as exc:  # noqa: BLE001
            log.warning("Caché ilegible, la ignoro: %s", type(exc).__name__)

    def get(self, name: str):
        return self.data.get(name)

    def put(self, name: str, value) -> None:
        self.data[name] = value
        self.save()

    def save(self) -> None:
        if not self.path:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "wb") as file:
                pickle.dump(self.data, file)
            os.replace(tmp, self.path)
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo guardar la caché: %s", type(exc).__name__)
