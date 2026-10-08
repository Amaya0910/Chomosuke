"""services/lemmy_video_fetcher.py"""

import logging
import random
from typing import Collection, Sequence
from urllib.parse import urlparse

import aiohttp

from services.meme_source import TIPO_VIDEO, MemeSource, MemeSourceError, primero_disponible

logger = logging.getLogger("bump-bot")

USER_AGENT = "bump-bot/1.0 (Discord bot de memes)"
INSTANCIA_POR_DEFECTO = "lemmy.world"

TAMANO_PAGINA = 50  # Lemmy limita cada petición a 50 posts
PAGINAS_POSIBLES = (1, 2)  # una página al azar da más variedad
MAX_COMUNIDADES_A_PROBAR = 3

TIPOS_VIDEO = ("video/mp4", "video/webm", "video/quicktime")
EXTENSIONES_VIDEO = (".mp4", ".webm", ".mov")


class LemmyVideoFetcher(MemeSource):
    """Obtiene memes en video desde la API pública de Lemmy (sin clave).

    Solo acepta posts cuyo enlace sea un archivo de video directo
    (mp4/webm/mov), que Discord reproduce con su propio reproductor.
    Las comunidades (formato "nombre@instancia") se reciben por constructor.
    """

    def __init__(self, comunidades: Sequence[str]):
        if not comunidades:
            raise ValueError("Debes indicar al menos una comunidad de Lemmy.")
        self.comunidades = tuple(comunidades)

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
                self.comunidades, k=min(MAX_COMUNIDADES_A_PROBAR, len(self.comunidades))
            )
        return await primero_disponible(candidatas, lambda c: self._buscar_en(c, excluir))

    async def _buscar_en(self, comunidad: str, excluir: Collection[str]) -> dict | None:
        posts = await self._pedir_posts(comunidad)
        random.shuffle(posts)

        videos = repetidos = 0
        for item in posts:
            meme = self._normalizar(item, comunidad)
            if meme is None:
                continue
            videos += 1
            if meme["post_link"] in excluir or meme["media_url"] in excluir:
                repetidos += 1
                continue
            return meme

        logger.info(
            f"{comunidad}: {len(posts)} posts revisados, {videos} videos, "
            f"{repetidos} ya enviados. No hay nada nuevo que enviar."
        )
        return None

    async def _pedir_posts(self, comunidad: str) -> list[dict]:
        """Pide posts a Lemmy. Lanza MemeSourceError si la fuente falla."""
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
                        raise MemeSourceError(f"HTTP {resp.status}")
                    data = await resp.json()
        except MemeSourceError:
            raise
        except Exception as e:
            logger.error(f"Error de conexión con Lemmy ({comunidad}): {e}")
            raise MemeSourceError(str(e)) from e

        posts = data.get("posts") if isinstance(data, dict) else None
        if not isinstance(posts, list):
            logger.warning(f"Lemmy devolvió un formato inesperado para {comunidad}")
            raise MemeSourceError("formato inesperado")
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