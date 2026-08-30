"""repositories.py"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from .database import Database


class GuildConfigRepository(ABC):
    """Puerto (interfaz) para persistir la configuración de bump por servidor.

    Los cogs dependen de esta abstracción y no de SQLite directamente
    (Principio de Inversión de Dependencias). Así se puede cambiar de
    backend (Postgres, Redis, etc.) sin tocar la lógica del bot, y se
    puede sustituir por un fake/mock en tests.
    """

    @abstractmethod
    def get(self, guild_id: int): ...

    @abstractmethod
    def set_canal_aviso(self, guild_id: int, canal_id: int) -> None: ...

    @abstractmethod
    def set_rol_aviso(self, guild_id: int, rol_id: Optional[int]) -> None: ...

    @abstractmethod
    def set_estado(self, guild_id: int, proximo_bump: Optional[datetime], mensaje_id: Optional[int]) -> None: ...

    @abstractmethod
    def all_pending(self): ...


class SQLiteGuildConfigRepository(GuildConfigRepository):
    """Implementación concreta sobre SQLite (una fila por servidor)."""

    def __init__(self, database: Database):
        self.db = database
        self._init_schema()

    def _init_schema(self):
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                canal_aviso_id INTEGER,
                rol_aviso_id INTEGER,
                proximo_bump TEXT,
                mensaje_id INTEGER
            )
            """
        )

    def _ensure_row(self, guild_id: int):
        self.db.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))

    def get(self, guild_id: int):
        return self.db.fetchone("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))

    def set_canal_aviso(self, guild_id: int, canal_id: int) -> None:
        self._ensure_row(guild_id)
        self.db.execute("UPDATE guild_config SET canal_aviso_id = ? WHERE guild_id = ?", (canal_id, guild_id))

    def set_rol_aviso(self, guild_id: int, rol_id: Optional[int]) -> None:
        self._ensure_row(guild_id)
        self.db.execute("UPDATE guild_config SET rol_aviso_id = ? WHERE guild_id = ?", (rol_id, guild_id))

    def set_estado(self, guild_id: int, proximo_bump: Optional[datetime], mensaje_id: Optional[int]) -> None:
        self._ensure_row(guild_id)
        self.db.execute(
            "UPDATE guild_config SET proximo_bump = ?, mensaje_id = ? WHERE guild_id = ?",
            (proximo_bump.isoformat() if proximo_bump else None, mensaje_id, guild_id),
        )

    def all_pending(self):
        return self.db.fetchall(
            "SELECT guild_id, proximo_bump FROM guild_config WHERE proximo_bump IS NOT NULL"
        )


class MemeConfigRepository(ABC):
    """Puerto para persistir la configuración de memes diarios por servidor."""

    @abstractmethod
    def set_config(self, guild_id: int, channel_id: int, webhook_url: str,
                   times: str, subreddit: Optional[str]) -> None: ...

    @abstractmethod
    def get_config(self, guild_id: int): ...

    @abstractmethod
    def get_all_configs(self): ...


class SQLiteMemeConfigRepository(MemeConfigRepository):
    """Implementación concreta sobre SQLite (una fila por servidor).

    `times` guarda una lista de horarios "HH:MM" separados por coma
    (ej. "09:00,15:00,21:00"), lo que permite varios memes al día.
    """

    def __init__(self, database: Database):
        self.db = database
        self._init_schema()

    def _init_schema(self):
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS meme_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                webhook_url TEXT NOT NULL,
                hour INTEGER NOT NULL DEFAULT 12,
                minute INTEGER NOT NULL DEFAULT 0,
                subreddit TEXT,
                times TEXT
            )
            """
        )
        self._migrar_columna_times()

    def _migrar_columna_times(self):
        """Migración automática: si el bot ya tenía la tabla creada de antes
        (sin la columna 'times'), la agrega y rellena las filas existentes
        con su hour/minute actual, para no perder configuración previa."""
        columnas = [fila["name"] for fila in self.db.fetchall("PRAGMA table_info(meme_config)")]
        if "times" not in columnas:
            self.db.execute("ALTER TABLE meme_config ADD COLUMN times TEXT")
        self.db.execute(
            "UPDATE meme_config SET times = printf('%02d:%02d', hour, minute) WHERE times IS NULL"
        )

    def set_config(self, guild_id: int, channel_id: int, webhook_url: str,
                   times: str, subreddit: Optional[str] = None) -> None:
        primera_hora, primer_minuto = (int(x) for x in times.split(",")[0].split(":"))
        self.db.execute(
            """
            INSERT INTO meme_config (guild_id, channel_id, webhook_url, hour, minute, subreddit, times)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                webhook_url = excluded.webhook_url,
                hour = excluded.hour,
                minute = excluded.minute,
                subreddit = excluded.subreddit,
                times = excluded.times
            """,
            (guild_id, channel_id, webhook_url, primera_hora, primer_minuto, subreddit, times),
        )

    def get_config(self, guild_id: int):
        return self.db.fetchone("SELECT * FROM meme_config WHERE guild_id = ?", (guild_id,))

    def get_all_configs(self):
        return self.db.fetchall("SELECT * FROM meme_config")