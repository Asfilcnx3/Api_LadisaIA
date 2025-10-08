import inspect
import logging

from typing import Dict, Any, Callable, Awaitable

from schemas.api_models import CommandResponse
from services.production_service import ProductionService
from core.exceptions import DispatcherError, ValidationError
from services.scheduling_service import SchedulingService

# Definimos un tipo para nuestras funciones de herramientas
ToolCallable = Callable[..., Awaitable[CommandResponse]]
logger = logging.getLogger(__name__)

class ToolDispatcher:
    """
    Registra y despacha llamadas a los servicios correctos basadas en la acción determinada por el agente de IA.
    """
    def __init__(self, production_service: ProductionService, scheduling_service: SchedulingService):
        self.tool_map: Dict[str, ToolCallable] = {
            # Herramientas de Scheduling
            "ignore_machine": production_service.ignore_machine, # Listo
            "reactivate_machine": production_service.reactivate_machine, # Listo
            "disable_machine_units": production_service.disable_machine_units, 
            "enable_machine_units": production_service.enable_machine_units,
            
            # Herramientas de Query
            "query_order_status": production_service.query_order_status,
            "query_machine_status": production_service.query_machine_status, # Listo
            "register_roll_weight": production_service.register_roll_weight,
            "register_waste": production_service.register_waste, # Listo
            
            "generate_optimal_schedule": scheduling_service.generate_optimal_schedule,
            "prioritize_pedido": scheduling_service.prioritize_pedido, # Movido al nuevo servicio
            "generate_optimal_schedule_all_machines": scheduling_service.generate_optimal_schedule_all_machines,
            "recalculate_delivery_dates": scheduling_service.recalculate_delivery_dates,
        }

    def _validate_parameters(self, func: ToolCallable, params: Dict[str, Any]):
        """
        Valida que los parámetros proporcionados por el LLM coincidan con la firma de la función de la herramienta. Específicamente con los parámetros requeridos.
        """
        sig = inspect.signature(func)
        required_params = {
            p.name for p in sig.parameters.values() 
            if p.default is inspect.Parameter.empty
        }
        provided_params = set(params.keys())
        missing_params = required_params - provided_params
        if missing_params:
            raise ValidationError(f"Parametros faltantes para la siguiente acción: {', '.join(missing_params)}")
        #extra_params = provided_params - required_params
        #if extra_params:
        #    raise ValidationError(f"Parametros extra proporcionados para la siguiente acción: {', '.join(extra_params)}")

    async def dispatch(self, action: str, parameters: Dict[str, Any]) -> CommandResponse:
        """
        Busca y ejecuta la herramienta correspondiente a la acción.
        """
        if action not in self.tool_map:
            logger.warning(f"Intento de despacho de una acción no reconocida: '{action}'.")
            raise DispatcherError(f"Acción '{action}' no reconocida o no implementada.", status_code=404)
            
        # Busca la función de la herramienta en el mapa
        tool_function = self.tool_map[action]
        
        try:
            # Validar parametros ANTES de llamar a la función
            self._validate_parameters(tool_function, parameters)

            # Desempaqueta los parámetros y llama a la función de la herramienta
            logger.info(f"Ejecutando Herramienta '{action}' con los parámetros: {parameters}")
            return await tool_function(**parameters)
        except (ValidationError, TypeError) as e:
            logger.error(f"Error de validación para la acción '{action}': {str(e)}")
            raise e # Relanzamos para que el endpoint lo capture y devuleva un 402

        except Exception as e:
            # Captura los errores inesperados DENTRO de la ejecución de una herramienta
            logger.error(f"Error inesperado al ejecutar la acción '{action}': {str(e)}", exc_info=True)
            raise DispatcherError(f"Error inesperado al ejecutar la acción '{action}': {str(e)}")