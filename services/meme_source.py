"""services/meme_source.py"""

from abc import ABC, abstractmethod
from typing import Collection

TIPO_IMAGEN = "imagen"
TIPO_VIDEO = "video"
TIPO_MIXTO = "mixto"


class MemeSource(ABC):
    """Puerto para cualquier fuente de memes (imágenes, videos, otra API...).

    Devuelve un dict con: title, media_url, post_link, subreddit, media_type.
    """

    @abstractmethod
    async def get_meme(
        self,
        subreddit: str | None = None,
        excluir: Collection[str] = frozenset(),
    ) -> dict | None:
        """Un meme cuyo post_link o media_url no estén en `excluir`, o None."""
        ...