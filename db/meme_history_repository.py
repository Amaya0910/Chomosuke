from abc import ABC, abstractmethod

from .database import Database


class MemeHistoryRepository(ABC):
    """Puerto para recordar qué memes ya se enviaron en cada servidor."""

    @abstractmethod
    def recent_keys(self, guild_id: int) -> set[str]:
        """Enlaces de post y URLs de imagen de los memes enviados recientemente."""
        ...

    @abstractmethod
    def register(self, guild_id: int, post_link: str, image_url: str) -> None: ...


class SQLiteMemeHistoryRepository(MemeHistoryRepository):
    """Historial sobre SQLite. Conserva solo los últimos `max_per_guild`
    memes de cada servidor para que la tabla no crezca sin límite."""

    def __init__(self, database: Database, max_per_guild: int = 200):
        self.db = database
        self.max_per_guild = max_per_guild
        self._init_schema()

    def _init_schema(self):
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS meme_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                post_link TEXT NOT NULL,
                image_url TEXT NOT NULL
            )
            """
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_meme_history_guild ON meme_history (guild_id, id)"
        )

    def recent_keys(self, guild_id: int) -> set[str]:
        filas = self.db.fetchall(
            "SELECT post_link, image_url FROM meme_history WHERE guild_id = ?", (guild_id,)
        )
        claves: set[str] = set()
        for fila in filas:
            claves.add(fila["post_link"])
            claves.add(fila["image_url"])
        return claves

    def register(self, guild_id: int, post_link: str, image_url: str) -> None:
        self.db.execute(
            "INSERT INTO meme_history (guild_id, post_link, image_url) VALUES (?, ?, ?)",
            (guild_id, post_link, image_url),
        )
        self.db.execute(
            """
            DELETE FROM meme_history
            WHERE guild_id = ?
              AND id NOT IN (
                  SELECT id FROM meme_history WHERE guild_id = ? ORDER BY id DESC LIMIT ?
              )
            """,
            (guild_id, guild_id, self.max_per_guild),
        )