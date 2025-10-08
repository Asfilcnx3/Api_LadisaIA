from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

# Se usa el Basemodel para definir la estructura de nuestros datos.
class MachineModel(BaseModel): # Listo para producción
    """Representa una máquina en la base de datos."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str = Field(alias="nombre")
    max_width: int = Field(alias='ancho_maximo')
    inks: int = Field(alias='numero_tintas')
    plant: int = Field(alias='planta')
    pseudonym: Optional[str] = Field(alias='seudonimo')
    share_rolls: Optional[str] = Field(alias='comparte_rodillos')
    time_change_units: float = Field(alias='tiempo_cambio_unidad')
    avg_velocity: float = Field(alias='velocidad_promedio')
    estatus: str = Field(..., description="Ej: 'activa', 'mantenimiento', 'error', 'desactivada'")
    functional_inks: int = Field(alias='tintas_funcionando')

class MermaReasonModel(BaseModel):
    """Representa una razón de merma registrada en la base de datos."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    active: bool = True

class MermaModel(BaseModel):
    """Representa una merma registrada en la base de datos."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    process: str = Field(..., description="Ej: 'impresión', 'corte', 'doblado', 'laminación', 'segunda_laminación'")
    reason_id: int
    quantity: float
    observations: Optional[str] = None
    user_id: int

class PedidoModel(BaseModel):
    """Representa los datos esenciales de un pedido."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    product_id: int
    total_kg: float
    status: int

class OrderModel(BaseModel):
    """Representa una orden de producción en la base de datos."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str = Field(..., description="Ej: 'impresión', 'pendiente', 'en_proceso', 'completada'")
    total_kg: float
    printed_kg: float
    num_colors: int
    assigned_machine_id: Optional[str] = None
    priority: int = 0

class ProductionQueueItem(BaseModel):
    """Representa la posición de una orden en la cola de producción."""
    model_config = ConfigDict(from_attributes=True)

    order_id: OrderModel
    machine_id: Optional[MachineModel] = None
    sequence_order: int

class OrderModelforOrder(BaseModel):
    """Representa un item en la cola de producción."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    machine_id: int
    order_production: int

class SchedulableOrderModel(BaseModel):
    """Representa los datos de un pedido listos para ser planificados."""
    model_config = ConfigDict(from_attributes=True)

    id_en_cola: Optional[int] = None # Nuevo campo para la posición en la cola

    id: int
    producto_id: int
    status: int
    datos: str # Mantenemos el JSON como string por ahora
    fecha_entrega: Optional[datetime]
    fecha_forzosa_entrega: Optional[datetime]
    prioridad_planeacion: int
    dias_restantes: Optional[int]
    producto_nombre: str
    cantidad: str
    colores: Optional[str]
    num_colores: int
    materiales: str
    total_peso_neto: float
    total_metros_impresion: float
    num_etiquetas: int

class SchedulableOrdersFromMachine(BaseModel):
    """Representa los datos de un pedido listos para ser planificados."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    producto_id: int
    status: int
    datos: str # Mantenemos el JSON como string por ahora
    fecha_entrega: Optional[datetime]
    fecha_forzosa_entrega: Optional[datetime]
    prioridad_planeacion: int
    dias_restantes: Optional[int]
    producto_nombre: str
    id_en_cola: int
    order_production: int
    probable_fecha_entrega: Optional[datetime]
    razon: Optional[str]
    cantidad: str
    colores: Optional[str]
    num_colores: int
    materiales: str
    total_peso_neto: float
    total_metros_impresion: float
    num_etiquetas: int

class SchedulableAllMachineModel(BaseModel):
    """Representa los datos de una máquina listos para ser planificados."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    producto_id: int
    status: int
    datos: str # Mantenemos el JSON como string por ahora
    fecha_entrega: Optional[datetime]
    fecha_forzosa_entrega: Optional[datetime]
    prioridad_planeacion: int
    dias_restantes: Optional[int]
    producto_nombre: str
    cantidad: str
    colores: Optional[str]
    num_colores: int
    materiales: str
    total_peso_neto: float
    total_metros_impresion: float
    num_etiquetas: int
    maquina_id: str # Nuevo campo para saber la máquina asignada