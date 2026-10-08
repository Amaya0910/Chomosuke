"""services/meme_service.py"""

import random
from dataclasses import dataclass

from db.meme_history_repository import MemeHistoryRepository
from services.meme_source import TIPO_IMAGEN, TIPO_MIXTO, MemeSource, MemeSourceError


@dataclass(frozen=True)
class ResultadoMeme:
    """Resultado de buscar un meme.

    - meme presente: se encontró uno nuevo.
    - meme None y fuente_fallo False: la fuente respondió bien, pero no hay
      nada nuevo que enviar.
    - meme None y fuente_fallo True: al menos una fuente falló y ninguna dio
      un meme, así que no se puede asegurar que no hubiera nada.
    """

    meme: dict | None
    fuente_fallo: bool = False


class MemeService:
    """Coordina las fuentes de memes con el historial: entrega memes que el
    servidor todavía no ha visto y registra los que sí se enviaron."""

    def __init__(self, sources: dict[str, MemeSource], history: MemeHistoryRepository):
        self.sources = sources
        self.history = history

    async def siguiente(
        self, guild_id: int, subreddit: str | None, tipo: str = TIPO_IMAGEN
    ) -> ResultadoMeme:
        ya_enviados = self.history.recent_keys(guild_id)

        if tipo == TIPO_MIXTO:
            orden = list(self.sources)
            random.shuffle(orden)  # una al azar; si falla, prueba la otra
        else:
            orden = [tipo] if tipo in self.sources else [TIPO_IMAGEN]

        fallos = 0
        for clave in orden:
            try:
                meme = await self.sources[clave].get_meme(subreddit, excluir=ya_enviados)
            except MemeSourceError:
                fallos += 1
                continue
            if meme is not None:
                return ResultadoMeme(meme)

        return ResultadoMeme(None, fuente_fallo=fallos > 0)

    def marcar_enviado(self, guild_id: int, meme: dict) -> None:
        self.history.register(guild_id, meme["post_link"], meme["media_url"])