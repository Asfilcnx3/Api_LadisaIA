import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import select, update, or_, text, delete, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from DataAbstractionLayer.base import BaseDatabase

from schemas.api_models import OrderStatusResponse

from schemas.orm_models import (
    Machine as MachineORM, RazonMermas as RazonMermasORM, Mermas as MermasORM,
    Pedidos as PedidoORM, OrdenPedido as OrdenPedidoORM, Etiqueta as EtiquetaORM,
    Productos as ProductosORM, SubEtiqueta1 as SubEtiqueta1ORM
)# Importamos los modelos ORM

from schemas.db_models import (
    MachineModel, MermaModel, MermaReasonModel, PedidoModel, OrderModelforOrder, SchedulableOrderModel, SchedulableAllMachineModel, SchedulableOrdersFromMachine
) # Importamos los modelos Pydantic


logger = logging.getLogger(__name__)

class MySQLDB(BaseDatabase):
    """Implementación de la DAL para una base de datos MySQL."""
    
    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url)
        self.async_session = sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        logger.info("Implementación de DAL para MySQL inicializada.")

    async def check_connection(self) -> bool:
        """Verifica la conectividad con la base de datos ejecutando una consulta simple."""
        try:
            async with self.engine.connect() as connection:
                await connection.execute(select(1))
            return True
        except Exception as e:
            logger.error(f"Fallo en la conexión con la base de datos: {e}")
            raise

    async def get_all_machine_status(self) -> List[MachineModel]: # lista para trabajar
        async with self.async_session() as session:
            stmt = select(MachineORM)
            result = await session.execute(stmt)
            machines_orm = result.scalars().all()
            
            machines = [MachineModel.model_validate(machine) for machine in machines_orm]
            return machines

    async def get_machine_by_id(self, machine_id: str) -> Optional[MachineModel]: # lista para trabajar
        async with self.async_session() as session:
            stmt = select(MachineORM).where(MachineORM.id == machine_id)
            result = await session.execute(stmt)
            machine_orm = result.scalar_one_or_none()
            
            if machine_orm:
                # Convierte el modelo ORM de SQLAlchemy a nuestro modelo Pydantic
                return MachineModel.model_validate(machine_orm)
            return None
        
    async def get_machine_by_name_or_pseudonim(self, name: str) -> Optional[MachineModel]: # lista para trabajar
        async with self.async_session() as session:
            # La clausula or_() permite buscar por nombre o seudónimo
            stmt = select(MachineORM).where(
                or_(MachineORM.name == name, MachineORM.pseudonym == name)
            )
            result = await session.execute(stmt)
            machine_orm = result.scalar_one_or_none()
            
            if machine_orm:
                # Convierte el modelo ORM de SQLAlchemy a nuestro modelo Pydantic
                return MachineModel.model_validate(machine_orm)
            return None
    
    async def update_machine_status(self, machine_id: str, status: Optional[str] = None, functional_inks: Optional[int] = None) -> bool: # lista para trabajar
        """
        Actualiza el estado y/o tintas funcionales de una máquina.
        Esta función es flexible y solo actualiza los campos que se le proporcionan.
        """
        # --- 1. Validar que al menos un campo se va a actualizar ---
        if status is None and functional_inks is None:
            # No hay nada que hacer, pero la operación no falló.
            return True

        async with self.async_session() as session:
            # --- 2. Construir el diccionario de valores a actualizar ---
            values_to_update = {}
            if status is not None:
                values_to_update["estatus"] = status
            if functional_inks is not None:
                values_to_update["functional_inks"] = functional_inks

            # --- 3. Ejecutar la actualización y hacer commit ---
            update_stmt = (
                update(MachineORM)
                .where(MachineORM.id == machine_id)
                .values(**values_to_update)
            )
            result = await session.execute(update_stmt)
            await session.commit()

            # rowcount > 0 significa que al menos una fila fue afectada.
            return result.rowcount > 0
        
    async def register_waste_record(self, order_id: int, process: str, reason_id: int, quantity: float, observations: str, user_id: int) -> MermaModel: # lista para trabajar
        """
        Crea/registra las mermas en la tabla "registro_mermas" usando las razones dentro de "razon_mermas" apoyandose de la función de busqueda
        """
        async with self.async_session() as session:
            new_record_orm = MermasORM(
                order_id=order_id,
                process=process,
                reason_id=reason_id,
                quantity=quantity,
                observations=observations,
                user_id=user_id # En un sistema real, este ID vendría del usuario autenticado
            )
            session.add(new_record_orm)
            await session.commit()
            await session.refresh(new_record_orm)
            return MermaModel.model_validate(new_record_orm)

    async def get_waste_reason_by_name(self, name: str) -> Optional[MermaReasonModel]: # lista para trabajar
        """
        Busca una razón de merma por su nombre, asegurándose de que esté activa.
        """
        async with self.async_session() as session:
            stmt = select(RazonMermasORM).where(
                RazonMermasORM.name.ilike(f"%{name}%"), # Busca una coincidencia parcial e insensible a mayúsculas
                RazonMermasORM.active == True # SQLAlchemy traduce esto a 'activo = 1' en la DB
            )
            result = await session.execute(stmt)
            reason_orm = result.scalar_one_or_none()
            if reason_orm:
                return MermaReasonModel.model_validate(reason_orm)
            return None
        
    async def get_order_by_id(self, pedido_id: int) -> Optional[PedidoModel]: # lista para trabajar
        """
        Busca el pedido dentro de la tabla "pedido" y extrae ciertos campos dentro de esta tabla, pero no todos.
        """
        async with self.async_session() as session:
            stmt = select(PedidoORM).where(PedidoORM.id == pedido_id)
            result = await session.execute(stmt)
            pedido_orm = result.scalar_one_or_none()
            if pedido_orm:
                # Pydantic mapeará los campos del ORM (id, usuario, etc.)
                # a los campos del Pydantic Model (id, user_id, etc.)
                return PedidoModel.model_validate(pedido_orm)
            return None
        
    async def get_machines_status_with_details(self, machine_id: Optional[int] = None) -> List[Dict]:
        """
        Ejecuta una consulta compleja que une máquinas, su orden actual (orden=1),
        y calcula el progreso de dicha orden.
        """
        query = text("""
            WITH
            -- Paso 1: Encontrar la primera orden en la cola para cada máquina
            FirstOrderInQueue AS (
                SELECT
                    maquina_id,
                    pedido_id,
                    orden,
                    probable_fecha_entrega
                FROM orden_impresion_i_a_s
                WHERE orden = 1
            ),
            -- Paso 2: Calcular los kilos impresos por pedido
            KilosImpresos AS (
                SELECT pedido_id, SUM(peso_neto_impresion) as kilos_impresos
                FROM sub_etiqueta_1 WHERE mostrar = 1 GROUP BY pedido_id
            ),
            -- Paso 3: Calcular los kilos totales requeridos por pedido
            KilosRequeridos AS (
                SELECT pedido_id, SUM(peso_neto) as kilos_requeridos
                FROM etiqueta WHERE etiqueta_para = 1 AND mostrar = 1 GROUP BY pedido_id
            )
            -- Consulta Final: Unir toda la información
            SELECT
                m.*,
                -- Campos de las otras tablas con alias para evitar colisiones
                p.id as pedido_id, p.status as estatus_pedido, prod.nombre as producto_nombre,
                fo.orden as posicion_en_cola, fo.probable_fecha_entrega,
                COALESCE(kr.kilos_requeridos, 0) as kilos_requeridos,
                COALESCE(ki.kilos_impresos, 0) as kilos_impresos
            FROM maquina m
            LEFT JOIN FirstOrderInQueue fo ON m.id = fo.maquina_id
            LEFT JOIN pedido p ON fo.pedido_id = p.id
            LEFT JOIN productos prod ON p.producto_id = prod.id_producto
            LEFT JOIN KilosRequeridos kr ON fo.pedido_id = kr.pedido_id
            LEFT JOIN KilosImpresos ki ON fo.pedido_id = ki.pedido_id
            WHERE
                m.estatus = 'activa'
                -- Filtro opcional para buscar una sola máquina
                AND (:machine_id IS NULL OR m.id = :machine_id);
        """)

        async with self.engine.connect() as connection:
            result = await connection.execute(query, {"machine_id": machine_id})
            return result.mappings().all()
        
    async def get_full_order_status_details(self, pedido_id: int) -> Optional[OrderStatusResponse]:
        async with self.async_session() as session:
            # --- 1. Subconsulta para Kilos Impresos ---
            # SUM(peso_neto_impresion) from sub_etiqueta_1
            kilos_impresos_subq = select(func.sum(SubEtiqueta1ORM.net_weight_impression)).where(
                SubEtiqueta1ORM.order_id == pedido_id,
                SubEtiqueta1ORM.show == 1
            ).scalar_subquery()

            # --- 2. Subconsulta para Kilos Requeridos ---
            # SUM(peso_neto) from etiqueta
            kilos_requeridos_subq = select(func.sum(EtiquetaORM.net_weight)).where(
                EtiquetaORM.order_id == pedido_id,
                EtiquetaORM.label_for == 1,
                EtiquetaORM.show == 1
            ).scalar_subquery()

            # --- 3. Consulta Principal ---
            stmt = select(
                PedidoORM.id.label("pedido_id"),
                ProductosORM.name.label("producto_nombre"),
                PedidoORM.status.label("estatus_pedido"),
                OrdenPedidoORM.machine_id.label("maquina_asignada_id"),
                OrdenPedidoORM.order_production.label("posicion_en_cola"),
                OrdenPedidoORM.probable_delivery_date.label("fecha_probable_entrega"),
                kilos_impresos_subq.label("kilos_impresos"),
                kilos_requeridos_subq.label("kilos_requeridos")
            ).select_from(PedidoORM).join(
                ProductosORM, PedidoORM.product_id == ProductosORM.id
            ).outerjoin( # Usamos outerjoin por si la orden no está en la cola
                OrdenPedidoORM, PedidoORM.id == OrdenPedidoORM.order_id
            ).where(PedidoORM.id == pedido_id)

            result = await session.execute(stmt)
            data = result.first()

            if not data:
                return None

            # --- 4. Construir el objeto de respuesta ---
            kilos_req = float(data.kilos_requeridos or 0.0)
            kilos_imp = float(data.kilos_impresos or 0.0)
            
            return OrderStatusResponse(
                pedido_id=data.pedido_id,
                producto_nombre=data.producto_nombre,
                estatus_pedido=data.estatus_pedido,
                esta_en_cola=True if data.maquina_asignada_id is not None else False,
                maquina_asignada_id=data.maquina_asignada_id,
                posicion_en_cola=data.posicion_en_cola,
                fecha_probable_entrega=data.fecha_probable_entrega,
                kilos_requeridos=kilos_req,
                kilos_impresos=kilos_imp,
                porcentaje_progreso=round((100 * kilos_imp) / kilos_req, 1) if kilos_req > 0 else 0.0
            )

    async def get_order_position_in_queue(self, pedido_id: int) -> Optional[OrderModelforOrder]:
        """Busca la orden en la tabla de planificación 'orden_impresion_i_a_s'."""
        async with self.async_session() as session:
            stmt = select(OrdenPedidoORM).where(OrdenPedidoORM.order_id == pedido_id)
            result = await session.execute(stmt)
            queue_item = result.scalar_one_or_none()
            if queue_item:
                return OrderModelforOrder.model_validate(queue_item)
            return None
        
    async def get_queue_item_by_pedido_id(self, pedido_id: int) -> Optional[OrderModelforOrder]: # por probar
        async with self.async_session() as session:
            stmt = select(OrdenPedidoORM).where(OrdenPedidoORM.order_id == pedido_id)
            result = await session.execute(stmt)
            item_orm = result.scalar_one_or_none()
            return OrderModelforOrder.model_validate(item_orm) if item_orm else None

    async def get_production_queue_for_machine(self, maquina_id: int) -> List[OrderModelforOrder]: # por probar
        async with self.async_session() as session:
            stmt = select(OrdenPedidoORM).where(OrdenPedidoORM.machine_id == maquina_id).order_by(OrdenPedidoORM.order_production)
            result = await session.execute(stmt)
            items_orm = result.scalars().all()
            return [OrderModelforOrder.model_validate(item) for item in items_orm]

    async def update_production_queue(self, updates: List[Dict[str, Any]]) -> bool: # por probar
        """Usa un bulk update para eficiencia."""
        if not updates:
            return True
        async with self.async_session() as session:
            await session.execute(update(OrdenPedidoORM), updates)
            await session.commit()
            return True

    # async def get_schedulable_orders_for_machine(self, maquina_id: int) -> List[SchedulableOrderModel]: # por probar
    #     """
    #     Obtiene la cola de producción actual y la enriquece con datos de las tablas
    #     pedido, productos y etiqueta en una sola consulta.
    #     """
    #     query = text("""
    #         SELECT 
    #             p.id, p.producto_id, p.status, p.datos, p.fecha_entrega, p.fecha_forzosa_entrega,
    #             p.prioridad_planeacion,
    #             DATEDIFF(COALESCE(p.fecha_forzosa_entrega, p.fecha_entrega), CURDATE()) as dias_restantes,
    #             prod.nombre as producto_nombre,
    #             JSON_EXTRACT(p.datos, '$.cantidad') as cantidad,
    #             JSON_EXTRACT(p.datos, '$.pantone') as colores,
    #             JSON_LENGTH(JSON_EXTRACT(p.datos, '$.pantone')) as num_colores,
    #             JSON_EXTRACT(p.datos, '$.materiales') as materiales,
    #             SUM(e.peso_neto) as total_peso_neto,
    #             SUM(e.metros_impresion) as total_metros_impresion,
    #             COUNT(DISTINCT e.numero) as num_etiquetas
    #         FROM pedido p
    #         INNER JOIN productos prod ON p.producto_id = prod.id_producto
    #         INNER JOIN tipos_de_productos tdp ON prod.id_tipo_producto = tdp.id_tipo_producto
    #         INNER JOIN etiqueta e ON e.pedido_id = p.id
    #         WHERE 
    #             p.id IN :order_ids  -- <-- CORRECCIÓN CLAVE: Filtrar por la lista de IDs
    #             AND e.etiqueta_para = 1 AND e.mostrar = 1 AND e.peso_neto > 0
    #             AND p.status <= 5
    #             AND JSON_VALID(p.datos)
    #             AND tdp.tipo_proceso NOT IN (6, 7, 9)
    #         GROUP BY p.id, prod.nombre;
    #     """)
    #     async with self.engine.connect() as connection:
    #         result = await connection.execute(query, {"maquina_id": maquina_id})
    #         orders_data = result.mappings().all()
    #         return [SchedulableOrderModel.model_validate(row) for row in orders_data]

    async def get_schedulable_orders_for_machine(self, maquina_id: int) -> List[SchedulableOrderModel]:
        """Ejecuta la consulta de planificación de todas las máquinas directamente en la base de datos."""
        query = text("""
                    SELECT
                        p.id, p.producto_id, p.status, p.datos, p.fecha_entrega, p.fecha_forzosa_entrega,
                        p.prioridad_planeacion,
                        DATEDIFF(COALESCE(p.fecha_forzosa_entrega, p.fecha_entrega), CURDATE()) as dias_restantes,
                        prod.nombre as producto_nombre,
                        JSON_EXTRACT(p.datos, '$.cantidad') as cantidad,
                        JSON_EXTRACT(p.datos, '$.pantone') as colores,
                        JSON_LENGTH(JSON_EXTRACT(p.datos, '$.pantone')) as num_colores,
                        JSON_EXTRACT(p.datos, '$.materiales') as materiales,
                        SUM(e.peso_neto) as total_peso_neto,
                        SUM(e.metros_impresion) as total_metros_impresion,
                        COUNT(DISTINCT e.numero) as num_etiquetas
                FROM pedido p
                INNER JOIN productos prod ON p.producto_id = prod.id_producto
                INNER JOIN tipos_de_productos tdp ON prod.id_tipo_producto = tdp.id_tipo_producto
                INNER JOIN etiqueta e ON e.pedido_id = p.id AND e.etiqueta_para = 1 AND e.mostrar = 1 AND e.peso_neto > 0
                WHERE p.status <= 5
                AND JSON_VALID(p.datos)
                AND JSON_UNQUOTE(JSON_EXTRACT(p.datos, '$.maquina')) = :maquina_id
                AND tdp.tipo_proceso NOT IN (6, 7, 9)
                GROUP BY
                    p.id, prod.nombre
                ORDER BY
                    CASE WHEN dias_restantes < 3 THEN 1 ELSE 2 END,
                    dias_restantes ASC, p.prioridad_planeacion ASC;
                """)
        async with self.engine.connect() as connection:
            result = await connection.execute(query, {"maquina_id": maquina_id})
            orders_data = result.mappings().all()
            return [SchedulableOrderModel.model_validate(row) for row in orders_data]
        
    async def get_schedulable_orders_for_all_machines(self) -> List[SchedulableAllMachineModel]:
        """Ejecuta la consulta de planificación de todas las máquinas directamente en la base de datos."""
        query = text("""
            SELECT 
                p.id, p.producto_id, p.status, p.datos, p.fecha_entrega, p.fecha_forzosa_entrega,
                p.prioridad_planeacion,
                DATEDIFF(COALESCE(p.fecha_forzosa_entrega, p.fecha_entrega), CURDATE()) as dias_restantes,
                prod.nombre as producto_nombre,
                JSON_EXTRACT(p.datos, '$.cantidad') as cantidad,
                JSON_EXTRACT(p.datos, '$.pantone') as colores,
                JSON_LENGTH(JSON_EXTRACT(p.datos, '$.pantone')) as num_colores,
                JSON_EXTRACT(p.datos, '$.materiales') as materiales,
                SUM(e.peso_neto) as total_peso_neto,
                SUM(e.metros_impresion) as total_metros_impresion,
                COUNT(DISTINCT e.numero) as num_etiquetas,
                -- Se usa JSON_UNQUOTE para obtener el valor limpio
                JSON_UNQUOTE(JSON_EXTRACT(p.datos, '$.maquina')) as maquina_id
            FROM pedido p
            INNER JOIN productos prod ON p.producto_id = prod.id_producto
            INNER JOIN tipos_de_productos tdp ON prod.id_tipo_producto = tdp.id_tipo_producto
            INNER JOIN etiqueta e ON e.pedido_id = p.id AND e.etiqueta_para = 1 AND e.mostrar = 1 AND e.peso_neto > 0
            WHERE p.status <= 5
                AND JSON_VALID(p.datos)
                -- NOTA: Esta lista de máquinas está hardcodeada. En el futuro, podría ser dinámica.
                AND JSON_UNQUOTE(JSON_EXTRACT(p.datos, '$.maquina')) IN ('1','2','4','9','13','14','15','16','17')
                AND tdp.tipo_proceso NOT IN (6, 7, 9)
            -- El GROUP BY debe incluir todas las columnas no agregadas del SELECT.
            GROUP BY 
                p.id, p.producto_id, p.status, p.datos, p.fecha_entrega, p.fecha_forzosa_entrega,
                p.prioridad_planeacion, prod.nombre
            ORDER BY 
                maquina_id, dias_restantes ASC;
        """)
        async with self.engine.connect() as connection:
            # Esta consulta no necesita parámetros
            result = await connection.execute(query)
            orders_data = result.mappings().all()
            return [SchedulableAllMachineModel.model_validate(row) for row in orders_data]
        
    async def get_schedulable_orders_by_ids(self, maquina_id: int) -> List[SchedulableOrdersFromMachine]:
        """
        Obtiene la cola de producción actual y la enriquece con datos de las tablas
        pedido, productos y etiqueta en una sola consulta optimizada.
        """
        query = text("""
            SELECT
                p.id, p.producto_id, p.status, p.datos, p.fecha_entrega, p.fecha_forzosa_entrega,
                p.prioridad_planeacion,
                DATEDIFF(COALESCE(p.fecha_forzosa_entrega, p.fecha_entrega), CURDATE()) as dias_restantes,
                prod.nombre as producto_nombre,
                oias.id as id_en_cola, -- ID de la fila en la tabla de planificación (CRUCIAL)
                oias.orden as order_production,
                oias.probable_fecha_entrega,
                oias.razon,
                JSON_EXTRACT(p.datos, '$.cantidad') as cantidad,
                JSON_EXTRACT(p.datos, '$.pantone') as colores,
                JSON_LENGTH(JSON_EXTRACT(p.datos, '$.pantone')) as num_colores,
                JSON_EXTRACT(p.datos, '$.materiales') as materiales,
                SUM(e.peso_neto) as total_peso_neto,
                SUM(e.metros_impresion) as total_metros_impresion,
                COUNT(DISTINCT e.numero) as num_etiquetas
            FROM orden_impresion_i_a_s oias
            INNER JOIN pedido p ON oias.pedido_id = p.id
            INNER JOIN productos prod ON p.producto_id = prod.id_producto
            LEFT JOIN etiqueta e ON oias.pedido_id = e.pedido_id AND e.etiqueta_para = 1 AND e.mostrar = 1 AND e.peso_neto > 0
            WHERE oias.maquina_id = :maquina_id
            GROUP BY oias.id, p.id, prod.nombre
            ORDER BY oias.orden ASC;
        """)
        async with self.engine.connect() as connection:
            result = await connection.execute(query, {"maquina_id": maquina_id})
            orders_data = result.mappings().all()
        return [SchedulableOrderModel.model_validate(row) for row in orders_data]

    async def overwrite_machine_schedule(self, maquina_id: int, new_schedule: List[Dict[str, Any]]) -> bool: # Funciona
        """Realiza una operación atómica de borrado e inserción para actualizar la planificación."""
        async with self.async_session() as session:
            # 1. Borrar la planificación antigua para esta máquina
            delete_stmt = delete(OrdenPedidoORM).where(OrdenPedidoORM.machine_id == maquina_id)
            await session.execute(delete_stmt)

            # 2. Insertar la nueva planificación
            if new_schedule:
                # Crea objetos ORM para la inserción en bloque
                schedule_objects = [OrdenPedidoORM(**item) for item in new_schedule]
                session.add_all(schedule_objects)

            await session.commit()
            return True

    async def update_queue_dates_and_times(self, updates: List[Dict[str, Any]]) -> bool:
        """Ejecuta un 'bulk update' en la tabla orden_impresion_i_a_s."""
        if not updates:
            return True

        async with self.async_session() as session:
            # Esta sintaxis es más explícita y segura para bulk updates.
            # Le dice a SQLAlchemy que use 'id' para el WHERE y actualice el resto.
            stmt = update(OrdenPedidoORM)
            await session.execute(stmt, updates)
            await session.commit()
            return True

    # Esta será la ultima en hacerse
    async def register_roll_weight(self, machine_id: str, order_id: str, weight_kg: float) -> bool: # por definir como funciona
        async with self.async_session() as session:
            # Verificar que la máquina y la orden existan
            machine_stmt = select(MachineORM).where(MachineORM.id == machine_id)
            order_stmt = select(OrdenPedidoORM).where(OrdenPedidoORM.id == order_id)
            
            machine_result = await session.execute(machine_stmt)
            order_result = await session.execute(order_stmt)
            
            machine_orm = machine_result.scalar_one_or_none()
            order_orm = order_result.scalar_one_or_none()
            
            if not machine_orm or not order_orm:
                return False
            
            # Aquí iría la lógica para registrar el peso del rollo.
            # Dado que no se especifica una tabla para esto, asumimos que se registra en otra parte.
            # Por ahora, simplemente retornamos True para indicar éxito.
            return True

    # ... Aquí implementarías el resto de los métodos de la interfaz BaseDatabase ...