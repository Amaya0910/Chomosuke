import re

_PATTERN = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$", re.IGNORECASE)


class DurationParseError(ValueError):
    """Se lanza cuando el usuario escribe una duración inválida."""


def parse_duration(texto: str) -> int:
    """Convierte cadenas tipo '5m', '30s', '1h20m' en segundos.

    Lanza DurationParseError (con un mensaje listo para mostrar al usuario)
    si el formato es inválido o la duración total es 0.
    """
    texto = texto.strip().lower().replace(" ", "")
    if not texto:
        raise DurationParseError("Debes indicar una duración, ej: `5m`, `30s`, `1h20m`.")

    match = _PATTERN.fullmatch(texto)
    if not match or not any(match.groups()):
        raise DurationParseError(
            f"No entendí la duración `{texto}`. Usa un formato como `10s`, `5m`, `2h` o `1h30m`."
        )

    horas, minutos, segundos = (int(g) if g else 0 for g in match.groups())
    total = horas * 3600 + minutos * 60 + segundos

    if total <= 0:
        raise DurationParseError("La duración debe ser mayor a 0.")

    if total > 24 * 3600:
        raise DurationParseError("La duración máxima permitida es 24h.")

    return total