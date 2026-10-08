"""services/meme_source.py"""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Collection, Iterable

TIPO_IMAGEN = "imagen"
TIPO_VIDEO = "video"
TIPO_MIXTO = "mixto"


class MemeSourceError(Exception):
    """La fuente no pudo dar una respuesta válida (red, HTTP o formato inesperado).

    No es lo mismo que 'no hay memes nuevos': en ese caso la fuente respondió
    bien y simplemente no tenía nada que servir, y get_meme devuelve None.
    """


class MemeSource(ABC):
    """Puerto para cualquier fuente de memes (imágenes, videos, otra API...).

    Devuelve un dict con: title, media_url, post_link, subreddit, media_type
    y, opcionalmente, origen (texto que se muestra como procedencia).

    Contrato:
    - Devuelve el meme si encontró uno que no esté en `excluir`.
    - Devuelve None si la fuente respondió bien pero no hay nada nuevo.
    - Lanza MemeSourceError si la fuente falló y no se pudo saber.
    """

    @abstractmethod
    async def get_meme(
        self,
        subreddit: str | None = None,
        excluir: Collection[str] = frozenset(),
    ) -> dict | None: ...


async def primero_disponible(
    candidatas: Iterable[str],
    buscar: Callable[[str], Awaitable[dict | None]],
) -> dict | None:
    """Prueba cada candidata (subreddit, comunidad...) hasta encontrar un meme.

    Si alguna falló y ninguna dio un meme, lanza MemeSourceError: no se puede
    asegurar que no hubiera nada, porque una de las fuentes no respondió.
    Si todas respondieron bien pero estaban vacías, devuelve None.
    """
    fallos = 0
    for candidata in candidatas:
        try:
            meme = await buscar(candidata)
        except MemeSourceError:
            fallos += 1
            continue
        if meme is not None:
            return meme

    if fallos:
        raise MemeSourceError(f"{fallos} fuente(s) fallaron y ninguna dio un meme nuevo.")
    return None