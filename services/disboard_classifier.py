import discord

PALABRAS_ENFRIAMIENTO = ("espera", "wait", "minutos", "cooldown", "you can bump")
PALABRAS_EXITO = ("bump done", "listo", "éxito", "exitoso", "gracias por", "thx for", "bumpeado", "bump!")


class DisboardMessageClassifier:
    """Sabe interpretar los embeds que envía Disboard. Nada más (SRP)."""

    def clasificar(self, embed: discord.Embed) -> str:
        """Devuelve 'enfriamiento', 'exito' o 'desconocido'."""
        descripcion = (embed.description or "").lower()

        if any(p in descripcion for p in PALABRAS_ENFRIAMIENTO):
            return "enfriamiento"
        if any(p in descripcion for p in PALABRAS_EXITO):
            return "exito"
        return "desconocido"