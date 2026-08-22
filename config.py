import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    """Configuración global del bot. Única responsabilidad: leer y validar el entorno."""

    token: str
    disboard_id: int
    cooldown_seconds: int
    db_path: str
    bump_emoji: str

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
        )