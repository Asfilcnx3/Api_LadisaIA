import logging
from typing import Optional
from DataAbstractionLayer.base import BaseDatabase
from typing import Union
from schemas.api_models import CommandResponse, OrderStatusResponse, MachineStatusDetail, AllMachinesStatusResponse
from schemas.db_models import MachineModel

logger = logging.getLogger(__name__)

class ProductionService:
    """
    Contiene la lógica de negocio (casos de uso) para las operaciones de producción.
    No conoce la API ni el agente, solo interactúa con la capa de datos.
    """
    def __init__(self, db: BaseDatabase):
        self.db = db

    async def ignore_machine(self, machine_ids: list[str]) -> CommandResponse: # Lista para producción
        """Lógica de negocio para poner una o más máquinas en mantenimiento."""
        try:
            # Lista de rastreo para cada resultado
            updated_machines = []
            not_found_machines = []
            already_in_maintenance = []

            if not machine_ids:
                return CommandResponse(
                    success=False, 
                    message="No se especificaron máquinas para poner en mantenimiento.", 
                    action_executed="ignore_machine", 
                    data=None
                )

            for machine_id in machine_ids:
                # Intenta buscar por ID primero, que es lo más eficiente.
                machine = await self.db.get_machine_by_id(machine_id)

                if not machine:
                    # Si no se encuentra por ID, intenta buscar por nombre o seudónimo.
                    machine = await self.db.get_machine_by_name_or_pseudonim(machine_id)

                # Caso 1: La máquina no existe
                if not machine:
                    not_found_machines.append(machine_id)
                    continue

                # Caso 2: La máquina ya está en mantenimiento
                if machine.estatus == "mantenimiento":
                    already_in_maintenance.append(machine_id)
                    continue
                
                # Caso 3: La máquina está en estado 'activo', se procede a ponerla en mantenimiento.
                success = await self.db.update_machine_status(machine.id, status="mantenimiento")
                if success:
                    # Usamos el identificador original para el mensaje de respuesta, que es más amigable.
                    updated_machines.append(machine_id)
            
            if not updated_machines and not not_found_machines:
                return CommandResponse(
                    success=False, 
                    message=f"Todas las máquinas especificadas ya estaban en mantenimiento o no existían.", 
                    action_executed="ignore_machine", 
                    data={
                        "updated": updated_machines,
                        "already_in_maintenance": already_in_maintenance,
                        "not_found": not_found_machines
                    }
                )

            # Construir un mensaje de respuesta claro y consolidado
            parts = []
            if updated_machines:
                parts.append(f"Puestas en mantenimiento: {updated_machines}")
            if already_in_maintenance:
                parts.append(f"Ya estaban en mantenimiento: {already_in_maintenance}")
            if not_found_machines:
                parts.append(f"No encontradas: {not_found_machines}")
        
            message = f"Operación completada. {'. '.join(parts)}."
        
            return CommandResponse(
                success=True, 
                message=message, 
                action_executed="ignore_machine", 
                data={
                    "updated": updated_machines, 
                    "already_in_maintenance": already_in_maintenance,
                    "not_found": not_found_machines
                }
            )

        except Exception as e:
            return CommandResponse(
                success=False, 
                message=f"Error inesperado al poner máquinas en mantenimiento: {e}", 
                action_executed="ignore_machine", 
                data=None
            )

    async def reactivate_machine(self, machine_ids: list[str]) -> CommandResponse: # Lista para producción
        """Lógica de negocio para sacar una o más máquinas de mantenimiento."""
        try:
            # Listas para rastrear el resultado de cada máquina
            reactivated_machines = []
            not_found_machines = []
            already_active_machines = []

            if not machine_ids:
                return CommandResponse(
                    success=False, 
                    message="No se especificaron máquinas para reactivar.", 
                    action_executed="reactivate_machine", 
                    data=None
                )

            for machine_id in machine_ids:
                machine = await self.db.get_machine_by_id(machine_id)
                
                if not machine:
                    # Si no se encuentra por ID, intenta buscar por nombre o seudónimo.
                    machine = await self.db.get_machine_by_name_or_pseudonim(machine_id)

                # Caso 1: La máquina no existe
                if not machine:    
                    not_found_machines.append(machine_id)
                    continue
            
            # <-- VALIDACIÓN: Verifica si la máquina realmente está en mantenimiento.
                if machine.estatus != "mantenimiento":
                    already_active_machines.append(machine_id)
                    continue

                # Caso 2: La máquina existe y está en mantenimiento, se procede a reactivar.
                success = await self.db.update_machine_status(machine.id, status="activa")
                if success:
                    reactivated_machines.append(machine_id)
        
            # Construir un mensaje de respuesta claro y consolidado
            parts = []
            if reactivated_machines:
                parts.append(f"Reactivadas: {reactivated_machines}")
            if already_active_machines:
                parts.append(f"Ya estaban activas: {already_active_machines}")
            if not_found_machines:
                parts.append(f"No encontradas: {not_found_machines}")

            message = f"Operación completada. {'. '.join(parts)}."

            return CommandResponse(
                success=True, 
                message=message, 
                action_executed="reactivate_machine",
                data={
                    "reactivated": reactivated_machines,
                    "already_active": already_active_machines,
                    "not_found": not_found_machines
                }
            )

        except Exception as e:
            return CommandResponse(
                success=False, 
                message=f"Error inesperado al reactivar máquinas: {e}", 
                action_executed="reactivate_machine",
                data=None
            )
        
    async def query_machine_status(self, machine_identifier: Optional[Union[str, int]] = None) -> CommandResponse:
        """
        Consulta el estado de una máquina específica o de todas, incluyendo
        el detalle y progreso de la orden actual.
        """
        try:
            target_machine_id: Optional[int] = None
            if machine_identifier:
                machine = None
                if isinstance(machine_identifier, int) or machine_identifier.isdigit():
                    machine = await self.db.get_machine_by_id(int(machine_identifier))
                else:
                    machine = await self.db.get_machine_by_name_or_pseudonim(machine_identifier)

                if not machine:
                    return CommandResponse(
                        success=False, 
                        message=f"Máquina '{machine_identifier}' no encontrada.",
                        action_executed="query_machine_status",
                        data=None
                    )
                target_machine_id = machine.id

            # --- 1. Llamar al método "Todo en Uno" de la DAL ---
            machine_details_from_db = await self.db.get_machines_status_with_details(target_machine_id)

            if not machine_details_from_db:
                return CommandResponse(
                    success=False, 
                    message="No se encontraron máquinas activas.",
                    action_executed="query_machine_status",
                    data=None
                )

            # --- 2. Procesar los resultados y construir los objetos de respuesta ---
            machines_details_list = []
            for row in machine_details_from_db:
                current_order_data = None
                # Si la consulta trajo información de un pedido (JOIN exitoso)
                if row['pedido_id']:
                    kilos_req = float(row['kilos_requeridos'])
                    kilos_imp = float(row['kilos_impresos'])
                    
                    current_order_data = OrderStatusResponse(
                        pedido_id=row['pedido_id'],
                        producto_nombre=row['producto_nombre'],
                        estatus_pedido=row['estatus_pedido'],
                        esta_en_cola=True,
                        maquina_asignada_id=row['id'],
                        posicion_en_cola=row['posicion_en_cola'],
                        fecha_probable_entrega=row['probable_fecha_entrega'],
                        kilos_requeridos=kilos_req,
                        kilos_impresos=kilos_imp,
                        porcentaje_progreso=round((100 * kilos_imp) / kilos_req, 1) if kilos_req > 0 else 0.0
                    )
                
                machine_data = MachineModel.model_validate(row) # Pydantic mapeará los campos coincidentes
                machines_details_list.append(
                    MachineStatusDetail(machine=machine_data, current_order=current_order_data)
                )

            # --- 3. Construir la respuesta final ---
            response_data = AllMachinesStatusResponse(
                machines_count=len(machines_details_list),
                machines_details=machines_details_list
            )

            message = f"Estado detallado de {len(machines_details_list)} máquina(s) recuperado."
            return CommandResponse(
                success=True, 
                message=message, 
                action_executed="query_machine_status", 
                data=response_data
            )

        except Exception as e:
            logger.error(f"Error al consultar el estado de las máquinas: {e}", exc_info=True)
            return CommandResponse(
                success=False, 
                message=f"Error inesperado al consultar máquinas: {e}",
                action_executed="query_machine_status",
                data=None
            )
        
    async def register_waste(self, pedido_id: int, weight_kg: float, reason: str, observations: str = "", user_id: int = 1) -> CommandResponse:
        """
        Lógica de negocio para registrar un desperdicio.
        1. Valida que el pedido exista.
        2. Valida que la razón de merma exista.
        3. Crea el registro en la base de datos.
        """
        try:
            # 1. Validar que el pedido existe
            pedido = await self.db.get_order_by_id(pedido_id)
            if not pedido:
                return CommandResponse(success=False, message=f"El pedido con ID '{pedido_id}' no fue encontrado.")

            # 2. Validar que la razón de merma exista
            waste_reason = await self.db.get_waste_reason_by_name(reason)
            if not waste_reason:
                return CommandResponse(success=False, message=f"La razón de merma '{reason}' no se encontró o no está activa.")

            # 3. Crear el registro de merma
            new_record = await self.db.register_waste_record(
                order_id=pedido.id,
                process="impresion", # O un valor por defecto
                reason_id=waste_reason.id,
                quantity=weight_kg,
                observations=observations,
                user_id=user_id # Esto debería venir del usuario autenticado
            )

            if new_record:
                message = f"Registrado desperdicio de {weight_kg}kg en el pedido {pedido.id} por '{waste_reason.name}'."
                return CommandResponse(success=True, message=message, action_executed="register_waste", data=new_record)

            return CommandResponse(success=False, message="No se pudo crear el registro de merma.", action_executed="register_waste", data=None)

        except Exception as e:
            return CommandResponse(
                success=False, 
                message=f"Error inesperado al registrar desperdicio: {e}", 
                action_executed="register_waste", 
                data=None
            )

    async def disable_machine_units(self, machine_id: str, units_to_disable: int) -> CommandResponse: # Funciona
        """
        Deshabilita un número de unidades de tinta activas en una máquina, validando la entrada
        y el estado actual de la máquina.
        """
        try:
            # --- 1. Buscar la máquina ---
            machine = None
            if machine_id.isdigit():
                # Intenta buscar por ID primero, que es lo más eficiente.
                machine = await self.db.get_machine_by_id(machine_id)

            # Si no se encuentra por ID, intenta buscar por nombre o seudónimo.
            if not machine:
                machine = await self.db.get_machine_by_name_or_pseudonim(machine_id)

            # Caso: La máquina no existe
            if not machine:
                return CommandResponse(
                    success=False, 
                    message=f"Máquina '{machine_id}' no encontrada.", 
                    action_executed="query_machine_status", 
                    data=None
                )

            # --- 2. Validar la entrada y el estado actual --
            if units_to_disable <= 0:
                return CommandResponse(
                    success=False,
                    message=f"El número de unidades a deshabilitar debe ser mayor a 0.",
                    action_executed="disable_machine_units",
                    data=None
                )

            if machine.functional_inks == 0:
                return CommandResponse(
                    success=True, 
                    message=f"La máquina '{machine.name}' ya tiene todas sus unidades deshabilitadas.",
                    action_executed="disable_machine_units",
                    data=None
                )

            # Comprueba si se intentan deshabilitar más unidades de las que están funcionando.
            if units_to_disable > machine.functional_inks:
                return CommandResponse(
                    success=False,
                    message=(f"No se pueden deshabilitar {units_to_disable} unidades. "
                                f"La máquina '{machine.name}' solo tiene {machine.functional_inks} funcionales en este momento."),
                    action_executed="disable_machine_units",
                    data=None
                )

            # --- 3. Calcular y ejecutar la actualización ---
            new_functional_inks = machine.functional_inks - units_to_disable
            
            success = await self.db.update_machine_status(
                machine_id=machine.id,
                functional_inks=new_functional_inks
            )
            
            if success:
                message = (f"Se deshabilitaron {units_to_disable} unidades en '{machine.name}'. "
                            f"Ahora tiene {new_functional_inks}/{machine.inks} unidades funcionales.")
                return CommandResponse(
                    success=True, 
                    message=message, 
                    action_executed="disable_machine_units",
                    data=None
                )
            else:
                return CommandResponse(
                    success=False, 
                    message=f"No se pudieron actualizar las unidades de la máquina '{machine.name}'.",
                    action_executed="disable_machine_units",
                    data=None
                )

        except Exception as e:
            return CommandResponse(
                success=False, 
                message=f"Error inesperado al deshabilitar unidades: {e}", 
                action_executed="disable_machine_units",
                data=None
            )

    async def enable_machine_units(self, machine_id: str, units_to_enable: Optional[int] = None) -> CommandResponse:
        """
        Restaura unidades de tinta funcionales en una máquina.
        - Si 'units_to_enable' es None, restaura todas las unidades.
        - Si se especifica un número, restaura esa cantidad de unidades.
        """
        try:
            # --- 1. Búsqueda robusta de la máquina ---
            machine = None
            if machine_id.isdigit():
                machine = await self.db.get_machine_by_id(int(machine_id))

            if not machine:
                machine = await self.db.get_machine_by_name_or_pseudonim(machine_id)

            if not machine:
                return CommandResponse(
                    success=False, 
                    message=f"Máquina '{machine_id}' no encontrada.",
                    action_executed="enable_machine_units",
                    data=None
                )

            # --- 2. Validación del estado actual ---
            if machine.functional_inks == machine.inks:
                return CommandResponse(
                    success=True,
                    message=f"La máquina '{machine.name}' ya tiene todas sus {machine.inks} tintas funcionales.",
                    action_executed="enable_machine_units",
                    data=None
                )

            # --- 3. Lógica de cálculo mejorada ---
            currently_disabled = machine.inks - machine.functional_inks

            if units_to_enable is None or units_to_enable <= 0:
                # Caso por defecto: restaurar todas las unidades deshabilitadas.
                units_to_restore = currently_disabled
            else:
                # Caso específico: restaurar un número, pero sin exceder el total de deshabilitadas.
                units_to_restore = min(units_to_enable, currently_disabled)

            # Calcula el nuevo número total de tintas funcionales.
            new_functional_inks = machine.functional_inks + units_to_restore

            # --- 4. Llamada a la capa de datos ---
            success = await self.db.update_machine_status(
                machine_id=machine.id,
                functional_inks=new_functional_inks
            )

            if success:
                message = (f"Se restauraron {units_to_restore} tintas en '{machine.name}'. "
                            f"Ahora tiene {new_functional_inks}/{machine.inks} tintas funcionales.")
                return CommandResponse(
                    success=True, 
                    message=message, 
                    action_executed="enable_machine_units",
                    data=None
                )
            else:
                return CommandResponse(
                    success=False, 
                    message=f"No se pudieron restaurar las tintas de la máquina '{machine.name}'.",
                    action_executed="enable_machine_units",
                    data=None
                )

        except Exception as e:
            return CommandResponse(
                success=False, 
                message=f"Error inesperado al habilitar unidades: {e}", 
                action_executed="enable_machine_units",
                data=None
            )

    async def query_order_status(self, pedido_id: int) -> CommandResponse:
        """
        Consulta el estado detallado de una orden llamando a un único método de la DAL.
        """
        try:
            # --- 1. Llamar al método que lo hace todo ---
            status_data = await self.db.get_full_order_status_details(pedido_id)
            
            if not status_data:
                return CommandResponse(
                    success=False, 
                    message=f"El pedido con ID '{pedido_id}' no fue encontrado.",
                    action_executed="query_order_status",
                    data=None
                )

            # --- 2. Construir el mensaje para el usuario ---
            if status_data.esta_en_cola:
                message = (f"La orden {pedido_id} ('{status_data.producto_nombre}') está en la cola de la máquina {status_data.maquina_asignada_id}, "
                            f"en la posición {status_data.posicion_en_cola}. "
                            f"Lleva un progreso del {status_data.porcentaje_progreso}% "
                            f"({status_data.kilos_impresos:.2f} de {status_data.kilos_requeridos:.2f} kg). "
                            f"Fecha de entrega probable: {status_data.fecha_probable_entrega.strftime('%Y-%m-%d') if status_data.fecha_probable_entrega else 'No calculada'}.")
            else:
                message = (f"La orden {pedido_id} ('{status_data.producto_nombre}') NO está en la cola de producción. "
                            f"Su progreso es del {status_data.porcentaje_progreso}%.")

            return CommandResponse(
                success=True,
                message=message,
                action_executed="query_order_status",
                data=status_data
            )
        
        except Exception as e:
            logger.error(f"Error al consultar el estado de la orden {pedido_id}: {e}", exc_info=True)
            return CommandResponse(
                success=False, 
                message=f"Error inesperado al consultar la orden: {e}",
                action_executed="query_order_status",
                data=None
            )

    async def register_roll_weight(self, machine_id: str, weight_kg: float) -> CommandResponse: # Por definir como funcionará en producción
        """
        Registra el peso de un rollo, asociándolo a la orden actual de la máquina.
        """
        try:
            machine = await self.db.get_machine_by_id(machine_id)
            if not machine:
                return CommandResponse(
                    success=False, 
                    message=f"Máquina '{machine_id}' no encontrada.", 
                    action_executed="register_roll_weight", 
                    data=None
                )
            
            # Inferimos la orden del trabajo actual de la máquina.
            if not machine.current_order_id:
                return CommandResponse(
                    success=False, 
                    message=f"La máquina '{machine_id}' no tiene una orden activa para registrar el peso.", 
                    action_executed="register_roll_weight", 
                    data=None
                )

            success = await self.db.register_roll_weight(machine_id, machine.current_order_id, weight_kg)
            
            if success:
                message = f"Registrado rollo de {weight_kg}kg para la orden {machine.current_order_id} en la máquina {machine_id}."
                return CommandResponse(
                    success=True, 
                    message=message, 
                    action_executed="register_roll_weight", 
                    data=None
                )
            else:
                return CommandResponse(
                    success=False, 
                    message="Error al guardar el registro del peso.", 
                    action_executed="register_roll_weight", 
                    data=None
                )

        except Exception as e:
            return CommandResponse(
                success=False, 
                message=f"Error inesperado al registrar peso: {e}", 
                action_executed="register_roll_weight", 
                data=None
            )