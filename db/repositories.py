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