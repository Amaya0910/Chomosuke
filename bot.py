import os
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bump-bot")

# === CONFIGURACIÓN GLOBAL (no depende del servidor) ===
TOKEN = os.getenv("DISCORD_TOKEN")
ID_DISBOARD = 302050872383242240  # ID oficial de Disboard
TIEMPO_ENFRIAMIENTO = int(os.getenv("TIEMPO_ENFRIAMIENTO", "7200"))  # 2 horas por defecto
DB_PATH = os.getenv("DB_PATH", "bumpbot.db")
EMOJI_BUMP_ID = os.getenv("EMOJI_BUMP_ID", "")
EMOJI_ANIMADO = os.getenv("EMOJI_ANIMADO", "false").lower() == "true"
EMOJI_BUMP = f"<{'a' if EMOJI_ANIMADO else ''}:emoji:{EMOJI_BUMP_ID}>" if EMOJI_BUMP_ID else "🎉"
# ========================================================

if not TOKEN:
    raise RuntimeError(
        "No se encontró DISCORD_TOKEN. Crea un archivo .env con DISCORD_TOKEN=tu_token_aqui "
        "(mira .env.example). Si ese token ya estuvo expuesto públicamente, "
        "regenéralo antes de usarlo."
    )

PALABRAS_ENFRIAMIENTO = ("espera", "wait", "minutos", "cooldown", "you can bump")
PALABRAS_EXITO = ("bump done", "listo", "éxito", "exitoso", "gracias por", "thx for", "bumpeado", "bump!")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True


class BumpBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.pending_timers: dict[int, asyncio.Task] = {}  # guild_id -> task

    async def setup_hook(self):
        await self.tree.sync()


client = BumpBot()

# ---------------------------------------------------------------------------
# Base de datos (una fila por servidor)
# ---------------------------------------------------------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
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
        conn.commit()


def get_config(guild_id: int) -> sqlite3.Row | None:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
        ).fetchone()


def ensure_row(guild_id: int):
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,)
        )
        conn.commit()


def set_canal_aviso(guild_id: int, canal_id: int):
    ensure_row(guild_id)
    with db() as conn:
        conn.execute(
            "UPDATE guild_config SET canal_aviso_id = ? WHERE guild_id = ?",
            (canal_id, guild_id),
        )
        conn.commit()


def set_rol_aviso(guild_id: int, rol_id: int | None):
    ensure_row(guild_id)
    with db() as conn:
        conn.execute(
            "UPDATE guild_config SET rol_aviso_id = ? WHERE guild_id = ?",
            (rol_id, guild_id),
        )
        conn.commit()


def set_estado(guild_id: int, proximo_bump: datetime | None, mensaje_id: int | None):
    ensure_row(guild_id)
    with db() as conn:
        conn.execute(
            "UPDATE guild_config SET proximo_bump = ?, mensaje_id = ? WHERE guild_id = ?",
            (proximo_bump.isoformat() if proximo_bump else None, mensaje_id, guild_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Lógica del bot
# ---------------------------------------------------------------------------

def clasificar_mensaje_disboard(embed: discord.Embed) -> str:
    """Devuelve 'enfriamiento', 'exito' o 'desconocido' según el embed de Disboard."""
    descripcion = (embed.description or "").lower()
    color = embed.color.value if embed.color else None

    # Disboard usa colores distintos para éxito (verde/azul) y error (rojo/naranja).
    # Los colores exactos pueden cambiar, así que las palabras clave son el respaldo principal.
    if any(p in descripcion for p in PALABRAS_ENFRIAMIENTO):
        return "enfriamiento"
    if any(p in descripcion for p in PALABRAS_EXITO):
        return "exito"
    return "desconocido"


async def borrar_mensaje_previo(guild: discord.Guild, canal_id: int | None, mensaje_id: int | None):
    if not mensaje_id or not canal_id:
        return
    canal = guild.get_channel(canal_id)
    if canal is None:
        return
    try:
        mensaje_previo = await canal.fetch_message(mensaje_id)
        await mensaje_previo.delete()
    except discord.NotFound:
        pass
    except discord.Forbidden:
        logger.error(f"[{guild.id}] Sin permisos para borrar el recordatorio anterior.")
    except discord.HTTPException as e:
        logger.warning(f"[{guild.id}] No se pudo borrar el recordatorio anterior: {e}")


async def iniciar_temporizador(guild_id: int, segundos: float):
    if segundos > 0:
        await asyncio.sleep(segundos)

    guild = client.get_guild(guild_id)
    if guild is None:
        logger.error(f"No se pudo encontrar el servidor {guild_id} al terminar el temporizador.")
        return

    config = get_config(guild_id)
    if not config or not config["canal_aviso_id"]:
        logger.warning(f"[{guild_id}] No hay canal de aviso configurado. Usa /bump-config canal.")
        return

    canal = guild.get_channel(config["canal_aviso_id"])
    if canal is None:
        logger.error(f"[{guild_id}] El canal de aviso configurado ya no existe.")
        return

    mencion = f"<@&{config['rol_aviso_id']}> " if config["rol_aviso_id"] else ""
    try:
        mensaje_enviado = await canal.send(
            f"{mencion}**¡El enfriamiento ha terminado!** Ya pueden usar `/bump` nuevamente. {EMOJI_BUMP}"
        )
        set_estado(guild_id, datetime.now(timezone.utc), mensaje_enviado.id)
    except discord.Forbidden:
        logger.error(f"[{guild_id}] Sin permisos para enviar mensajes en el canal de aviso.")

    client.pending_timers.pop(guild_id, None)


def programar_temporizador(guild_id: int, segundos: float):
    tarea_previa = client.pending_timers.get(guild_id)
    if tarea_previa and not tarea_previa.done():
        tarea_previa.cancel()
    tarea = asyncio.create_task(iniciar_temporizador(guild_id, segundos))
    client.pending_timers[guild_id] = tarea


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------

@client.event
async def on_ready():
    logger.info(f"Bot encendido y conectado como {client.user}")
    init_db()

    with db() as conn:
        filas = conn.execute(
            "SELECT guild_id, proximo_bump FROM guild_config WHERE proximo_bump IS NOT NULL"
        ).fetchall()

    for fila in filas:
        proximo = datetime.fromisoformat(fila["proximo_bump"])
        restante = (proximo - datetime.now(timezone.utc)).total_seconds()
        logger.info(f"[{fila['guild_id']}] Retomando temporizador: {max(restante, 0):.0f}s restantes")
        programar_temporizador(fila["guild_id"], max(restante, 0))


@client.event
async def on_message(message: discord.Message):
    # Solo nos interesan mensajes de Disboard dentro de un servidor
    if message.guild is None or message.author.id != ID_DISBOARD:
        return
    if not message.embeds:
        return

    clasificacion = clasificar_mensaje_disboard(message.embeds[0])
    guild = message.guild

    if clasificacion == "enfriamiento":
        await asyncio.sleep(3)
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass
        return

    if clasificacion == "desconocido":
        logger.warning(f"[{guild.id}] Embed de Disboard no reconocido, se ignora.")
        return

    # clasificacion == "exito"
    config = get_config(guild.id)
    if config:
        await borrar_mensaje_previo(guild, config["canal_aviso_id"], config["mensaje_id"])

    await asyncio.sleep(3)
    try:
        await message.delete()
    except discord.Forbidden:
        logger.error(f"[{guild.id}] Sin permisos para borrar el mensaje de Disboard.")
    except discord.HTTPException as e:
        logger.warning(f"[{guild.id}] No se pudo borrar el mensaje de Disboard: {e}")

    proximo_bump = datetime.now(timezone.utc) + timedelta(seconds=TIEMPO_ENFRIAMIENTO)
    set_estado(guild.id, proximo_bump, None)
    programar_temporizador(guild.id, TIEMPO_ENFRIAMIENTO - 3)
    logger.info(f"[{guild.id}] Bump confirmado. Próximo aviso en {TIEMPO_ENFRIAMIENTO}s.")


# ---------------------------------------------------------------------------
# Comandos slash de configuración (solo administradores)
# ---------------------------------------------------------------------------

grupo_config = app_commands.Group(name="bump-config", description="Configura el bot de bumps para este servidor")


@grupo_config.command(name="canal", description="Define el canal donde se avisa que ya se puede bumpear")
@app_commands.checks.has_permissions(manage_guild=True)
async def config_canal(interaction: discord.Interaction, canal: discord.TextChannel):
    set_canal_aviso(interaction.guild_id, canal.id)
    await interaction.response.send_message(
        f"Listo. Los avisos de enfriamiento terminado se enviarán a {canal.mention}.",
        ephemeral=True,
    )


@grupo_config.command(name="rol", description="Define el rol a mencionar cuando termina el enfriamiento (opcional)")
@app_commands.checks.has_permissions(manage_guild=True)
async def config_rol(interaction: discord.Interaction, rol: discord.Role | None = None):
    set_rol_aviso(interaction.guild_id, rol.id if rol else None)
    if rol:
        await interaction.response.send_message(f"Se mencionará a {rol.mention} en cada aviso.", ephemeral=True)
    else:
        await interaction.response.send_message("Se quitó la mención de rol en los avisos.", ephemeral=True)


@grupo_config.command(name="ver", description="Muestra la configuración actual del bot en este servidor")
async def config_ver(interaction: discord.Interaction):
    config = get_config(interaction.guild_id)
    if not config or not config["canal_aviso_id"]:
        await interaction.response.send_message(
            "Este servidor todavía no tiene canal de aviso configurado. Usa `/bump-config canal`.",
            ephemeral=True,
        )
        return

    canal = f"<#{config['canal_aviso_id']}>"
    rol = f"<@&{config['rol_aviso_id']}>" if config["rol_aviso_id"] else "Ninguno"
    estado = "Sin bump registrado todavía"
    if config["proximo_bump"]:
        proximo = datetime.fromisoformat(config["proximo_bump"])
        estado = f"Próximo aviso: <t:{int(proximo.timestamp())}:R>"

    await interaction.response.send_message(
        f"**Canal de aviso:** {canal}\n**Rol mencionado:** {rol}\n**Estado:** {estado}",
        ephemeral=True,
    )


@config_canal.error
@config_rol.error
async def config_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "Necesitas el permiso de 'Administrar servidor' para usar este comando.", ephemeral=True
        )
    else:
        logger.exception("Error en comando de configuración", exc_info=error)
        await interaction.response.send_message("Ocurrió un error al ejecutar el comando.", ephemeral=True)


client.tree.add_command(grupo_config)

client.run(TOKEN)