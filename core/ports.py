from abc import ABC, abstractmethod
from typing import Dict, Any, List

class AbstractLanguageAgent(ABC):
    """
    Define la interfaz o puerto para un agente de lenguaje inteligente. Cualquier proveedor de LLM (OpenAI, Gemini, etc.) debe implementar esta clase.
    """

    @abstractmethod
    async def process_command(self, user_message: str) -> Dict[str, Any]:
        """
        Toma un mensaje de usuario en lenguaje natural y lo traduce a una
        acción estructurada con parámetros.

        Args:
            user_message: El texto plano del usuario.

        Returns:
            Un diccionario con la 'action' y los 'parameters' interpretados.
            Ej: {"action": "prioritize_order", "parameters": {"order_id": "123"}}
        """
        pass

    @abstractmethod
    async def check_connection(self) -> tuple[bool, List]:
        """
        Verifica la conectividad con el servicio de IA subyacente.
        Debe lanzar una excepcion si la conexión falla.
        """
        pass