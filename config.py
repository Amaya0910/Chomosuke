import os
from dataclasses import dataclass
from datetime import date

from dotenv import load_dotenv

load_dotenv()

# Comunidades de Lemmy por defecto para los videos (formato nombre@instancia).
DEFAULT_LEMMY_COMUNIDADES = "memes@lemmy.world,lemmyshitpost@lemmy.world,funny@lemmy.world"


@dataclass(frozen=True)
class Config:
    """Configuración global del bot. Única responsabilidad: leer y validar el entorno."""

    token: str
    disboard_id: int
    cooldown_seconds: int
    db_path: str
    bump_emoji: str
    countdown_start: date
    countdown_end: date
    lemmy_communities: tuple[str, ...]

    @staticmethod
    def _parse_comunidades(raw: str) -> tuple[str, ...]:
        comunidades = tuple(c.strip() for c in raw.split(",") if c.strip())
        invalidas = [c for c in comunidades if "@" not in c]
        if not comunidades or invalidas:
            raise RuntimeError(
                "LEMMY_COMUNIDADES debe tener al menos una comunidad con formato nombre@instancia, "
                "separadas por coma (ej. memes@lemmy.world,funny@lemmy.world)."
                + (f" Valores inválidos: {', '.join(invalidas)}." if invalidas else "")
            )
        return comunidades

    @staticmethod
    def from_env() -> "Config":
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise RuntimeError(
                "No se encontró DISCORD_TOKEN. Crea un archivo .env con DISCORD_TOKEN=tu_token_aqui "
                "(mira .env.example). Si ese token ya estuvo expuesto públicamente, "
                "regenéralo antes de usarlo."
            )

        emoji_id = os.getenv("EMOJI_BUMP_ID", "")
        animado = os.getenv("EMOJI_ANIMADO", "false").lower() == "true"
        emoji = f"<{'a' if animado else ''}:emoji:{emoji_id}>" if emoji_id else "🎉"

        return Config(
            token=token,
            disboard_id=302050872383242240,
            cooldown_seconds=int(os.getenv("TIEMPO_ENFRIAMIENTO", "7200")),
            db_path=os.getenv("DB_PATH", "bumpbot.db"),
            bump_emoji=emoji,
            countdown_start=date(2026, 8, 1),
            countdown_end=date(2027, 8, 1),
            lemmy_communities=Config._parse_comunidades(
                os.getenv("LEMMY_COMUNIDADES", DEFAULT_LEMMY_COMUNIDADES)
            ),
        )