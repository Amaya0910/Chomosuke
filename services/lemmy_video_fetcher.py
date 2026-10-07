"""services/lemmy_video_fetcher.py"""

import logging
import random
from typing import Collection
from urllib.parse import urlparse

import aiohttp

from services.meme_source import TIPO_VIDEO, MemeSource

logger = logging.getLogger("bump-bot")

USER_AGENT = "bump-bot/1.0 (Discord bot de memes)"
INSTANCIA_POR_DEFECTO = "lemmy.world"

TAMANO_PAGINA = 50  # Lemmy limita cada petición a 50 posts
PAGINAS_POSIBLES = (1, 2)  # una página al azar da más variedad
MAX_COMUNIDADES_A_PROBAR = 3

TIPOS_VIDEO = ("video/mp4", "video/webm", "video/quicktime")
EXTENSIONES_VIDEO = (".mp4", ".webm", ".mov")

# Comunidades donde buscar videos, con formato "nombre@instancia". Si una no
# existe verás un 404 en el log: quítala o cámbiala sin tocar nada más.
COMUNIDADES = [
    "memes@lemmy.world",
    "lemmyshitpost@lemmy.world",
    "funny@lemmy.world",
]


class LemmyVideoFetcher(MemeSource):
    """Obtiene memes en video desde la API pública de Lemmy (sin clave).

    Solo acepta posts cuyo enlace sea un archivo de video directo
    (mp4/webm/mov), que Discord reproduce con su propio reproductor.
    """

    async def get_meme(
        self,
        subreddit: str | None = None,
        excluir: Collection[str] = frozenset(),
    ) -> dict | None:
        # Una comunidad de Lemmy lleva "@"; cualquier otro valor es un
        # subreddit pensado para la fuente de imágenes y se ignora aquí.
        if subreddit and "@" in subreddit:
            candidatas = [subreddit]
        else:
            candidatas = random.sample(
                COMUNIDADES, k=min(MAX_COMUNIDADES_A_PROBAR, len(COMUNIDADES))
            )

        for comunidad in candidatas:
            meme = await self._buscar_en(comunidad, excluir)
            if meme is not None:
                return meme
        return None

    async def _buscar_en(self, comunidad: str, excluir: Collection[str]) -> dict | None:
        posts = await self._pedir_posts(comunidad)
        random.shuffle(posts)

        for item in posts:
            meme = self._normalizar(item, comunidad)
            if meme is None:
                continue
            if meme["post_link"] in excluir or meme["media_url"] in excluir:
                continue
            return meme

        logger.info(f"{comunidad}: no hay videos nuevos disponibles.")
        return None

    async def _pedir_posts(self, comunidad: str) -> list[dict]:
        nombre, _, instancia = comunidad.partition("@")
        instancia = instancia or INSTANCIA_POR_DEFECTO
        url = f"https://{instancia}/api/v3/post/list"
        params = {
            "community_name": nombre,
            "sort": "TopMonth",
            "limit": str(TAMANO_PAGINA),
            "page": str(random.choice(PAGINAS_POSIBLES)),
        }
        headers = {"User-Agent": USER_AGENT}
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Lemmy respondió {resp.status} para {comunidad}")
                        return []
                    data = await resp.json()
        except Exception as e:
            logger.error(f"Error obteniendo videos de {comunidad}: {e}")
            return []

        posts = data.get("posts") if isinstance(data, dict) else None
        if not isinstance(posts, list):
            logger.warning(f"Respuesta de Lemmy con formato inesperado para {comunidad}")
            return []
        return posts

    @classmethod
    def _normalizar(cls, item: dict, comunidad_pedida: str) -> dict | None:
        """Se queda solo con videos directos, sin NSFW ni posts removidos."""
        post = item.get("post") or {}
        comunidad = item.get("community") or {}

        if post.get("nsfw") or comunidad.get("nsfw"):
            return None
        if post.get("removed") or post.get("deleted"):
            return None

        url = post.get("url")
        if not url or not cls._es_video(post):
            return None

        try:
            titulo = post["name"]
            enlace = post["ap_id"]
        except KeyError:
            return None

        nombre = comunidad.get("name") or comunidad_pedida.split("@")[0]
        host = urlparse(comunidad.get("actor_id") or "").netloc
        origen = f"!{nombre}@{host}" if host else f"!{comunidad_pedida}"

        return {
            "title": titulo,
            "media_url": url,
            "post_link": enlace,
            "subreddit": nombre,
            "origen": origen,
            "media_type": TIPO_VIDEO,
        }

    @staticmethod
    def _es_video(post: dict) -> bool:
        tipo = (post.get("url_content_type") or "").lower()
        if tipo in TIPOS_VIDEO:
            return True
        return post["url"].lower().split("?")[0].endswith(EXTENSIONES_VIDEO)