from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CountdownStatus:
    dias_restantes: int
    porcentaje: float
    finalizado: bool


class CountdownCalculator:
    """Calcula días restantes y porcentaje de avance entre dos fechas fijas.

    No sabe nada de Discord, SQLite ni horarios: solo hace la cuenta. Esto
    lo hace fácil de probar de forma aislada (SRP).
    """

    def __init__(self, fecha_inicio: date, fecha_fin: date):
        if fecha_fin <= fecha_inicio:
            raise ValueError("fecha_fin debe ser posterior a fecha_inicio")
        self.fecha_inicio = fecha_inicio
        self.fecha_fin = fecha_fin
        self._dias_totales = (fecha_fin - fecha_inicio).days

    def calcular(self, hoy: date) -> CountdownStatus:
        dias_restantes = max((self.fecha_fin - hoy).days, 0)

        dias_transcurridos = (hoy - self.fecha_inicio).days
        dias_transcurridos = max(0, min(dias_transcurridos, self._dias_totales))
        porcentaje = (dias_transcurridos / self._dias_totales) * 100

        return CountdownStatus(
            dias_restantes=dias_restantes,
            porcentaje=round(porcentaje, 2),
            finalizado=hoy >= self.fecha_fin,
        )