import logging
from enum import Enum
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import field_validator, model_validator, ValidationError
from pydantic_settings import BaseSettings

# Carga las variables de entorno desde un archivo .env si existe
load_dotenv()
logger = logging.getLogger(__name__)

class Environment(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

class Settings(BaseSettings):
    """
    Clase para gestionar la configuración de la aplicación
    Valida la presencia y formato de valirables crítivas al momento de la inicialización.
    """
    # --- Configuración del Entorno ---
    ENVIRONMENT: Environment = Environment.DEVELOPMENT

    # API Settings -- Configuración General
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Imprenta Inteligente API"
    APP_VERSION: str = "1.0.1"
    
    # Lista de origenes permitidos para CORS
    # Pydantic-settings convierte automáticamente un string JSON en una lista de Python.
    # Ejemplo en .env: BACKEND_CORS_ORIGINS='["http://localhost:3000", "https://el-frontend.com"]'
    BACKEND_CORS_ORIGINS: List[str] = ["*"]  # Por defecto permite todo para desarrollo

    # OpenAI Settings
    OPENAI_API_KEY: str # es obligatoria para que el servicio funcione
    OPENAI_MODEL: str = "gpt-5"
    
    # Database Settings -- Definir que implementación de la DAL se utilizará
    DATABASE_TYPE: str = "dummy"  # dummy, postgres, legacy
    DATABASE_URL: Optional[str] = None

    ## Development settings
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # WhatsApp/Twilio Settings (opcional para futuro)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_WHATSAPP_NUMBER: Optional[str] = None
    
    # File Upload Settings
    MAX_FILE_SIZE_MB: int = 10
    UPLOAD_DIR: str = "uploads"
    
    # Task Queue Settings (para comparación de imágenes)
    REDIS_URL: Optional[str] = None
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True

    @field_validator("OPENAI_API_KEY")
    @classmethod
    def validate_openai_api_key(cls, v: str) -> str:
        """
        Valida que la clave de OpenAI no esté vacía y tenga un formato plausible.
        """
        if not v:
            raise ValueError("La variable de entorno OPENAI_API_KEY no puede estar vacía.")
        if not v.startswith("sk-"):
            raise ValueError("OPENAI_API_KEY no comienza con 'sk-'. Podría ser inválida.")
        return v

    @model_validator(mode="after")
    def _consolidate_validations(self) -> "Settings":
        """
        # MEJORA: Se consolidan todos los validadores de modelo en uno solo para mayor claridad.
        Valida configuraciones que dependen de otras y ajusta reglas según el entorno.
        """
        # Regla 1: Si la base de datos es 'postgres', la URL de conexión es obligatoria.
        if self.DATABASE_TYPE == "postgres" and not self.DATABASE_URL:
            raise ValueError("Se requiere la variable de entorno DATABASE_URL cuando DATABASE_TYPE es 'postgres'.")

        # Regla 2: Lógica específica para el entorno de producción.
        if self.ENVIRONMENT == Environment.PRODUCTION:
            # En producción, CORS no debe ser un comodín.
            if "*" in self.BACKEND_CORS_ORIGINS:
                raise ValueError("En el entorno de PRODUCCIÓN, BACKEND_CORS_ORIGINS no puede contener '*'. Especifique los dominios permitidos.")
            
            # En producción, la base de datos no debería ser 'dummy'.
            if self.DATABASE_TYPE == "dummy":
                raise ValueError("En el entorno de PRODUCCIÓN, DATABASE_TYPE no puede ser 'dummy'.")
        
        # MEJORA: La advertencia de CORS ahora es más inteligente y solo se muestra en desarrollo.
        elif self.ENVIRONMENT == Environment.DEVELOPMENT and "*" in self.BACKEND_CORS_ORIGINS:
            logger.warning("CORS está configurado para permitir todos los orígenes. Adecuado para desarrollo, pero inseguro para producción.")
            
        return self

# INICIALIZACIÓN SEGURA 
# Se envuelve la creación de la instancia en un bloque try/except para
# capturar errores de validación y terminar la aplicación de forma controlada.
try:
    settings = Settings()
    logger.info(f"Configuración cargada exitosamente para el entorno: {settings.ENVIRONMENT.value}")
    # En producción, se recomienda usar un gestor de secretos (ej. AWS Secrets Manager, HashiCorp Vault) en lugar de archivos .env para manejar claves de API 
    # y otras credenciales sensibles. La validación de Pydantic seguirá siendo útil.
except ValidationError as e:
    # Si falta una variable crítica o tiene un formato incorrecto, el programa no se iniciará y mostrará un error claro.
    logger.critical(f"Error fatal: Faltan configuraciones críticas o son inválidas. No se puede iniciar la aplicación.")
    logger.critical(e)
    # Termina el proceso si la configuración es inválida.
    exit(1)