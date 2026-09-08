from abc import ABC, abstractmethod
from typing import Optional

from .database import Database


class CountdownConfigRepository(ABC):
    """Puerto para persistir en qué canal se publica el contador, por servidor."""

    @abstractmethod
    def get_canal(self, guild_id: int) -> Optional[int]: ...

    @abstractmethod
    def set_canal(self, guild_id: int, canal_id: int) -> None: ...

    @abstractmethod
    def all_configured(self):
        """Filas (guild_id, canal_id) de todos los servidores con canal configurado."""
        ...


class SQLiteCountdownConfigRepository(CountdownConfigRepository):
    def __init__(self, database: Database):
        self.db = database
        self._init_schema()

    def _init_schema(self):
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS countdown_config (
                guild_id INTEGER PRIMARY KEY,
                canal_id INTEGER
            )
            """
        )

    def get_canal(self, guild_id: int) -> Optional[int]:
        fila = self.db.fetchone("SELECT canal_id FROM countdown_config WHERE guild_id = ?", (guild_id,))
        return fila["canal_id"] if fila else None

    def set_canal(self, guild_id: int, canal_id: int) -> None:
        self.db.execute(
            "INSERT INTO countdown_config (guild_id, canal_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET canal_id = excluded.canal_id",
            (guild_id, canal_id),
        )

    def all_configured(self):
        return self.db.fetchall(
            "SELECT guild_id, canal_id FROM countdown_config WHERE canal_id IS NOT NULL"
        )