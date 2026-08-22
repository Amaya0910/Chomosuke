import asyncio
import logging
from typing import Awaitable, Callable, Dict

logger = logging.getLogger("bump-bot")


class TimerScheduler:

    def __init__(self):
        self._tareas: Dict[str, asyncio.Task] = {}

    def programar(
        self,
        clave: str,
        segundos: float,
        callback: Callable[[], Awaitable[None]],
        reemplazar: bool = True,
    ) -> None:
        tarea_previa = self._tareas.get(clave)
        if tarea_previa and not tarea_previa.done():
            if not reemplazar:
                raise ValueError(f"Ya existe una tarea programada con la clave '{clave}'.")
            tarea_previa.cancel()

        async def envoltorio():
            try:
                if segundos > 0:
                    await asyncio.sleep(segundos)
                await callback()
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(f"Error ejecutando temporizador '{clave}'")
            finally:
                self._tareas.pop(clave, None)

        self._tareas[clave] = asyncio.create_task(envoltorio())

    def cancelar(self, clave: str) -> bool:
        tarea = self._tareas.get(clave)
        if tarea and not tarea.done():
            tarea.cancel()
            self._tareas.pop(clave, None)
            return True
        return False

    def activo(self, clave: str) -> bool:
        tarea = self._tareas.get(clave)
        return bool(tarea and not tarea.done())