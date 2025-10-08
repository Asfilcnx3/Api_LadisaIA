from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from schemas.api_models import OrderStatusResponse
from schemas.db_models import MermaModel, MermaReasonModel, PedidoModel, OrderModelforOrder, SchedulableOrderModel, MachineModel, SchedulableAllMachineModel, SchedulableOrdersFromMachine

class BaseDatabase(ABC):
    """
    Capa de abstracción para operaciones de base de datos.
    Utiliza modelo pydantic para garantizar la seguridad de tipos y la valiación de datos.
    """

    @abstractmethod
    async def get_machine_by_id(self, machine_id: str) -> Optional[MachineModel]:
        """Obtiene información de una máquina por ID."""
        pass
    
    @abstractmethod
    async def update_machine_status(self, machine_id: str, status: Optional[str] = None, functional_inks: Optional[int] = None) -> bool:
        """Actualiza el estado y/o las unidades de una máquina"""
        pass
    
    @abstractmethod
    async def register_roll_weight(self, machine_id: str, order_id: str, weight_kg: float) -> bool:
        """Registra el peso de un rollo asociado a una orden o máquina."""
        pass
    
    @abstractmethod
    async def register_waste_record(self, order_id: str, process: str, reason_id: int, quantity: float, observations: str, user_id: int) -> MermaModel:
        """Registra desperdicios asociados a una orden y máquina."""
        pass

    @abstractmethod
    async def get_waste_reason_by_name(self, reason_id: int) -> Optional[MermaReasonModel]:
        """Obtiene la razón de desperdicio por ID."""
        pass

    @abstractmethod
    async def get_order_by_id(self, order_id: int) -> Optional[PedidoModel]: # todavía no se usa
        """Busca un pedido por su ID."""
        pass
    
    @abstractmethod
    async def get_all_machine_status(self) -> List[MachineModel]:
        """Obtiene una lista con el estado de todas las maquinas."""
        pass
    
    @abstractmethod
    async def get_full_order_status_details(self, pedido_id: int) -> Optional[OrderStatusResponse]:
        """
        Obtiene todos los detalles necesarios para el estado de una orden,
        combinando información de pedido, productos, etiquetas y la cola de producción.
        """
        pass

    @abstractmethod
    async def check_connection(self) -> bool:
        """
        Verifica la conectividad con la base de datos. Debe lanzar una excepción si la conexión falla.
        """
        pass

    @abstractmethod
    async def get_order_position_in_queue(self, pedido_id: int) -> Optional[OrderModelforOrder]:
        """
        Busca la posición de una orden en la cola de producción actual.
        """
        pass

    @abstractmethod
    async def get_machines_status_with_details(self, machine_id: Optional[int] = None) -> List[Dict]:
        """
        Obtiene el estado de una o todas las máquinas, incluyendo los detalles
        y el progreso de la orden que está en la primera posición de su cola.
        """
        pass

    @abstractmethod
    async def get_machine_by_name_or_pseudonim(self, name: str) -> Optional[MachineModel]:
        """Obtiene información de una máquina por nombre o seudónimo."""
        pass

    @abstractmethod
    async def get_queue_item_by_pedido_id(self, pedido_id: int) -> Optional[OrderModelforOrder]:
        """Busca un item de la cola por su pedido_id."""
        pass

    @abstractmethod
    async def get_production_queue_for_machine(self, maquina_id: int) -> List[OrderModelforOrder]:
        """
        Obtiene la cola de producción actual para una máquina, ya enriquecida con todos
        los detalles necesarios para el cálculo de fechas.
        """
        pass

    @abstractmethod
    async def update_production_queue(self, updates: List[Dict[str, Any]]) -> bool:
        """Aplica actualizaciones de orden a múltiples registros de la cola."""
        pass

    @abstractmethod
    async def get_schedulable_orders_for_machine(self, maquina_id: int) -> List[SchedulableOrderModel]:
        """Ejecuta la consulta compleja para obtener los pedidos planificables de una máquina."""
        pass

    @abstractmethod
    async def overwrite_machine_schedule(self, maquina_id: int, new_schedule: List[Dict[str, Any]]) -> bool:
        """Borra la planificación actual de una máquina y la reemplaza con la nueva secuencia."""
        pass

    @abstractmethod
    async def get_schedulable_orders_for_all_machines(self) -> List[SchedulableAllMachineModel]:
        """Ejecuta la consulta para obtener todos los pedidos planificables de todas las máquinas."""
        pass

    @abstractmethod
    async def update_queue_dates_and_times(self, updates: List[Dict[str, Any]]) -> bool:
        """
        Actualiza en bloque los campos de tiempo y fecha para registros existentes
        en la tabla de la cola de producción.
        """
        pass

    @abstractmethod
    async def get_schedulable_orders_by_ids(self, order_ids: List[int]) -> List[SchedulableOrdersFromMachine]:
        """
        Ejecuta la consulta compleja para obtener los detalles completos de una lista específica
        de IDs de pedidos.
        """
        pass

    # Aquí deben ir el resto de los métodos, deben estar actualizados para usar los modelos Pydantic