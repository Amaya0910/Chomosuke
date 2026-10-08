"""services/meme_fetcher.py"""

import logging
import random
from typing import Collection

import aiohttp

from services.meme_source import TIPO_IMAGEN, MemeSource, MemeSourceError, primero_disponible

logger = logging.getLogger("bump-bot")

MEME_API_URL = "https://meme-api.com/gimme"

# Cuántos memes se piden por llamada: más candidatos = menos repetidos.
TAMANO_LOTE = 5
# Cuántos subreddits distintos se prueban si no se pidió uno específico.
MAX_SUBREDDITS_A_PROBAR = 3

# Subreddits en español conocidos por tener memes. Si alguno deja de
# funcionar o no te gusta, puedes agregar/quitar de esta lista sin
# tocar el resto del código.
SPANISH_SUBREDDITS = [
    "MAAU",
    "DylanteroYT",
    "BeelcitosMemes",
    "Carola",
    "memexico",
    "memes_de_pobres",
    "dankgentina",
    "yo_elvr",
]


class MemeFetcher(MemeSource):
    """Obtiene memes en imagen/GIF desde meme-api.com.

    No conoce Discord ni la base de datos: recibe por parámetro qué memes
    debe evitar (`excluir`) y devuelve el primero que sirva.
    """

    async def get_meme(
        self,
        subreddit: str | None = None,
        excluir: Collection[str] = frozenset(),
    ) -> dict | None:
        # Una comunidad de Lemmy lleva "@" y no es un subreddit: se ignora
        # aquí y se usa la lista por defecto.
        if subreddit and "@" not in subreddit:
            candidatos = [subreddit]
        else:
            candidatos = random.sample(
                SPANISH_SUBREDDITS, k=min(MAX_SUBREDDITS_A_PROBAR, len(SPANISH_SUBREDDITS))
            )
        return await primero_disponible(candidatos, lambda sub: self._buscar_en(sub, excluir))

    async def _buscar_en(self, subreddit: str, excluir: Collection[str]) -> dict | None:
        items = await self._pedir_lote(subreddit)
        random.shuffle(items)

        validos = repetidos = 0
        for item in items:
            meme = self._normalizar(item)
            if meme is None:
                continue
            validos += 1
            if meme["post_link"] in excluir or meme["media_url"] in excluir:
                repetidos += 1
                continue
            return meme

        logger.info(
            f"r/{subreddit}: {len(items)} memes revisados, {validos} válidos, "
            f"{repetidos} ya enviados. No hay nada nuevo que enviar."
        )
        return None

    async def _pedir_lote(self, subreddit: str) -> list[dict]:
        """Pide un lote a la API. Lanza MemeSourceError si la fuente falla."""
        url = f"{MEME_API_URL}/{subreddit}/{TAMANO_LOTE}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning(f"La fuente de imágenes respondió {resp.status} para r/{subreddit}")
                        raise MemeSourceError(f"HTTP {resp.status}")
                    data = await resp.json()
        except MemeSourceError:
            raise
        except Exception as e:
            logger.error(f"Error de conexión con la fuente de imágenes (r/{subreddit}): {e}")
            raise MemeSourceError(str(e)) from e

        if "memes" in data:
            return list(data["memes"])
        if "url" in data:
            return [data]
        logger.warning(f"La fuente de imágenes devolvió un formato inesperado para r/{subreddit}")
        raise MemeSourceError("formato inesperado")

    @staticmethod
    def _normalizar(item: dict) -> dict | None:
        """Descarta NSFW y respuestas incompletas; devuelve el formato interno."""
        if item.get("nsfw"):
            return None
        try:
            return {
                "title": item["title"],
                "media_url": item["url"],
                "post_link": item["postLink"],
                "subreddit": item["subreddit"],
                "media_type": TIPO_IMAGEN,
            }
        except KeyError:
            return None