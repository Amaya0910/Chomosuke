"""services/meme_fetcher.py"""

import logging
import random
import aiohttp

logger = logging.getLogger("bump-bot")

MEME_API_URL = "https://meme-api.com/gimme"

# Subreddits en español conocidos por tener memes. Si alguno deja de
# funcionar o no te gusta, puedes agregar/quitar de esta lista sin
# tocar el resto del código.
SPANISH_SUBREDDITS = [
    "SpanishMeme",
    "memexico",
    "memes_de_pobres",
    "dankgentina",
    "yo_elvr",
]


class MemeFetcher:
    """Encapsula la obtención de un meme desde una fuente externa.
    Si mañana cambias de API, solo tocas esta clase."""

    async def get_meme(self, subreddit: str | None = None, _intentos: int = 0) -> dict | None:
        # Si no se especifica un subreddit, elige uno al azar de la lista en español
        elegido = subreddit or random.choice(SPANISH_SUBREDDITS)
        url = f"{MEME_API_URL}/{elegido}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Meme API respondió {resp.status} para r/{elegido}")
                        return await self._reintentar(subreddit, _intentos)

                    data = await resp.json()

                    if "url" not in data:
                        logger.warning(f"Respuesta sin meme válido para r/{elegido}")
                        return await self._reintentar(subreddit, _intentos)

                    if data.get("nsfw"):
                        return await self.get_meme(subreddit, _intentos)  # reintenta mismo subreddit

                    return {
                        "title": data["title"],
                        "image_url": data["url"],
                        "post_link": data["postLink"],
                        "subreddit": data["subreddit"],
                    }
        except Exception as e:
            logger.error(f"Error obteniendo meme de r/{elegido}: {e}")
            return await self._reintentar(subreddit, _intentos)

    async def _reintentar(self, subreddit: str | None, intentos: int) -> dict | None:
        """Si el subreddit falló y el usuario no pidió uno específico,
        prueba con otro de la lista (máximo 3 intentos)."""
        if subreddit is not None or intentos >= 2:
            return None
        return await self.get_meme(None, intentos + 1)