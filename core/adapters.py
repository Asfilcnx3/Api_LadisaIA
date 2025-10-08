import json
import logging
from openai import AsyncOpenAI, APIError
from typing import Dict, Any, List

from core.config import settings
from core.exceptions import AgentError
from core.ports import AbstractLanguageAgent # <-- Implementa nuestra interfaz

logger = logging.getLogger(__name__)

# La definición de herramientas es específica de este adaptador (OpenAI)
TOOLS_DEFINITION: List[Dict[str, Any]] = [
    { # Funciona en la programación real de la bdd
        "type": "function",
        "function": {
            "name": "ignore_machine",
            "description": "Pone una o varias máquinas en estado de mantenimiento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_ids": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        }, 
                        "description": "Una lista con los identificadores (ID, nombre exacto o seudónimo) de las máquinas a poner en mantenimiento. Ej: ['Titán', 'Heidelberg', '1']"
                    }
                },
                "required": ["machine_ids"]
            }
        }
    },
    { # Funciona en la programación real de la bdd
        "type": "function",
        "function": {
            "name": "reactivate_machine",
            "description": "Reactiva una o más máquinas que estaban en mantenimiento, poniéndolas de nuevo en estado 'activo' para que puedan recibir órdenes de producción.",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_ids": {
                        "type": "array", 
                        "items": {
                            "type": "string"
                        }, 
                        "description": "Una lista con los nombres o IDs de las máquinas a reactivar. Ej: ['Titán', 'Heidelberg']"
                    }
                },
                "required": ["machine_ids"]
            }
        }
    },
    { # Funciona en la programación real de la bdd
        "type": "function",
        "function": {
            "name": "query_machine_status",
            "description": "Consulta el estado, unidades activas o la orden en curso de una o todas las máquinas en producción.",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_identifier": {"type": "string", "description": "Opcional. ID o Nombre de la máquina. Si se omite, se devolverá el estado de todas las máquinas."}
                },
                "required": []
            }
        }
    },
    { # Funciona en la programación real de la bdd
        "type": "function",
        "function": {
            "name": "register_waste",
            "description": "Registra una cantidad de desperdicio (merma) para una orden de producción específica.",
            "parameters": {
                "type": "object",
                "properties": {
                "pedido_id": {
                    "type": "integer",
                    "description": "El ID numérico de la orden de producción (pedido) a la que se le asignará el desperdicio."
                },
                "weight_kg": {
                    "type": "number",
                    "description": "La cantidad de desperdicio en kilogramos."
                },
                "reason": {
                    "type": "string",
                    "description": "La razón del desperdicio. Por ejemplo: 'Error de color', 'Ajuste de máquina'."
                },
                "observations": {
                    "type": "string",
                    "description": "Opcional. Observaciones adicionales sobre el desperdicio."
                },
            },
            "required": ["pedido_id", "weight_kg", "reason"]
            }
        }
    },
    { # Funciona en la programación real de la bdd
        "type": "function",
        "function": {
            "name": "disable_machine_units",
            "description": "Reduce la capacidad en una máquina especificando un número de uniades de tinta que no funcionan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {"type": "string", "description": "Nombre o ID de la máquina. Ej: 'IMPOBOL', 'FLEXOTECNICA', '1'"},
                    "units_to_disable": {"type": "integer", "description": "Número de unidades de tinta que no funcionan o desabilitadas"}
                },
                "required": ["machine_id", "units_to_disable"]
            }
        }
    },
    { # Funciona en la programación real de la bdd
        "type": "function",
        "function": {
            "name": "enable_machine_units",
            "description": "Restaura las unidades tinta de una máquina. Por defecto restaura todas, pero se puede especificar un número exacto a restaurar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_id": {"type": "string", "description": "El nombre, pseudónimo o ID de la máquina. Ej: 'IMPOBOL', 'FLEXOTECNICA', '1'"},
                    "units_to_enable": {"type": "integer", "description": "Opcional. El número de unidades que se quieren restaurar. Si se omite, se restaurarán todas las unidades deshabilitadas."}
                },
                "required": ["machine_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_optimal_schedule",
            "description": "Ejecuta el algoritmo de optimización para generar una nueva cola de producción para una máquina específica. Esto borra la planificación anterior y la reemplaza.",
            "parameters": {
                "type": "object",
                "properties": {
                    "maquina_identifier": { 
                        "type": "string", 
                        "description": "El ID, nombre o seudónimo de la máquina para la cual generar la planificación. (Ej: '1', 'IMPOBOL', 'FLEXOTECNICA')"
                    }
                },
            "required": ["maquina_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_optimal_schedule_all_machines",
            "description": "Ejecuta el algoritmo de optimización para generar una nueva cola de producción para todas las máquinas. Esto borra la planificación anterior y la reemplaza.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reoptimize": { 
                        "type": "boolean", 
                        "description": "Si es 'true', se reoptimiza toda la planificación actual. Si es 'false' (por defecto), solo se genera una nueva planificación si la máquina está inactiva o sin planificación."
                    }
                },
            "required": ["reoptimize"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "prioritize_pedido",
            "description": "Establece un pedido como máxima prioridad. Puede hacerse con o sin reoptimización del resto de la cola.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pedido_id": {
                        "type": "integer",
                        "description": "El ID numérico del pedido que se va a priorizar."
                    },
                    "reoptimize": {
                        "type": "boolean",
                        "description": "Si es 'true', el resto de la cola se reoptimiza. Si es 'false' (por defecto), solo se mueve el pedido al inicio."
                    }
                },
                "required": ["pedido_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recalculate_delivery_dates",
            "description": "Recalcula las fechas de entrega de una máquina en función de su nueva prioridad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "maquina_identifier": { 
                        "type": "string", 
                        "description": "El ID, nombre o seudónimo de la máquina para la cual generar la planificación. (Ej: '1', 'IMPOBOL', 'FLEXOTECNICA')"
                    }
                },
            "required": ["maquina_identifier"]
            }
        }
    },
    { # Por definir como funcionará en producción
        "type": "function",
        "function": {
            "name": "query_order_status",
            "description": "Consulta el estado, progreso o fecha de entrada de una orden en producción.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pedido_id": {"type": "string", "description": "El ID numérico de la orden de producción (pedido)."}
                },
                "required": ["pedido_id"]
            }
        }
    },
    # { # Por definir como funcionará en producción
    #     "type": "function",
    #     "function": {
    #         "name": "register_roll_weight",
    #         "description": "Registra el peso de un rollo para la orden actual de una máquina, especificando el peso del rollo y la maquina.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "machine_id": {"type": "string", "description": "Nombre o ID de la máquina"},
    #                 "weight_kg": {"type": "integer", "description": "Cantidad de peso del rollo en kilogramos"}
    #             },
    #             "required": ["machine_id", "weight_kg"]
    #         }
    #     }
    # },
    { # Herramienta especial para peticiones no reconocidas
        "type": "function",
        "function": {
            "name": "unknown_request",
            "description": "Se utiliza cuando la petición del usuario no corresponde a ninguna de las herramientas disponibles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_request": {"type": "string", "description": "La petición original del usuario que no pudo ser entendida."}
                },
                "required": ["user_request"]
            }
        }
    }
]

class OpenAIAgentAdapter(AbstractLanguageAgent): # <-- Hereda de la interfaz
    """
    Adaptador que implementa la interfaz AbstractLanguageAgent utilizando el servicio de OpenAI.
    """
    
    def __init__(self): # Instanciamos el cliente asíncrono.
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.system_prompt = self._build_system_prompt()
        
    def _build_system_prompt(self) -> str:
        """Construye el prompt del sistema que define el rol del asistente."""
        return (
            "Eres un asistente experto en la gestión de producción de una imprenta. "
            "Tu tarea es analizar la petición del usuario y utilizar la herramienta (función) adecuada para cumplirla. "
            "Si la petición es ambigua o no corresponde a ninguna herramienta, utiliza la herramienta 'unknown_request'."
        )
    
    async def process_command(self, user_message: str) -> Dict[str, Any]:
        """
        Procesa un comando de usuario utilizando Tool Calling y devuelve la acción estructurada.
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message}
        ]

        try:
            # Hacemos la llamada a la API especificando las herramientas disponibles.
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                tools=TOOLS_DEFINITION,
                tool_choice="auto"
            )
            
            # Extraer el contenido de la respuesta
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls
            
            # Verificamos si el modelo decidió usar una herramienta.
            if tool_calls:
                tool_call = tool_calls[0] # la primera llamada
                action_name = tool_call.function.name
                # Los argumentos ya vienen parseados como un diccionario
                action_args = json.loads(tool_call.function.arguments)
                
                logger.info(f"Agente interpretó la acción: {action_name} con los parametros: {action_args}")
                return {
                    "action": action_name,
                    "parameters": action_args
                }
            else:
                logger.warning(f"El modelo no seleccionó una herramienta para el mensaje {user_message}.")
                return { # Si el modelo no eligió una herramienta, lo consideramos un fallo.
                    "action": "error",
                    "message": "El modelo no seleccionó una herramienta.",
                    "raw_response": response_message.content
                }
        except APIError as e:
            # Captura errores específicos de la API de OpenAI (ej. 401, 500, etc.)
            logger.error(f"Error en la API de OpenAI: {e.status_code} - {e.error}")
            raise AgentError(f"El servicio de IA no está disponible o encontró un error: {e.message}")
        except Exception as e:
            # Captura otros errores inesperados durante la llamada (ej. timeouts)
            logger.error(f"Error inesperado al procesar el comando con el agente: {e}", exc_info=True)
            raise AgentError(f"Error inesperado al conectar con el servicio de IA: {e}")

    async def check_connection(self) -> tuple[bool, List]:
        """
        Verifica la conectividad con la API de OpenAI haciendo una llamada ligera y de bajo costo para listar los modelos disponibles.
        """
        try:
            # client.models.list() es una llamada barata que valida la API key y la disponibilidad de servicio
            models = await self.client.models.list()
            logger.info("Conexión con la API de OpenAI verificada exitosamente.")
            
            models_id = [m.id for m in models.data]
            return True, models_id
        except APIError as e:
            logger.error(f"Error al verificar la conectividad con la API de OpenAI: {e.message}")
            raise AgentError(f"No se pudo conectar al servicio de IA: {e.message}")
    
    # def validate_command(self, command: Dict[str, Any]) -> tuple[bool, str]:
    #     """
    #     Valida que un comando tenga la estructura correcta
        
    #     Returns:
    #         tuple(is_valid, error_message)
    #     """
    #     if "action" not in command:
    #         return False, "Falta el campo 'action'"
        
    #     valid_actions = {
    #         "ignore_machine", "disable_machine_units", "prioritize_order", 
    #         "prioritize_order_only", "query_order_status", "query_machine_status",
    #         "query_production_schedule", "register_roll_weight", "register_waste",
    #         "compare_print_quality", "unknown", "error"
    #     }
        
    #     if command["action"] not in valid_actions:
    #         return False, f"Acción '{command['action']}' no válida"
        
    #     return True, ""