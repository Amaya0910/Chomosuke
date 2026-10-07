"""services/meme_fetcher.py"""

import logging
import random
from typing import Collection

import aiohttp

from services.meme_source import TIPO_IMAGEN, MemeSource

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
        if subreddit:
            return await self._buscar_en(subreddit, excluir)

        candidatos = random.sample(
            SPANISH_SUBREDDITS, k=min(MAX_SUBREDDITS_A_PROBAR, len(SPANISH_SUBREDDITS))
        )
        for elegido in candidatos:
            meme = await self._buscar_en(elegido, excluir)
            if meme is not None:
                return meme
        return None

    async def _buscar_en(self, subreddit: str, excluir: Collection[str]) -> dict | None:
        items = await self._pedir_lote(subreddit)
        random.shuffle(items)

        for item in items:
            meme = self._normalizar(item)
            if meme is None:
                continue
            if meme["post_link"] in excluir or meme["media_url"] in excluir:
                continue
            return meme

        logger.info(f"r/{subreddit}: no hay memes nuevos en este lote.")
        return None

    async def _pedir_lote(self, subreddit: str) -> list[dict]:
        url = f"{MEME_API_URL}/{subreddit}/{TAMANO_LOTE}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Meme API respondió {resp.status} para r/{subreddit}")
                        return []
                    data = await resp.json()
        except Exception as e:
            logger.error(f"Error obteniendo memes de r/{subreddit}: {e}")
            return []

        if "memes" in data:
            return list(data["memes"])
        if "url" in data:
            return [data]
        logger.warning(f"Respuesta sin memes válidos para r/{subreddit}")
        return []

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