from functools import lru_cache

from core.agent import ProductionAgent
from DataAbstractionLayer.dummy_db import DummyDB
from DataAbstractionLayer.base import BaseDatabase
from tools.scheduling_tools import SchedulingTools
from tools.query_tools import QueryTools
from core.dispatcher import ToolDispatcher

# Usamos lru_cache(maxsize=None) como una forma simple de crear singletons.
# La función se ejecutará solo una vez y su resultado se cacheará para siempre.

@lru_cache(maxsize=None)
def get_db_instance() -> BaseDatabase:
    """Crea y devuelve una instancia singleton de la base de datos."""
    return DummyDB()

@lru_cache(maxsize=None)
def get_agent_instance() -> ProductionAgent:
    """Crea y devuelve una instancia singleton del agente de IA."""
    return ProductionAgent()

@lru_cache(maxsize=None)
def get_tool_dispatcher() -> ToolDispatcher:
    """
    Crea y devuelve un despachador de herramientas, inyectando las dependencias necesarias.
    """
    db_instance = get_db_instance()
    scheduling_tools = SchedulingTools(db=db_instance)
    query_tools = QueryTools(db=db_instance)
    
    # El despachador se inicializa con todas las herramientas disponibles.
    return ToolDispatcher(scheduling_tools=scheduling_tools, query_tools=query_tools)
