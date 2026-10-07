"""services/meme_service.py"""

import random

from db.meme_history_repository import MemeHistoryRepository
from services.meme_source import TIPO_IMAGEN, TIPO_MIXTO, MemeSource


class MemeService:
    """Coordina las fuentes de memes con el historial: entrega memes que el
    servidor todavía no ha visto y registra los que sí se enviaron."""

    def __init__(self, sources: dict[str, MemeSource], history: MemeHistoryRepository):
        self.sources = sources
        self.history = history

    async def siguiente(
        self, guild_id: int, subreddit: str | None, tipo: str = TIPO_IMAGEN
    ) -> dict | None:
        ya_enviados = self.history.recent_keys(guild_id)

        if tipo == TIPO_MIXTO:
            orden = list(self.sources)
            random.shuffle(orden)  # una al azar; si falla, prueba la otra
        else:
            orden = [tipo] if tipo in self.sources else [TIPO_IMAGEN]

        for clave in orden:
            meme = await self.sources[clave].get_meme(subreddit, excluir=ya_enviados)
            if meme is not None:
                return meme
        return None

    def marcar_enviado(self, guild_id: int, meme: dict) -> None:
        self.history.register(guild_id, meme["post_link"], meme["media_url"])