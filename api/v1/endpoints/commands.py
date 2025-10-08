import logging

from fastapi import APIRouter, HTTPException, Depends

from schemas.api_models import CommandRequest, CommandResponse, HealthAgentResponse
from core.ports import AbstractLanguageAgent
from core.adapters import OpenAIAgentAdapter
from core.dispatcher import ToolDispatcher
from api.v1.dependencies import get_agent_instance, get_tool_dispatcher
from core.exceptions import BaseAppException, AgentError
from core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/process", # Ruta simplificada
    response_model=CommandResponse,
    summary="Procesa un comando de lenguaje natural",
    description="Recibe texto, lo interpreta con un agente de IA y ejecuta la acción correspondiente."
)
async def process_command(
    request: CommandRequest,
    agent: OpenAIAgentAdapter = Depends(get_agent_instance),
    dispatcher: ToolDispatcher = Depends(get_tool_dispatcher)
):
    try:
        logger.info(f"Procesando comando del usuario '{request.user_id or 'anonymous'}: '{request.text}'")

        # 1. Interpretar el comando con el agente de IA (usando Tool Calling)
        interpreted_command = await agent.process_command(request.text)
        print(interpreted_command)
        
        action = interpreted_command.get("action")
        parameters = interpreted_command.get("parameters", {})
        print(action)
        print(parameters)

        # Manejar caso donde el agente no puede determinar una acción
        if action == "unknown_request":
            logger.warning(f"Comando no reconocido por el agente: '{request.text}'")
            return CommandResponse(
                success=False, 
                message="No se pudo interpretar la instrucción. Por favor intenta reformular la pregunta.",
                action_executed=action
            )
        if action == "error":
            logger.error(f"Error del agente de IA: {interpreted_command.get('message')}")
            return CommandResponse(
                success=False,
                message=f"Error del agente de IA: {interpreted_command.get('raw_response')}",
                action_executed=action
            )

        # 2. Despachar y ejecutar la acción correspondiente
        result = await dispatcher.dispatch(action, parameters)
        return result
        
    except BaseAppException as e:
        # Captura nuestras excepciones e negocio personalizadas y las convierte en respuesta HTTP con el código de estado apropiado.
        logger.error(f"Error de aplicación manejando: {e.status_code} - {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)

    except Exception as e: # Ultimo recurso
        # Captura errores inesperados a nivel de la API los cuales son totalmente inesperados
        logger.critical(f"Error interno no manejado: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ocurrió un error interno inesperado en el servidor: {str(e)}.")

@router.get(
    "/health", 
    response_model=HealthAgentResponse,
    summary="Verifica la salud del servicio y sus dependencias (Agente de IA)",
    description="Verifica la salud del servicio y sus dependencias (Agente de IA)"
)
async def agent_status_check(agent: AbstractLanguageAgent = Depends(get_agent_instance)):
    """
    Verifica que el servicio e procesamiento de comandos pueda conectarse
    exitosamente a su dependencia principal: el agende de lenguaje (OpenAI).
    """
    try:
        _, models = await agent.check_connection()
        return HealthAgentResponse(
            status="healthy",
            message="El agente de IA está conectado y operativo.",
            model_in_use=settings.OPENAI_MODEL,
            models=models
        )
    except AgentError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "message": "El agente de IA no está conectado u operativo (servicio no disponible).",
                "error": str(e)
            }
        )