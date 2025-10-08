import logging
from functools import lru_cache

from core.config import settings
from DataAbstractionLayer.base import BaseDatabase
from core.ports import AbstractLanguageAgent
from core.adapters import OpenAIAgentAdapter
from services.production_service import ProductionService
from core.dispatcher import ToolDispatcher
from services.scheduling_service import SchedulingService

logger = logging.getLogger(__name__)

@lru_cache(maxsize=None)
def get_db_instance() -> BaseDatabase:
    """
    Fábrica de instancias de la DAL.
    Lee la configuración y devuelve la implementación de base de datos correcta.
    Esto permite cambiar entre una DB en memoria y una DB compartida.
    """
    try:
        if settings.DATABASE_TYPE == "mysql":
            from DataAbstractionLayer.mysql_db import MySQLDB
            logger.info("Usando implementación de base de datos: MySQL.")
            # Se asegura de que la URL esté configurada (ya validado en config.py)
            return MySQLDB(settings.DATABASE_URL)

        if settings.DATABASE_TYPE == "postgres":
                from DataAbstractionLayer.postgres_db import PostgresDB
                logger.info("Usando implementación de base de datos: PostgreSQL.")
                # Se asegura de que la URL esté configurada (ya validado en config.py)
                return PostgresDB(settings.DATABASE_URL)
    
        # Por defecto, o si se especifica 'dummy', usa la base de datos en memoria.
        from DataAbstractionLayer.dummy_db import DummyDB
        logger.info("Usando implementación de base de datos: DummyDB (en memoria).")
        return DummyDB()

    except Exception as e:
        logger.error(f"Error al obtener la instancia de la base de datos: {str(e)}")
        raise e

@lru_cache(maxsize=None)
def get_agent_instance() -> AbstractLanguageAgent:
    """Devuelve el adaptador del agente de IA configurado."""
    # Actualmente solo tenemos OpenAI, pero aquí podrías añadir lógica
    # para seleccionar otros adaptadores en el futuro.
    return OpenAIAgentAdapter()

@lru_cache(maxsize=None)
def get_production_service() -> ProductionService:
    """Crea y devuelve una instancia del servicio de negocio."""
    db_instance = get_db_instance()
    return ProductionService(db=db_instance)

@lru_cache(maxsize=None)
def get_tool_dispatcher() -> ToolDispatcher:
    """Crea y devuelve un despachador, inyectando el servicio de negocio."""
    service_instance = get_production_service()
    return ToolDispatcher(production_service=service_instance)

@lru_cache(maxsize=None)
def get_scheduling_service() -> SchedulingService:
    """Crea y devuelve una instancia del servicio de planificación."""
    db_instance = get_db_instance()
    return SchedulingService(db=db_instance)

@lru_cache(maxsize=None)
def get_tool_dispatcher() -> ToolDispatcher:
    """Crea y devuelve un despachador, inyectando todos los servicios."""
    prod_service = get_production_service()
    sched_service = get_scheduling_service()
    return ToolDispatcher(production_service=prod_service, scheduling_service=sched_service)