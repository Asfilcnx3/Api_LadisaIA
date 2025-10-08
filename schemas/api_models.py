from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from .db_models import MachineModel, OrderModel, ProductionQueueItem

# --- Modelos de Petición (Lo que el cliente envía) ---

class CommandRequest(BaseModel):
    """Modelo para la petición principal de un comando de lenguaje natural."""
    text: str = Field(..., min_length=1, description="Texto del comando en lenguaje natural.")
    user_id: Optional[str] = Field(None, description="Id de usuario (opcional)")
    context: Optional[Dict[str, Any]] = Field(None, description="Contexto adicional (opcional)")

    @field_validator("text")
    @classmethod
    def text_must_not_be_empty(cls, v: str) -> str:
        """
        Validador que asegura que el texto de entrada, no esté vacio o solo contenga espacios.
        """
        if not v.strip():
            raise ValueError("El texto no puede estar vacío o solo contener espacios")
        return v

class ImageComparisonRequest(BaseModel):
    """Modelo para peticiones de comparación de imágenes."""
    order_id: str
    reference_image_url: str = Field(..., description="URL de la imagen de referencia.")
    printed_image_url: str = Field(..., description="URL de la imagen impresa para comparar.")

class OrderRequest(BaseModel):
    order_id: str
    priority: int
    
    @field_validator('priority')
    def validate_priority(cls, v):
        if not 1 <= v <= 10:
            raise ValueError("La prioridad debe estar entre 1 y 10")
        return v

# --- Modelos de Respuesta (Lo que la API devuelve) ---

class CommandResponse(BaseModel):
    """Modelo genérico para respuestas de la API tras ejecutar un comando."""
    success: bool = Field(..., description="Indica si el comando se ejecutó exitosamente")
    message: str = Field(..., description="Mensaje descriptivo de la respuesta para el usuario")
    action_executed: Optional[str] = Field(None, description="Nombre de la acción ejecutada (opcional)")
    data: Optional[Any] = Field(None, description="Datos adicionales de la respuesta (opcional)")

class HealthCheckResponse(BaseModel):
    """Modelo para la respuesta del endpoint de health check."""
    status: str = Field("healthy", description="Estado del servicio")
    service: str = Field("Imprenta Inteligente API", description="Nombre del servicio")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp de la respuesta")
    database_status: str = Field("connected", description="Estado de la base de datos")
    database_type: str = Field("dummy", description="Tipo de base de datos")

class HealthAgentResponse(BaseModel):
    """Modelo para la respuesta del endpoint de health check del agente de IA."""
    status: str = Field("healthy", description="Estado del agente de IA")
    service: str = Field("Agente de IA", description="Nombre del agente")
    message: str = Field("El agente de IA está conectado y operativo.", description="Mensaje descriptivo de la respuesta para el usuario") 
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp de la respuesta")
    model_in_use: str = Field("dummy", description="Modelo de IA en uso")
    models: List[str] = Field(..., description="Lista de modelos disponibles")

class OrderStatusResponse(BaseModel):
    """Modelo detallado para la respuesta del estado de una orden."""
    # Datos básicos del pedido
    pedido_id: int = Field(..., description="ID del pedido")
    producto_nombre: str = Field(..., description="Nombre del producto")
    estatus_pedido: int = Field(..., description="Estado del pedido")

    # Datos de producción
    esta_en_cola: bool = Field(..., description="Indica si el pedido está en cola")
    maquina_asignada_id: Optional[int] = Field(None, description="ID de la máquina asignada (opcional)")
    posicion_en_cola: Optional[int] = Field(None, description="Posición en la cola (opcional)")
    fecha_probable_entrega: Optional[datetime] = Field(None, description="Fecha probable de entrega (opcional)")

    # Datos de progreso
    kilos_requeridos: float = Field(..., description="Kilos requeridos para completar el pedido")
    kilos_impresos: float = Field(..., description="Kilos impresos hasta el momento")
    porcentaje_progreso: float = Field(..., description="Porcentaje de progreso del pedido")

class MachineStatusDetail(BaseModel):
    """Contiene la información de una máquina y el detalle de su orden actual."""
    machine: MachineModel
    current_order: Optional[OrderStatusResponse] = None # Reutilizamos el modelo que ya creamos

# Este será el modelo principal de la respuesta
class AllMachinesStatusResponse(BaseModel):
    """Respuesta para el estado de una o todas las máquinas."""
    machines_count: int
    machines_details: List[MachineStatusDetail]

class ErrorResponse(BaseModel):
    """Modelo para respuestas de error estandarizadas."""
    detail: str = Field(..., description="Mensaje de error descriptivo")