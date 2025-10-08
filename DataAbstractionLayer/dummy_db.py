from typing import List, Optional, Dict
from datetime import datetime
import uuid

from .base import BaseDatabase
from schemas.db_models import MachineModel, OrderModel, ProductionQueueItem

class DummyDB(BaseDatabase):
    """
    Implementación dummy para el MVP. Simula una base de datos en memoria
    Utilizando moedelos Pydantic para garantizar la consistencia de los datos y los tipos.
    """
    
    def __init__(self):
        # Almacenamos instancias de modelos Pydantic, no con diccionarios o datos brutos.
        self._machines: Dict[str, MachineModel] = {
            m.id: m for m in [
                MachineModel(id="Titán", name="Máquina Titán", status="active", total_units=6, active_units=6, current_order_id=None),
                MachineModel(id="Heidelberg", name="Máquina Heidelberg", status="active", total_units=8, active_units=8, current_order_id="123456"),
                MachineModel(id="A", name="Máquina A", status="active", total_units=4, active_units=4, current_order_id="789012"),
                MachineModel(id="B", name="Máquina B", status="maintenance", total_units=4, active_units=4, current_order_id=None),
            ]
        }
        
        self._orders: Dict[str, OrderModel] = {
            o.id: o for o in [
                OrderModel(id="123456", name="Etiquetas Premium", total_kg=500, num_colors=4, printed_kg=350, assigned_machine_id="Heidelberg", status="in_progress", priority=2),
                OrderModel(id="789012", name="Empaque Especial", total_kg=200, num_colors=2, printed_kg=180, assigned_machine_id="A", status="in_progress", priority=1),
                OrderModel(id="555777", name="Bolsas Comerciales", total_kg=300, num_colors=3, printed_kg=0, assigned_machine_id=None, status="pending", priority=0),
            ]
        }
        
        self._production_queue: List[ProductionQueueItem] = [
            ProductionQueueItem(order_id=self._orders["123456"], machine_id=self._machines["Heidelberg"], sequence_order=1),
            ProductionQueueItem(order_id=self._orders["789012"], machine_id=self._machines["A"], sequence_order=2),
            ProductionQueueItem(order_id=self._orders["555777"], machine_id=None, sequence_order=3)
        ]
        
        self._roll_weights = []
        self._waste_records = []

    # Las firmas de los métodos y los tipos de retorno coinciden con BaseDatabase.
    async def get_machine_by_id(self, machine_id: str) -> Optional[MachineModel]:
        return self._machines.get(machine_id)
    
    async def get_order_by_id(self, order_id: str) -> Optional[OrderModel]:
        return self._orders.get(order_id)

    async def check_connection(self) -> bool:
        """
        Simula una comprobación de conexión para la base de datos en memoria.
        como siempre está "Conectada", simplmemente devuelve True
        """
        return True
    
    async def update_machine_status(self, machine_id: str, status: str, disable_units: Optional[int] = None) -> bool:
        if machine := self._machines.get(machine_id):
            machine.status = status
            if disable_units is not None:
                machine.active_units = machine.total_units - disable_units
            return True
        return False
    
    async def get_production_queue(self, machine_id: Optional[str] = None) -> List[ProductionQueueItem]:
        queue_copy = self._production_queue.copy()
        if machine_id:
            return [item for item in queue_copy if item.machine and item.machine.id == machine_id]
        return queue_copy
    
    async def prioritize_order(self, order_id: str, machine_id: Optional[str] = None, reorder_rest: bool = True) -> bool:
        target_item_index = -1
        for i, item in enumerate(self._production_queue):
            if item.order_id.id == order_id:
                target_item_index = i
                break
        
        if target_item_index == -1:
            return False
        
        # Mover el item al principio de la cola
        order_item = self._production_queue.pop(target_item_index)

        if machine_id and machine_id in self._machines:
            order_item.machine = self._machines[machine_id]

        self._production_queue.insert(0, order_item)
        
        # Re-indexar las posiciones si es necesario
        if reorder_rest:
            for i, item in enumerate(self._production_queue):
                item.sequence_order = i + 1
        else:
            order_item.sequence_order = 0 # 0 para la máxima prioridad sin afectar al resto
        
        return True
    
    async def register_roll_weight(self, machine_id: str, order_id: str, weight_kg: float) -> bool:
        record = {
            "id": str(uuid.uuid4()), "machine_id": machine_id, 
            "order_id": order_id, "weight_kg": weight_kg, "timestamp": datetime.now()
        }
        self._roll_weights.append(record)
        return True
    
    async def register_waste(self, order_id: str, machine_id: str, weight_kg: float, reason: str) -> bool:
        record = {
            "id": str(uuid.uuid4()), "order_id": order_id, "machine_id": machine_id, 
            "weight_kg": weight_kg, "reason": reason, "timestamp": datetime.now()
        }
        self._waste_records.append(record)
        return True
    
    async def get_all_machine_status(self) -> List[MachineModel]:
        return list(self._machines.values())
    
    async def get_machine_by_name_or_pseudonym(self, name: str) -> Optional[MachineModel]:
        """Implementación en memoria para buscar por nombre o seudónimo."""
        for machine in self._machines.values():
            if machine.name == name or machine.pseudonym == name:
                return machine
        return None