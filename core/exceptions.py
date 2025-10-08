class BaseAppException(Exception):
    """Clase base para excepciones personalizadas en esta aplicación."""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class AgentError(BaseAppException):
    """Se lanza cuando hay un error en la comunicación o lógica del agente de IA."""
    def __init__(self, message: str, status_code: int = 502): # 502 Bad Gateway es apropiado
        super().__init__(message, status_code)

class DispatcherError(BaseAppException):
    """Se lanza cuando hay un error al despachar o ejecutar una herramienta."""
    def __init__(self, message: str, status_code: int = 400): # 400 Bad Request es apropiado
        super().__init__(message, status_code)

class ValidationError(DispatcherError):
    """Se lanza cuando los parámetros para una herramienta no son válidos."""
    def __init__(self, message: str):
        super().__init__(message, status_code=422) # 422 Unprocessable Entity es más específico