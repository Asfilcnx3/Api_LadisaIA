from celery import Celery
from core.config import settings

# Se crea una instancia de Celery. El primer argumento es el nombre del módulo actual.
# El broker es la URL de Redis, donde Celery enviará los mensajes de las tareas.
# El backend también es Redis, donde Celery guardará los resultados de las tareas.
celery_app = Celery(
    "tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["core.tasks"] # Lista de módulos donde Celery buscará tareas.
)

celery_app.conf.update(
    task_track_started=True,
)
