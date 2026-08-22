import sqlite3
from contextlib import contextmanager


class Database:
    """Envuelve la conexión SQLite. Única responsabilidad: abrir/cerrar conexiones y ejecutar SQL crudo."""

    def __init__(self, path: str):
        self.path = path

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, query: str, params: tuple = ()):
        with self.connect() as conn:
            conn.execute(query, params)
            conn.commit()

    def fetchone(self, query: str, params: tuple = ()):
        with self.connect() as conn:
            return conn.execute(query, params).fetchone()

    def fetchall(self, query: str, params: tuple = ()):
        with self.connect() as conn:
            return conn.execute(query, params).fetchall()