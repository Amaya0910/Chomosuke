"""services/reddit_video_fetcher.py"""

import logging
import random
from typing import Collection

import aiohttp

from services.meme_source import TIPO_VIDEO, MemeSource

logger = logging.getLogger("bump-bot")

REDDIT_URL = "https://www.reddit.com/r/{subreddit}/hot.json"
# Reddit rechaza los User-Agent genéricos; usa uno descriptivo.
USER_AGENT = "bump-bot/1.0 (Discord bot de memes)"

# Videos más largos pesan demasiado y Discord los muestra mal.
DURACION_MAXIMA_SEG = 60
MAX_SUBREDDITS_A_PROBAR = 3

# Subreddits donde buscar videos. Agrega aquí los que tengan más videos;
# no hace falta tocar nada más del código.
VIDEO_SUBREDDITS = [
    "MAAU",
    "DylanteroYT",
    "BeelcitosMemes",
    "Carola",
    "memexico",
    "memes_de_pobres",
    "dankgentina",
    "yo_elvr",
]


class RedditVideoFetcher(MemeSource):
    """Obtiene memes en video desde el JSON público de Reddit.

    Usa `fallback_url`, el mp4 que Reddit aloja en v.redd.it. Ese archivo
    no trae audio (Reddit lo guarda aparte), así que los videos se ven
    pero sin sonido.
    """

    async def get_meme(
        self,
        subreddit: str | None = None,
        excluir: Collection[str] = frozenset(),
    ) -> dict | None:
        if subreddit:
            return await self._buscar_en(subreddit, excluir)

        candidatos = random.sample(
            VIDEO_SUBREDDITS, k=min(MAX_SUBREDDITS_A_PROBAR, len(VIDEO_SUBREDDITS))
        )
        for elegido in candidatos:
            meme = await self._buscar_en(elegido, excluir)
            if meme is not None:
                return meme
        return None

    async def _buscar_en(self, subreddit: str, excluir: Collection[str]) -> dict | None:
        posts = await self._pedir_posts(subreddit)
        random.shuffle(posts)

        for post in posts:
            meme = self._normalizar(post)
            if meme is None:
                continue
            if meme["post_link"] in excluir or meme["media_url"] in excluir:
                continue
            return meme

        logger.info(f"r/{subreddit}: no hay videos nuevos disponibles.")
        return None

    async def _pedir_posts(self, subreddit: str) -> list[dict]:
        url = REDDIT_URL.format(subreddit=subreddit)
        params = {"limit": "50", "raw_json": "1"}
        headers = {"User-Agent": USER_AGENT}
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Reddit respondió {resp.status} para r/{subreddit}")
                        return []
                    data = await resp.json()
        except Exception as e:
            logger.error(f"Error obteniendo videos de r/{subreddit}: {e}")
            return []

        try:
            return [hijo["data"] for hijo in data["data"]["children"]]
        except (KeyError, TypeError):
            logger.warning(f"Respuesta de Reddit con formato inesperado para r/{subreddit}")
            return []

    @staticmethod
    def _normalizar(post: dict) -> dict | None:
        """Se queda solo con videos alojados en Reddit, cortos y sin NSFW."""
        if post.get("over_18") or not post.get("is_video"):
            return None

        video = (post.get("media") or {}).get("reddit_video")
        if not video or not video.get("fallback_url"):
            return None
        if video.get("duration", 0) > DURACION_MAXIMA_SEG:
            return None

        try:
            return {
                "title": post["title"],
                "media_url": video["fallback_url"],
                "post_link": f"https://www.reddit.com{post['permalink']}",
                "subreddit": post["subreddit"],
                "media_type": TIPO_VIDEO,
            }
        except KeyError:
            return None