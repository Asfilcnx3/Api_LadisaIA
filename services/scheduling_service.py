import logging
from datetime import datetime
from typing import List, Tuple, Dict, Union
from collections import defaultdict

from DataAbstractionLayer.base import BaseDatabase
from schemas.db_models import SchedulableOrderModel
from schemas.api_models import CommandResponse
from core.optimizer import AlgoritmoGeneticoFlexo, GestorPrioridades, OptimizadorTotal
from core.calculators import DateCalculator, PlannerConfig

logger = logging.getLogger(__name__)

# Se define el orden de prioridad en una constante para facilitar su mantenimiento.
URGENCY_ORDER = ['CRITICA_ATRASADA', 'ATRASADA', 'URGENTE', 'PROXIMA', 'NORMAL']

class SchedulingService:
    def __init__(self, db: BaseDatabase):
        self.db = db

    async def generate_optimal_schedule(self, maquina_identifier: str) -> CommandResponse:
        """
        Genera y guarda una nueva planificación optimizada para una máquina,
        utilizando un algoritmo genético para los grupos de urgencia.
        """
        try:
            # --- 1. Cargar Datos ---
            machine_info = None
            maquina_identifier = maquina_identifier.strip() # limpiamos

            # Intentar obtener la máquina por ID, nombre o seudónimo
            if maquina_identifier.isdigit():
                machine_info = await self.db.get_machine_by_id(int(maquina_identifier))
            else:
                machine_info = await self.db.get_machine_by_name_or_pseudonim(maquina_identifier)

            # Si aún no se encuentra, devolver error
            if not machine_info:
                return CommandResponse(
                    success=False, 
                    message=f"Máquina con ID '{maquina_identifier}' no encontrada.",
                    action_executed="generate_optimal_schedule",
                    data=None
                )
            
            # Si la máquina no está activa, devolver error
            if machine_info and machine_info.estatus != 'activa':
                return CommandResponse(
                    success=False,
                    message=f"La máquina '{maquina_identifier}' no está activa.",
                    action_executed="generate_optimal_schedule",
                    data=None
                )
            
            # Obtener todos los pedidos que pueden ser planificados en esta máquina
            orders = await self.db.get_schedulable_orders_for_machine(machine_info.id)

            # Si no hay pedidos, devolver mensaje informativo
            if not orders:
                return CommandResponse(
                    success=True, 
                    message=f"No hay pedidos pendientes para planificar en la máquina {machine_info.id}.",
                    action_executed="generate_optimal_schedule",
                    data=None
                )
            
            # --- 2. Separar Órdenes con Prioridad Forzosa vs Optimizables---
            ordenes_forzosas = sorted(
                [o for o in orders if o.fecha_forzosa_entrega is not None], 
                key=lambda o: o.fecha_forzosa_entrega
            )
            ordenes_optimizables = [o for o in orders if o.fecha_forzosa_entrega is None]
            
            logger.info(f"Se han apartado {len(ordenes_forzosas)} órdenes con fecha forzosa. Optimizando las {len(ordenes_optimizables)} restantes.")

            # --- 3. Optimización Global (Capa 2) ---
            secuencia_optimizada_ids = []
            if ordenes_optimizables:
                # 3.1 -> Sin clasificar ya que son 1 o menos ordenes
                if len(ordenes_optimizables) <= 1:
                    logger.info("Añadiendo 1 o 0 órdenes optimizables sin AG.")
                    secuencia_optimizada_ids = [o.id for o in ordenes_optimizables]
                # 3.2 -> Clasificar con AG si son 2 o más órdenes
                else:
                    ag = AlgoritmoGeneticoFlexo(ordenes_optimizables, machine_info)
                    secuencia_optimizada_ids = ag.optimizar(poblacion_size=100, generaciones=200)

                    logger.info("=== DEBUG: Secuencia optimizada de órdenes (IDs) PRIMERAS 10 ORDENES ===")
                    for oid in secuencia_optimizada_ids[:10]:
                        orden = next((o for o in ordenes_optimizables if o.id == oid), None)
                        if orden:
                            logger.info(f"Orden {orden.id}: metros={orden.total_metros_impresion}, "
                                    f"colores={orden.colores}, "
                                    f"num_colores={orden.num_colores}, "
                                    f"materiales={orden.materiales}, "
                                    f"etiquetas={orden.num_etiquetas}, "
                                    f"cantidad={orden.cantidad}")

            # --- 4. Construir la Secuencia Final y Calcular Fechas ---
            secuencia_final_con_razon: List[Tuple[int, str]] = []
            # 4.1 -> Añadir las órdenes con fecha forzosa al inicio
            razon_forzosa = "Prioridad absoluta por fecha forzosa."
            secuencia_final_con_razon.extend([(o.id, razon_forzosa) for o in ordenes_forzosas])
            
            # 4.2 -> Añadir las órdenes optimizables clasificadas para optimizador genético
            razon_optimizada = "Posición calculada por optimizador genético."
            secuencia_final_con_razon.extend([(oid, razon_optimizada) for oid in secuencia_optimizada_ids])

            orders_dict = {o.id: o for o in orders}
            secuencia_ordenada_obj = [orders_dict[oid] for oid, razon in secuencia_final_con_razon]

            # Configuración del planificador
            planner_config = PlannerConfig(
                turnos_dia_semana=2, # Se trabajan 2 turnos
                horas_por_turno_semana=12, # Cada turno dura 12 horas
                dias_laborales=list(range(7)), # Lunes a Domingo
                hora_inicio_turno1=8, # Los turnos empiezan a las 8am
                turnos_sabado=2, # Se trabajan 2 turnos los sábados
                horas_por_turno_sabado=12, # Cada turno del sábado dura 12 horas
                eficiencia_maquina=0.95 # Ejemplo: esta máquina está al 95% de eficiencia
            )
            logger.info("=== DEBUG: Primeras 2 órdenes ===")
            for orden in secuencia_ordenada_obj[:2]:
                logger.info(f"Orden {orden.id}: metros={orden.total_metros_impresion}, "
                        f"etiquetas={orden.num_etiquetas}, "
                        f"cantidad={orden.cantidad}")
            
            # 4.3 -> Instanciar y usar el calculador
            calculator = DateCalculator(config=planner_config)

            # Llamar a nuestro nuevo módulo de cálculo
            fecha_inicio_planificacion = datetime.now() # O una fecha configurable
            ordenes_con_fechas = calculator.calcular_fechas_probables(secuencia_ordenada_obj, fecha_inicio_planificacion, machine_info)

            # --- 5. Guardar la Nueva Planificación (con nombres corregidos) ---
            new_schedule_for_db = []
            for i, orden_calculada in enumerate(ordenes_con_fechas, start=1):
                
                # Usar las claves que coinciden con el modelo ORM
                new_schedule_for_db.append({
                    "order_id": orden_calculada["id"],
                    "machine_id": machine_info.id,
                    "order_production": i, 
                    "reason": next((r for pid, r in secuencia_final_con_razon if pid == orden_calculada['id']), "N/A"),
                    "probable_delivery_date": orden_calculada["probable_fecha_entrega"],
                    
                    # Agregar tiempos desglosados
                    "tiempo_setup_min": orden_calculada["tiempo_setup_min"],
                    "tiempo_cambios_internos_min": orden_calculada["tiempo_cambios_internos_min"],
                    "tiempo_impresion_min": orden_calculada["tiempo_impresion_min"],
                    "tiempo_buffer_min": orden_calculada["tiempo_buffer_min"],
                    "tiempo_total_min": orden_calculada["tiempo_total_min"]
                })
            
            success = await self.db.overwrite_machine_schedule(machine_info.id, new_schedule_for_db)
            
            if success:
                logger.info("Se ha generado una nueva planificación optimizada.")
                message = f"Se ha generado una nueva planificación globalmente optimizada para la máquina {machine_info.id}."
                return CommandResponse(
                    success=True, 
                    message=message,
                    action_executed="generate_optimal_schedule",
                    data=None
                )
            
            return CommandResponse(
                success=False,
                message="Error al guardar la nueva planificación en la base de datos.",
                action_executed="generate_optimal_schedule",
                data=None
                )

        except Exception as e:
            logger.error(f"Error crítico durante la generación de la planificación: {e}", exc_info=True)
            return CommandResponse(
                success=False, 
                message=f"Error inesperado al generar la planificación: {e}",
                    action_executed="generate_optimal_schedule",
                    data=None
            )
        
    async def generate_optimal_schedule_all_machines(self, reoptimize: bool = False) -> CommandResponse:
        """
        Genera y guarda una nueva planificación optimizada para todas las máquinas,
        considerando la posibilidad de reasignar órdenes entre máquinas que comparten rodillos.
        """
        if reoptimize == False:
            return CommandResponse(
                success=False, 
                message="La reoptimización global no está implementada. Usa 'reoptimize=True' para planificar todas las máquinas.",
                action_executed="generate_optimal_schedule_all_machines",
                data=None
            )

        try:
            # --- 1. Cargar todas las máquinas activas ---
            # Filtrar solo las máquinas activas
            all_machines = await self.db.get_all_machine_status()
            active_machines = [m for m in all_machines if m.estatus == 'activa']

            if not active_machines:
                return CommandResponse(
                    success=False, 
                    message="No hay máquinas activas para planificar.",
                    action_executed="generate_optimal_schedule_all_machines",
                    data=None
                )

            logger.info(f"Iniciando optimización global para {len(active_machines)} máquinas activas.")

            # --- 2. Obtener todas las órdenes planificables ---
            all_schedulable_orders = await self.db.get_schedulable_orders_for_all_machines()

            if not all_schedulable_orders:
                return CommandResponse(
                    success=True, 
                    message="No hay órdenes pendientes para planificar en ninguna máquina.",
                    action_executed="generate_optimal_schedule_all_machines",
                    data=None
                )

            logger.info(f"Se encontraron {len(all_schedulable_orders)} órdenes planificables en total.")

            # --- 3. Construir el grafo de compatibilidad entre máquinas ---
            ot = OptimizadorTotal()
            machine_graph = ot._build_machine_compatibility_graph(active_machines)

            # --- 4. Agrupar órdenes por máquina actual ---
            orders_by_machine: Dict[int, List[SchedulableOrderModel]] = defaultdict(list)
            for order in all_schedulable_orders:
                try:
                    machine_id = int(order.maquina_id)  # Campo que viene de la query
                    orders_by_machine[machine_id].append(order)
                except (ValueError, TypeError):
                    logger.warning(f"La orden {order.id} tiene un ID de máquina inválido ('{order.maquina_id}') y será ignorada.")

            logger.info(f"Órdenes distribuidas en {len(orders_by_machine)} máquinas.")

            # --- 5. FASE 1: Reasignación inteligente de órdenes ---
            reasignaciones = ot._reasignar_ordenes_inteligente(
                orders_by_machine, 
                active_machines, 
                machine_graph
            )

            if reasignaciones:
                logger.info(f"Aplicando {len(reasignaciones)} reasignaciones...")

                # Aplicar reasignaciones de manera eficiente
                reasignaciones_por_origen = {}
                for orden_id, nueva_maquina_id, razon in reasignaciones:
                    # Encontrar la máquina origen
                    origen = None
                    for maq_id, ordenes in orders_by_machine.items():
                        if any(o.id == orden_id for o in ordenes):
                            origen = maq_id
                            break
                        
                    if origen:
                        if origen not in reasignaciones_por_origen:
                            reasignaciones_por_origen[origen] = []
                        reasignaciones_por_origen[origen].append((orden_id, nueva_maquina_id, razon))

                # Aplicar reasignaciones agrupadas por máquina origen
                for origen_id, movimientos in reasignaciones_por_origen.items():
                    ordenes_origen = orders_by_machine[origen_id]
                    ordenes_a_mover = []

                    for orden_id, destino_id, razon in movimientos:
                        orden = next((o for o in ordenes_origen if o.id == orden_id), None)
                        if orden:
                            ordenes_a_mover.append((orden, destino_id, razon))

                    # Remover todas las órdenes a mover de origen
                    for orden, _, _ in ordenes_a_mover:
                        ordenes_origen.remove(orden)

                    # Agregar a destinos
                    for orden, destino_id, razon in ordenes_a_mover:
                        if destino_id not in orders_by_machine:
                            orders_by_machine[destino_id] = []
                        orders_by_machine[destino_id].append(orden)
                        logger.info(f"Orden {orden.id}: {origen_id} → {destino_id} ({razon})")

                logger.info(f"Reasignaciones completadas.")

            # --- 6. FASE 2: Optimizar cada máquina individualmente ---
            all_schedules = []
            machines_dict = {m.id: m for m in active_machines}

            for machine_id, ordenes in orders_by_machine.items():
                if not ordenes:
                    logger.info(f"Máquina {machine_id} no tiene órdenes asignadas.")
                    continue
                
                machine_info = machines_dict.get(machine_id)
                if not machine_info:
                    logger.warning(f"No se encontró información para máquina {machine_id}.")
                    continue
                
                # Separar órdenes forzosas vs optimizables
                ordenes_forzosas = sorted(
                    [o for o in ordenes if o.fecha_forzosa_entrega is not None], 
                    key=lambda o: o.fecha_forzosa_entrega
                )
                ordenes_optimizables = [o for o in ordenes if o.fecha_forzosa_entrega is None]

                logger.info(
                    f"Máquina {machine_id}: {len(ordenes_forzosas)} forzosas, "
                    f"{len(ordenes_optimizables)} optimizables."
                )

                # Optimizar las órdenes no forzosas
                secuencia_optimizada_ids = []
                if ordenes_optimizables:
                    if len(ordenes_optimizables) <= 1:
                        secuencia_optimizada_ids = [o.id for o in ordenes_optimizables]
                    else:
                        ag = AlgoritmoGeneticoFlexo(ordenes_optimizables, machine_info)
                        secuencia_optimizada_ids = ag.optimizar(poblacion_size=100, generaciones=200)

                # Construir secuencia final con razones
                secuencia_final_con_razon = []
                razon_forzosa = "Prioridad absoluta por fecha forzosa."
                secuencia_final_con_razon.extend([(o.id, razon_forzosa) for o in ordenes_forzosas])

                razon_optimizada = "Posición calculada por optimizador genético global."
                secuencia_final_con_razon.extend([(oid, razon_optimizada) for oid in secuencia_optimizada_ids])

                # Calcular fechas probables
                orders_dict = {o.id: o for o in ordenes}
                secuencia_ordenada_obj = [orders_dict[oid] for oid, _ in secuencia_final_con_razon]

                planner_config = PlannerConfig(
                    turnos_dia_semana=2,
                    horas_por_turno_semana=12,
                    dias_laborales=list(range(7)),
                    hora_inicio_turno1=8,
                    turnos_sabado=2,
                    horas_por_turno_sabado=12,
                    eficiencia_maquina=0.95
                )

                calculator = DateCalculator(config=planner_config)
                fecha_inicio = datetime.now()
                ordenes_con_fechas = calculator.calcular_fechas_probables(
                    secuencia_ordenada_obj, 
                    fecha_inicio, 
                    machine_info
                )

                # Preparar para guardar
                for i, orden_calculada in enumerate(ordenes_con_fechas, start=1):
                    all_schedules.append({
                        "order_id": orden_calculada["id"],
                        "machine_id": machine_id,
                        "order_production": i,
                        "reason": next((r for pid, r in secuencia_final_con_razon if pid == orden_calculada['id']), "N/A"),
                        "probable_delivery_date": orden_calculada["probable_fecha_entrega"],

                        # Tiempos desglosados
                        "tiempo_setup_min": orden_calculada["tiempo_setup_min"],
                        "tiempo_cambios_internos_min": orden_calculada["tiempo_cambios_internos_min"],
                        "tiempo_impresion_min": orden_calculada["tiempo_impresion_min"],
                        "tiempo_buffer_min": orden_calculada["tiempo_buffer_min"],
                        "tiempo_total_min": orden_calculada["tiempo_total_min"]
                    })

            # --- 7. Guardar todas las planificaciones ---
            if not all_schedules:
                return CommandResponse(
                    success=False,
                    message="No se generaron planificaciones válidas para ninguna máquina.",
                    action_executed="generate_optimal_schedule_all_machines",
                    data=None
                )

            # Guardar por máquina
            machines_updated = 0
            for machine_id_int in orders_by_machine.keys():
                machine_schedule = [s for s in all_schedules if s["machine_id"] == machine_id_int]
                if machine_schedule:
                    success = await self.db.overwrite_machine_schedule(machine_id_int, machine_schedule)
                    if success:
                        machines_updated += 1

            message = (
                f"Optimización global completada: {machines_updated} máquinas actualizadas, "
                f"{len(all_schedules)} órdenes planificadas"
            )
            if reasignaciones:
                message += f", {len(reasignaciones)} órdenes reasignadas entre máquinas."

            logger.info(message)
            return CommandResponse(
                success=True,
                message=message,
                action_executed="generate_optimal_schedule_all_machines",
                data={
                    "machines_updated": machines_updated,
                    "total_orders": len(all_schedules),
                    "reassignments": len(reasignaciones) if reasignaciones else 0
                }
            )

        except Exception as e:
            logger.error(f"Error crítico durante la optimización global: {e}", exc_info=True)
            return CommandResponse(
                success=False, 
                message=f"Error inesperado: {e}",
                action_executed="generate_optimal_schedule_all_machines",
                data=None
            )

    async def prioritize_pedido(self, pedido_id: int, reoptimize: bool = False) -> CommandResponse:
        """
        Lógica de negocio para priorizar un pedido usando el Gestor de Prioridades.
        
        Args:
            pedido_id: ID del pedido a priorizar
            reoptimize: Si True, reoptimiza las demás órdenes después de priorizar
        
        Returns:
            CommandResponse con el resultado de la operación
        """
        try:
            # --- 1. Validar que el pedido existe en la cola ---
            item_to_prioritize = await self.db.get_queue_item_by_pedido_id(pedido_id)
            if not item_to_prioritize:
                return CommandResponse(
                    success=False, 
                    message=f"El pedido con ID '{pedido_id}' no se encuentra en la cola de producción.",
                    action_executed="prioritize_pedido",
                    data=None
                )

            # --- 2. Caso especial: Ya es el primero ---
            if item_to_prioritize.order_production == 1:
                return CommandResponse(
                    success=True, 
                    message=f"El pedido {pedido_id} ya es la máxima prioridad.",
                    action_executed="prioritize_pedido",
                    data=None
                    )

            # --- 3. Obtener información de la máquina ---
            maquina_id = item_to_prioritize.machine_id
            machine_info = await self.db.get_machine_by_id(maquina_id)
            if not machine_info:
                return CommandResponse(
                    success=False, 
                    message=f"No se encontró la máquina {maquina_id} asociada al pedido.",
                    action_executed="prioritize_pedido",
                    data=None
                )
            
            # --- 3.1 Validar que la máquina está activa ---
            if machine_info.estatus != 'activa':
                return CommandResponse(
                    success=False,
                    message=f"La máquina {maquina_id} no está activa.",
                    action_executed="prioritize_pedido",
                    data=None
                )

            # --- 4. Obtener la cola actual y las órdenes planificables ---
            current_queue_items = await self.db.get_production_queue_for_machine(maquina_id)
            schedulable_orders = await self.db.get_schedulable_orders_for_machine(maquina_id)
        
            # --- 5. VALIDACIÓN CRÍTICA: Verificar que el pedido a priorizar es planificable ---
            # Esto es importante para el futuro cuando las órdenes puedan cambiar de máquina
            if not any(order.id == pedido_id for order in schedulable_orders):
                logger.warning(
                    f"El pedido {pedido_id} está en la cola de la máquina {maquina_id} "
                    f"pero ya no es planificable en ella (posiblemente cambió de máquina al reordenar)."
                )
                return CommandResponse(
                    success=False,
                    message=f"El pedido {pedido_id} ya no puede ser planificado en la máquina {maquina_id}.",
                    action_executed="prioritize_pedido",
                    data=None
                )

            # Convertir a diccionarios para acceso rápido
            orders_dict = {order.id: order for order in schedulable_orders}
            current_sequence_ids = [item.order_id for item in current_queue_items]

            logger.info(
                f"Priorizando pedido {pedido_id} en máquina {maquina_id}. "
                f"Reoptimizar: {reoptimize}. Cola actual: {len(current_sequence_ids)} órdenes."
            )

            # --- 6. Instanciar y usar el Gestor de Prioridades ---
            gestor = GestorPrioridades(current_sequence_ids, orders_dict, machine_info)

            if reoptimize:
                gestor.priorizar_con_reoptimizacion(pedido_id)
                action_desc = "priorizado con reoptimización del resto de la cola"
            else:
                gestor.priorizar_sin_reprogramar(pedido_id)
                action_desc = "movido a la posición 1 (sin reoptimizar)"

            new_sequence = gestor.secuencia

            # --- 7. VALIDACIÓN: Verificar que la nueva secuencia es consistente ---
            if pedido_id not in new_sequence:
                logger.error(f"ERROR CRÍTICO: El pedido {pedido_id} no está en la nueva secuencia.")
                return CommandResponse(
                    success=False,
                    message="Error interno: la priorización falló de manera inesperada.",
                    action_executed="prioritize_pedido",
                    data=None
                )

            if new_sequence[0] != pedido_id:
                logger.error(
                    f"ERROR CRÍTICO: El pedido {pedido_id} debería estar primero "
                    f"pero está en posición {new_sequence.index(pedido_id) + 1}."
                )

            # --- 8. Preparar actualizaciones para la base de datos ---
            updates_for_db = []
            ordenes_sin_registro = []

            for i, p_id in enumerate(new_sequence, start=1):
                # Buscar el registro en la cola que corresponde a este pedido
                queue_item = next((item for item in current_queue_items if item.order_id == p_id), None)

                if queue_item:
                    updates_for_db.append({
                        'id': queue_item.id,
                        'order_production': i
                    })
                else:
                    # NOTA FUTURA: Esto podría suceder cuando las órdenes cambien de máquina
                    ordenes_sin_registro.append(p_id)

            if ordenes_sin_registro:
                logger.warning(
                    f"Se encontraron {len(ordenes_sin_registro)} órdenes en la nueva secuencia "
                    f"que no tienen registro en la cola actual: {ordenes_sin_registro[:5]}..."
                )

            # --- 9. Guardar los cambios en la base de datos ---
            if not updates_for_db:
                return CommandResponse(
                    success=False,
                    message="No se generaron actualizaciones válidas para la cola.",
                    action_executed="prioritize_pedido",
                    data=None
                )

            success = await self.db.update_production_queue(updates_for_db)

            if success:
                message = (
                    f"Pedido {pedido_id} {action_desc} en la máquina {maquina_id}. "
                    f"Se actualizaron {len(updates_for_db)} registros."
                )
                logger.info(message)
                return CommandResponse(
                    success=True, 
                    message=message, 
                    action_executed="prioritize_pedido",
                    data={
                        "pedido_id": pedido_id,
                        "maquina_id": maquina_id,
                        "nueva_posicion": 1,
                        "ordenes_reordenadas": len(updates_for_db),
                        "reoptimizado": reoptimize
                    }
                )
            else:
                return CommandResponse(
                    success=False,
                    message="Error al actualizar la cola de producción en la base de datos.",
                    action_executed="prioritize_pedido",
                    data=None
                )

        except Exception as e:
            logger.error(f"Error inesperado al priorizar el pedido {pedido_id}: {e}", exc_info=True)
            return CommandResponse(
                success=False, 
                message=f"Error inesperado: {str(e)}",
                action_executed="prioritize_pedido",
                data=None
            )

    async def recalculate_delivery_dates(self, maquina_identifier: Union[int, str]) -> CommandResponse:
        """
        Recalcula las fechas probables de entrega para una máquina después de 
        reordenamientos manuales (drag & drop) en el frontend.

        Este servicio:
        1. Obtiene la secuencia actual de la cola (ya reordenada manualmente)
        2. Calcula los tiempos y fechas probables para esa secuencia
        3. Actualiza SOLO los tiempos y fechas, sin modificar el orden

        Args:
            maquina_identifier: ID de la máquina cuya cola se recalculará

        Returns:
            CommandResponse con el resultado de la operación
        """
        try:
            # --- 1. Validar que la máquina existe ---
            machine_info = None
            if isinstance(maquina_identifier, int) or maquina_identifier.isdigit():
                machine_info = await self.db.get_machine_by_id(int(maquina_identifier))
            else:
                machine_info = await self.db.get_machine_by_name_or_pseudonim(maquina_identifier)

            if not machine_info:
                return CommandResponse(
                    success=False,
                    message=f"Máquina con ID {maquina_identifier} no encontrada.",
                    action_executed="recalculate_delivery_dates",
                    data=None
                )

            # --- 2. Obtener la cola actual ya enriquecida (UNA SOLA LLAMADA A LA DB) ---
            ordenes_secuenciadas = await self.db.get_schedulable_orders_by_ids(machine_info.id)
        
            if not ordenes_secuenciadas:
                return CommandResponse(
                    success=True, 
                    message=f"La máquina {machine_info.id} no tiene órdenes en cola para recalcular.",
                    action_executed="recalculate_delivery_dates",
                    data=None
                )

            logger.info(f"Recalculando fechas para {len(ordenes_secuenciadas)} órdenes en máquina {machine_info.id}...")

            # --- 3. Calcular fechas probables ---
            planner_config = PlannerConfig(
                turnos_dia_semana=2, # Se trabajan 2 turnos
                horas_por_turno_semana=12, # Cada turno dura 12 horas
                dias_laborales=list(range(7)), # Lunes a Domingo
                hora_inicio_turno1=8, # Los turnos empiezan a las 8am
                turnos_sabado=2, # Se trabajan 2 turnos los sábados
                horas_por_turno_sabado=12, # Cada turno del sábado dura 12 horas
                eficiencia_maquina=0.95 # Ejemplo: esta máquina está al 95% de eficiencia
            )
            calculator = DateCalculator(config=planner_config)
            fecha_inicio = datetime.now()
            ordenes_con_fechas = calculator.calcular_fechas_probables(ordenes_secuenciadas, fecha_inicio, machine_info)

            # Log debug
            logger.info(f"=== DEBUG: Órdenes calculadas: {len(ordenes_con_fechas)} ===")
            if ordenes_con_fechas:
                primer_orden = ordenes_con_fechas[0]
                logger.info(f"Primera orden keys: {list(primer_orden.keys())}")
                logger.info(f"Primera orden tiene 'id_en_cola': {'id_en_cola' in primer_orden}")
                logger.info(f"Valor de 'id_en_cola': {primer_orden.get('id_en_cola')}")

            # --- 4. Preparar y ejecutar la actualización en bloque ---
            updates_for_db = []
            for orden_calculada in ordenes_con_fechas:
                logger.info(f"Procesando orden {orden_calculada.get('id')}: id_en_cola={orden_calculada.get('id_en_cola')}")

                # Ahora 'orden_calculada' contiene 'id_en_cola' que viene de la query
                if "id_en_cola" in orden_calculada and orden_calculada["id_en_cola"] is not None:
                    updates_for_db.append({
                        'id': orden_calculada["id_en_cola"], # <-- Se usa el ID correcto
                        'probable_delivery_date': orden_calculada["probable_fecha_entrega"],
                        'tiempo_setup_min': orden_calculada.get("tiempo_setup_min"),
                        'tiempo_cambios_internos_min': orden_calculada.get("tiempo_cambios_internos_min"),
                        'tiempo_impresion_min': orden_calculada.get("tiempo_impresion_min"),
                        'tiempo_buffer_min': orden_calculada.get("tiempo_buffer_min"),
                        'tiempo_total_min': orden_calculada.get("tiempo_total_min"),
                    })
                else:
                    logger.warning(f"Orden {orden_calculada.get('id')} no tiene id_en_cola válido")
            
            logger.info(f"Total de actualizaciones preparadas: {len(updates_for_db)}")

            if not updates_for_db:
                return CommandResponse(
                    success=False, 
                    message="No se generaron actualizaciones válidas.",
                    action_executed="recalculate_delivery_dates",
                    data=None
                )

            success = await self.db.update_queue_dates_and_times(updates_for_db)
            if success:
                message = (
                    f"Fechas recalculadas para {len(updates_for_db)} órdenes "
                    f"en máquina {machine_info.id}."
                )
                logger.info(message)

                return CommandResponse(
                    success=True,
                    message=message,
                    action_executed="recalculate_delivery_dates",
                    data={
                        "machine_id": machine_info.id,
                        "orders_updated": len(updates_for_db),
                        "primera_entrega": ordenes_con_fechas[0]["probable_fecha_entrega"].isoformat() if ordenes_con_fechas else None,
                        "ultima_entrega": ordenes_con_fechas[-1]["probable_fecha_entrega"].isoformat() if ordenes_con_fechas else None
                    }
                )
            else:
                return CommandResponse(
                    success=False,
                    message="Error al actualizar las fechas en la base de datos.",
                    action_executed="recalculate_delivery_dates",
                    data=None
                )

        except Exception as e:
            logger.error(f"Error al recalcular fechas para máquina {machine_info.id}: {e}", exc_info=True)
            return CommandResponse(
                success=False,
                message=f"Error inesperado: {str(e)}",
                action_executed="recalculate_delivery_dates",
                data=None
            )