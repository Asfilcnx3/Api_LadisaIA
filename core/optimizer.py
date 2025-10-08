import random
import json
import logging
from typing import Any, Dict, List, Set, Tuple

# --- LIBRERÍAS DEL ALGORITMO GENÉTICO ---
from deap import base, creator, tools, algorithms

# Nuestros modelos Pydantic que vienen del servicio
from schemas.db_models import SchedulableOrderModel, MachineModel, SchedulableAllMachineModel

logger = logging.getLogger(__name__)

# MEJORA: Definir constantes para los "números mágicos" hace el código más legible y fácil de ajustar.
class OptimizerConfig:
    """Configuración centralizada para los pesos y costos del algoritmo."""
    # Pesos para la función de fitness
    SETUP_COST_WEIGHT: float = 100
    DELAY_PENALTY_WEIGHT: float = 10
    INK_OVERCAPACITY_PENALTY: float = 1000.0
    
    # Costos de cambio (en minutos o unidades de costo)
    MATERIAL_CHANGE_FACTOR: float = 2.0
    MATERIAL_SAME_FACTOR: float = 0.5
    INK_CLEAN_COST: float = 5.0  # Costo bajo por quitar una tinta  
    INK_ADD_COST: float = 25.0     # Costo alto por añadir una tinta
    SAME_CLIENT_BONUS_FACTOR: float = 0.8 # Descuento del 20%

    # Prioridad para órdenes con muchas tintas
    HIGH_INK_PRIORITY_WEIGHT: float = 50000.0  # Bonificación por poner órdenes complejas primero
    
    # Bonus por reutilización de colores
    COLOR_REUSE_BONUS: float = 15.0  # Descuento por cada color que se reutiliza

class EnrichedOrder:
    """Clase interna para evitar parsear JSON repetidamente."""
    def __init__(self, order: SchedulableOrderModel):
        self.original: SchedulableOrderModel = order
        self.id: int = order.id
        
        # --- Pre-parseo de datos JSON ---
        try:
            self.colores: Set[str] = set(json.loads(order.colores)) if order.colores and order.colores != 'null' else set()
            self.materiales: Set[str] = set(json.loads(order.materiales)) if order.materiales and order.materiales != 'null' else set()
            datos_dict = json.loads(order.datos) if order.datos else {}
            self.id_cliente: Any = datos_dict.get('id_cliente')
        except (json.JSONDecodeError, TypeError):
            self.colores = set()
            self.materiales = set()
            self.id_cliente = None

def clasificar_urgencia(orden: SchedulableOrderModel) -> str:
    """Clasifica una orden por urgencia basado en sus días restantes."""
    dias = orden.dias_restantes if orden.dias_restantes is not None else 999
    if dias < -30: return 'CRITICA_ATRASADA'
    elif dias < 0: return 'ATRASADA'
    elif dias <= 3: return 'URGENTE'
    elif dias <= 7: return 'PROXIMA'
    else: return 'NORMAL'

class AlgoritmoGeneticoFlexo:
    def __init__(self, ordenes: List[SchedulableOrderModel], maquina_info: MachineModel):
        self.ordenes_dict: Dict[int, EnrichedOrder] = {o.id: EnrichedOrder(o) for o in ordenes}

        # Mapa de índice a ID de pedido (ej. 0 -> 32766)
        self.idx_to_order_id: List[int] = [o.id for o in ordenes]
        # Mapa inverso de ID de pedido a índice (ej. 32766 -> 0)
        self.order_id_to_idx: Dict[int, int] = {order_id: i for i, order_id in enumerate(self.idx_to_order_id)}

        self.maquina = maquina_info
        self.config = OptimizerConfig()
        
        # --- CONFIGURACIÓN DE DEAP (AHORA TRABAJA CON ÍNDICES) ---
        # 1. Definir el tipo de problema: Minimizar un solo objetivo (el 'fitness score').
        creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
        # 2. Definir la estructura de un 'Individuo': una lista con un atributo de fitness.
        creator.create("Individual", list, fitness=creator.FitnessMin)

        self.toolbox = base.Toolbox()
        # 3. Instrucciones para crear un individuo: una permutación aleatoria de los IDs de las órdenes.
        # El individuo ahora es una permutación de ÍNDICES (0, 1, 2, ...)
        num_items = len(self.idx_to_order_id)
        self.toolbox.register("indices", random.sample, range(num_items), num_items)
        self.toolbox.register("individual", tools.initIterate, creator.Individual, self.toolbox.indices)
        # 4. Instrucciones para crear una población: una lista de N individuos.
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)

        # 5. Registrar los operadores genéticos
        self.toolbox.register("evaluate", self._evaluate_fitness)
        self.toolbox.register("mate", tools.cxOrdered) # Crossover para secuencias
        self.toolbox.register("mutate", tools.mutShuffleIndexes, indpb=0.05) # Mutación: intercambia algunas posiciones
        self.toolbox.register("select", tools.selTournament, tournsize=3) # Selección: el mejor de 3 competidores aleatorios

    def _evaluate_fitness(self, individual_indices: List[int]) -> tuple[float,]:
        """
        Calcula la 'calidad' de una secuencia de producción. Un valor más bajo es mejor.
        DEAP requiere que el resultado sea una tupla.
        """
        score = 0.0
        tiempo_acumulado_minutos = 0.0

        # DEBUG: Para ver el score de las primeras 5 órdenes
        # debug_info = []

        for i, current_idx in enumerate(individual_indices):
            current_order_id = self.idx_to_order_id[current_idx]
            current_order = self.ordenes_dict[current_order_id]
            if not current_order: continue

            num_colores_orden = len(current_order.colores)
            posicion_normalizada = i / len(individual_indices)

            # score_antes = score  # Para debugging

            # Para órdenes complejas (5+ colores): BONIFICAR si están al inicio
            if num_colores_orden >= 5:
                bonificacion = ((1 - posicion_normalizada) ** 2) * num_colores_orden * self.config.HIGH_INK_PRIORITY_WEIGHT
                score -= bonificacion
                # if i < 5:
                #     debug_info.append(f"Pos {i}: Orden {current_order_id} ({num_colores_orden} colores) - BONIF: -{bonificacion:.0f}")

            # Para órdenes moderadas (3-4 colores): bonificación menor
            elif num_colores_orden >= 3:
                bonificacion = (1 - posicion_normalizada) * num_colores_orden * (self.config.HIGH_INK_PRIORITY_WEIGHT * 0.2)
                score -= bonificacion
                # if i < 5:
                #     debug_info.append(f"Pos {i}: Orden {current_order_id} ({num_colores_orden} colores) - bonif: -{bonificacion:.0f}")

            # Para órdenes simples (1-2 colores): PENALIZAR si están al inicio
            else:
                penalizacion = (1 - posicion_normalizada) * (3 - num_colores_orden) * (self.config.HIGH_INK_PRIORITY_WEIGHT * 0.5)
                score += penalizacion
                # if i < 5:
                #     debug_info.append(f"Pos {i}: Orden {current_order_id} ({num_colores_orden} colores) - PENAL: +{penalizacion:.0f}")

            # Penalización por cambio de materiales y setup
            if i > 0:
                previous_idx = individual_indices[i-1]
                previous_order_id = self.idx_to_order_id[previous_idx]
                previous_order = self.ordenes_dict[previous_order_id]

                costo_cambio = self._calcular_costo_cambio(previous_order, current_order)
                score += costo_cambio * self.config.SETUP_COST_WEIGHT
                tiempo_acumulado_minutos += costo_cambio

                # if i < 5:
                #     debug_info[-1] += f" | Setup: +{costo_cambio * self.config.SETUP_COST_WEIGHT:.0f}"

            tiempo_prod = self._estimar_tiempo_produccion(current_order.original)
            tiempo_acumulado_minutos += tiempo_prod

            functional_inks = self.maquina.functional_inks or self.maquina.inks
            if num_colores_orden > functional_inks:
                score += (num_colores_orden - functional_inks) * self.config.INK_OVERCAPACITY_PENALTY

            dias_entrega = current_order.original.dias_restantes
            if dias_entrega is not None:
                plazo_minutos = dias_entrega * 1440
                if tiempo_acumulado_minutos > plazo_minutos:
                    retraso_minutos = tiempo_acumulado_minutos - plazo_minutos
                    urgencia = clasificar_urgencia(current_order.original)

                    if urgencia in ['CRITICA_ATRASADA', 'ATRASADA']:
                        peso_penalizacion = 50.0
                    elif urgencia == 'URGENTE':
                        peso_penalizacion = 20.0
                    else:
                        peso_penalizacion = self.config.DELAY_PENALTY_WEIGHT

                    # Limitar la penalización máxima por retraso a 500k por orden
                    # Esto evita que órdenes MUY atrasadas dominen completamente el fitness
                    penalizacion_retraso = min(retraso_minutos * peso_penalizacion, 500000)
                    score += penalizacion_retraso

        # # DEBUG: Log solo ocasionalmente para no saturar
        # if random.random() < 0.01:  # 1% de las evaluaciones
        #     logger.info("=== SAMPLE FITNESS EVALUATION ===")
        #     for info in debug_info:
        #         logger.info(info)
        #     logger.info(f"Score final: {score:.0f}")

        return (score, )

    def _calcular_costo_cambio(self, orden_anterior: EnrichedOrder, orden_actual: EnrichedOrder) -> float:
        """
        Calcula un costo de transición detallado entre dos órdenes, usando datos pre-parseados,
        enfocándose en la similitud de materiales y, sobre todo, de colores.
        """
        costo_total = 0.0
        tiempo_base = self.maquina.time_change_units or 15.0

        try:
            # 1. Costo por Material (ahora usa los sets pre-calculados)
            if orden_anterior.materiales != orden_actual.materiales:
                costo_total += tiempo_base * self.config.MATERIAL_CHANGE_FACTOR
            else:
                costo_total += tiempo_base * self.config.MATERIAL_SAME_FACTOR

            # 2. Costo por Tintas (ahora usa los sets pre-calculados)
            tintas_a_quitar = orden_anterior.colores - orden_actual.colores
            tintas_a_anadir = orden_actual.colores - orden_anterior.colores
            tintas_reutilizadas = orden_anterior.colores & orden_actual.colores

            # Penalización ALTA por cada tinta que se debe AÑADIR (estrategia "mala")
            costo_total += len(tintas_a_anadir) * self.config.INK_ADD_COST

            # Penalización BAJA por cada tinta que se debe QUITAR (estrategia "buena")
            costo_total += len(tintas_a_quitar) * self.config.INK_CLEAN_COST

            # Bonus por cada tinta que se reutiliza (reduce el costo)
            costo_total -= len(tintas_reutilizadas) * self.config.COLOR_REUSE_BONUS

            # 3. Bonificación por Cliente (ahora usa el atributo pre-calculado)
            if orden_anterior.id_cliente and orden_anterior.id_cliente == orden_actual.id_cliente:
                costo_total *= self.config.SAME_CLIENT_BONUS_FACTOR
            
            # Asegurar que el costo nunca sea negativo
            costo_total = max(0.0, costo_total)

        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Error parseando JSON en costo de cambio: {e}")
            return self.maquina.time_change_units or 15.0 # Fallback a un costo base

        return costo_total
    
    def _estimar_tiempo_produccion(self, orden: SchedulableOrderModel) -> float:
        """Estima minutos de producción usando los metros totales."""
        if not orden.total_metros_impresion or not self.maquina.avg_velocity or self.maquina.avg_velocity == 0:
            return 0
        # avg_velocity está en metros/HORA, debemos convertirlo a minutos para que sea consistente con el resto de los cálculos de tiempo.
        velocidad_metros_por_hora = self.maquina.avg_velocity
        velocidad_metros_por_minuto = velocidad_metros_por_hora / 60.0
        
        return orden.total_metros_impresion / velocidad_metros_por_minuto

    def optimizar(self, poblacion_size=100, generaciones=100, cxpb=0.7, mutpb=0.2) -> List[int]:
        """
        Ejecuta el motor del algoritmo genético de DEAP, devuelve la mejor secuencia de IDs de pedido.

        MEJORAS:
        - Aumentado tamaño de población y generaciones para mejor convergencia
        """
        logger.info(f"Iniciando optimización con AG global para {len(self.idx_to_order_id)} órdenes...")
        if not self.ordenes_dict:
            return []
        
        pop = self.toolbox.population(n=poblacion_size)        
        hof = tools.HallOfFame(1)        # Guardar el mejor individuo encontrado
        
        # Ejecutar el algoritmo
        algorithms.eaSimple(
            pop,
            self.toolbox,
            cxpb=cxpb, # Probabilidad de cruce
            mutpb=mutpb, # Probabilidad de mutación
            ngen=generaciones,
            halloffame=hof,
            verbose=False # Poner en True para ver el progreso en los logs
        )
        
        # El mejor individuo (hof[0]) es una lista de ÍNDICES.
        # Lo traducimos de vuelta a una lista de IDs de pedido antes de devolverla.
        best_sequence_indices = hof[0]
        best_sequence_ids = [self.idx_to_order_id[idx] for idx in best_sequence_indices]

        logger.info(f"Optimización completada. Mejor fitness: {hof[0].fitness.values[0]}")
        
        return best_sequence_ids

class GestorPrioridades:
    def __init__(self, secuencia_inicial: List[int], ordenes_dict: Dict[int, SchedulableOrderModel], maquina_info: MachineModel):
        self.secuencia = secuencia_inicial
        self.ordenes_dict = ordenes_dict
        self.maquina_info = maquina_info
        self.bloqueos: Dict[int, str] = {}
        
        # Validar que todas las órdenes en la secuencia existan en el diccionario
        self._validar_consistencia_inicial()
    
    def _validar_consistencia_inicial(self):
        """
        Valida que todas las órdenes en la secuencia inicial existan en ordenes_dict.
        Esto es crítico para el futuro cuando las órdenes puedan cambiar de máquina.
        """
        ordenes_invalidas = [o_id for o_id in self.secuencia if o_id not in self.ordenes_dict]
        
        if ordenes_invalidas:
            logger.warning(
                f"Se encontraron {len(ordenes_invalidas)} órdenes en la secuencia que no pertenecen "
                f"a esta máquina o ya no son planificables: {ordenes_invalidas[:5]}..."
            )
            # Filtrar las órdenes inválidas de la secuencia
            self.secuencia = [o_id for o_id in self.secuencia if o_id in self.ordenes_dict]
            logger.info(f"Secuencia limpiada. Órdenes válidas restantes: {len(self.secuencia)}")
    
    def priorizar_sin_reprogramar(self, orden_id: int):
        """
        Mueve la orden al principio sin optimizar.
        
        CASO 1: Priorización simple - solo cambia el orden, no recalcula nada más.
        Útil cuando se necesita urgencia inmediata sin afectar el resto de la planificación.
        """
        if orden_id not in self.secuencia:
            logger.warning(f"Intento de priorizar orden {orden_id} que no está en la secuencia actual.")
            return
        
        # VALIDACIÓN: Verificar que la orden existe en el diccionario de órdenes válidas
        if orden_id not in self.ordenes_dict:
            logger.error(
                f"Orden {orden_id} está en la secuencia pero no en ordenes_dict. "
                f"Posiblemente fue movida a otra máquina."
            )
            # Limpiar la secuencia removiendo esta orden huérfana
            self.secuencia.remove(orden_id)
            return
        
        # Mover al inicio
        self.secuencia.remove(orden_id)
        self.secuencia.insert(0, orden_id)
        self.bloqueos[orden_id] = 'FORZADA'
        logger.info(f"Orden {orden_id} priorizada sin reprogramación (movida a posición 1).")
    
    def priorizar_con_reoptimizacion(self, orden_id: int):
        """
        Prioriza una orden al inicio y reoptimiza el resto de la secuencia.
        
        CASO 2: Priorización inteligente - coloca la orden al inicio pero reorganiza
        las demás órdenes de manera óptima considerando:
        - Similitudes de colores/materiales
        - Tiempos de cambio
        - Fechas de entrega
        
        IMPORTANTE: Solo optimiza las órdenes "libres" (no bloqueadas previamente).
        """
        if orden_id not in self.secuencia:
            logger.warning(f"Intento de priorizar con reoptimización orden {orden_id} no encontrada.")
            return
        
        # VALIDACIÓN: Verificar que la orden existe en ordenes_dict
        if orden_id not in self.ordenes_dict:
            logger.error(
                f"Orden {orden_id} no se encuentra en ordenes_dict. "
                f"Puede haber sido reasignada a otra máquina."
            )
            self.secuencia.remove(orden_id)
            return
        
        # Remover la orden a priorizar de la secuencia
        self.secuencia.remove(orden_id)
        
        # Identificar órdenes libres (no bloqueadas) para reoptimización
        ordenes_libres_ids = [o_id for o_id in self.secuencia if o_id not in self.bloqueos]
        
        # VALIDACIÓN CRÍTICA: Filtrar órdenes que ya no pertenecen a esta máquina
        # Esto es esencial para cuando se implemente la optimización multi-máquina
        ordenes_libres_ids_validas = []
        ordenes_removidas = []
        
        for o_id in ordenes_libres_ids:
            if o_id in self.ordenes_dict:
                ordenes_libres_ids_validas.append(o_id)
            else:
                ordenes_removidas.append(o_id)
                # Remover también de la secuencia principal
                if o_id in self.secuencia:
                    self.secuencia.remove(o_id)
        
        if ordenes_removidas:
            logger.warning(
                f"Se removieron {len(ordenes_removidas)} órdenes que ya no pertenecen "
                f"a esta máquina: {ordenes_removidas[:5]}..."
            )
        
        # Solo optimizar si hay órdenes libres válidas
        if ordenes_libres_ids_validas:
            ordenes_libres_obj = [self.ordenes_dict[o_id] for o_id in ordenes_libres_ids_validas]
            
            logger.info(
                f"Reoptimizando {len(ordenes_libres_obj)} órdenes libres "
                f"(excluyendo {len(self.bloqueos)} bloqueadas)."
            )
            
            ag = AlgoritmoGeneticoFlexo(ordenes_libres_obj, self.maquina_info)
            secuencia_nueva_optimizada = ag.optimizar(poblacion_size=100, generaciones=200)
        else:
            logger.info("No hay órdenes libres para reoptimizar.")
            secuencia_nueva_optimizada = []
        
        # Reconstruir la secuencia: bloqueadas + priorizada + optimizadas
        ordenes_bloqueadas = [o_id for o_id in self.secuencia if o_id in self.bloqueos and o_id != orden_id]
        
        self.secuencia = (
            ordenes_bloqueadas +
            [orden_id] +
            secuencia_nueva_optimizada
        )
        
        self.bloqueos[orden_id] = 'ALTA'
        logger.info(
            f"Orden {orden_id} priorizada CON reoptimización. "
            f"Nueva secuencia: {len(ordenes_bloqueadas)} bloqueadas, "
            f"1 priorizada, {len(secuencia_nueva_optimizada)} reoptimizadas."
        )

class OptimizadorTotal:
    def _build_machine_compatibility_graph(self, machines: List[MachineModel]) -> Dict[int, Set[int]]:
        """
        Construye un grafo de compatibilidad basado en la columna 'comparte_rodillos'.
        La relación es simétrica: si la Máquina A puede pasar a B, B también puede pasar a A.

        Returns:
            Dict[machine_id, Set[compatible_machine_ids]]
        """
        graph: Dict[int, Set[int]] = {m.id: set() for m in machines}

        for machine in machines:
            # Si la columna 'share_rolls' tiene datos
            if machine.share_rolls:
                try:
                    # Parsear el string JSON, que contiene una lista de IDs como strings.
                    compatible_ids_str = json.loads(machine.share_rolls)
                    # Convertir los IDs de string a entero.
                    compatible_ids = {int(cid) for cid in compatible_ids_str}

                    # Añadir las conexiones para la máquina actual
                    graph[machine.id].update(compatible_ids)

                    # --- LÓGICA CLAVE: ASEGURAR SIMETRÍA ---
                    # Para cada máquina compatible, añadir una conexión de vuelta.
                    for comp_id in compatible_ids:
                        if comp_id in graph:
                            graph[comp_id].add(machine.id)
                
                except (json.JSONDecodeError, ValueError):
                    logger.warning(
                        f"No se pudo interpretar 'comparte_rodillos' para la máquina {machine.id}. "
                        f"Valor: '{machine.share_rolls}'"
                    )
        
        # Opcional: Limpiar el grafo para que una máquina no se liste a sí misma como compatible.
        for machine_id, connections in graph.items():
            connections.discard(machine_id)
            
        logger.info(f"Grafo de compatibilidad construido: {graph}")
        return graph

    def _reasignar_ordenes_inteligente(
        self, 
        orders_by_machine: Dict[int, List[SchedulableOrderModel]],
        machines: List[MachineModel],
        machine_graph: Dict[int, Set[int]]
    ) -> List[Tuple[int, int, str]]:
        """
        Analiza las órdenes y sugiere reasignaciones entre máquinas compatibles.
        
        Dos fases separadas: 
            - Primero capacidad (crítico), luego balanceo (opcional)
            - Límites más inteligentes: Solo balancea máquinas con 20+ órdenes, mueve máximo 30%

        MEJORAS:
        - Evita reasignaciones duplicadas
        - Actualiza cargas dinámicamente
        - Prioriza reasignaciones por capacidad de tintas sobre balanceo
        """
        reasignaciones = []
        machines_dict = {m.id: m for m in machines}
        ordenes_ya_reasignadas = set()  # Tracking de órdenes procesadas

        # Calcular carga inicial de cada máquina
        machine_loads = {m_id: len(orders) for m_id, orders in orders_by_machine.items()}

        # FASE 1: Reasignaciones por CAPACIDAD (alta prioridad)
        for current_machine_id, ordenes in list(orders_by_machine.items()):
            current_machine = machines_dict.get(current_machine_id)
            if not current_machine:
                continue
            
            compatible_machines = machine_graph.get(current_machine_id, set())
            if not compatible_machines:
                continue
            
            functional_inks_current = current_machine.functional_inks or current_machine.inks

            # Revisar cada orden
            for orden in list(ordenes):  # list() para evitar modificar mientras iteramos
                if orden.id in ordenes_ya_reasignadas:
                    continue
                
                # Parsear colores
                try:
                    num_colores = len(json.loads(orden.colores)) if orden.colores and orden.colores != 'null' else 0
                except (json.JSONDecodeError, TypeError):
                    num_colores = 0

                # CRITERIO 1: Orden excede capacidad de tintas
                if num_colores > functional_inks_current:
                    mejor_maquina = None
                    mejor_capacidad = functional_inks_current

                    # Buscar la MEJOR máquina compatible (con más tintas disponibles)
                    for comp_id in compatible_machines:
                        comp_machine = machines_dict.get(comp_id)
                        if not comp_machine:
                            continue
                        
                        comp_inks = comp_machine.functional_inks or comp_machine.inks

                        # Buscar máquina con suficientes tintas y no sobrecargada
                        if num_colores <= comp_inks and comp_inks > mejor_capacidad:
                            # Verificar que no esté demasiado cargada
                            carga_comp = machine_loads.get(comp_id, 0)
                            if carga_comp < 50:  # Límite de carga razonable
                                mejor_capacidad = comp_inks
                                mejor_maquina = comp_id

                    if mejor_maquina:
                        reasignaciones.append((
                            orden.id,
                            mejor_maquina,
                            f"Requiere {num_colores} tintas (actual: {functional_inks_current}, nueva: {mejor_capacidad})"
                        ))
                        ordenes_ya_reasignadas.add(orden.id)

                        # ACTUALIZAR CARGAS INMEDIATAMENTE
                        machine_loads[current_machine_id] = machine_loads.get(current_machine_id, 0) - 1
                        machine_loads[mejor_maquina] = machine_loads.get(mejor_maquina, 0) + 1

        # FASE 2: Reasignaciones por BALANCEO DE CARGA (menor prioridad)
        # Solo procesar máquinas que aún estén sobrecargadas después de la Fase 1
        for current_machine_id in sorted(machine_loads.keys(), key=lambda x: machine_loads[x], reverse=True):
            carga_actual = machine_loads.get(current_machine_id, 0)

            # Solo balancear si tiene más de 20 órdenes (umbral más alto)
            if carga_actual <= 20:
                continue
            
            current_machine = machines_dict.get(current_machine_id)
            if not current_machine:
                continue
            
            compatible_machines = machine_graph.get(current_machine_id, set())
            if not compatible_machines:
                continue
            
            ordenes = orders_by_machine.get(current_machine_id, [])
            functional_inks_current = current_machine.functional_inks or current_machine.inks

            # Calcular cuántas órdenes mover (máximo 30% de la carga)
            max_ordenes_a_mover = min(int(carga_actual * 0.3), carga_actual - 15)
            ordenes_movidas_de_esta_maquina = 0

            for orden in list(ordenes):
                if orden.id in ordenes_ya_reasignadas:
                    continue
                
                if ordenes_movidas_de_esta_maquina >= max_ordenes_a_mover:
                    break
                
                # Parsear colores
                try:
                    num_colores = len(json.loads(orden.colores)) if orden.colores and orden.colores != 'null' else 0
                except (json.JSONDecodeError, TypeError):
                    num_colores = 0

                # Buscar la máquina compatible con MENOR carga
                mejor_target = None
                min_load = carga_actual

                for comp_id in compatible_machines:
                    comp_machine = machines_dict.get(comp_id)
                    if not comp_machine:
                        continue
                    
                    comp_load = machine_loads.get(comp_id, 0)
                    comp_inks = comp_machine.functional_inks or comp_machine.inks

                    # La máquina debe poder manejar la orden y tener significativamente menos carga
                    if (num_colores <= comp_inks and 
                        comp_load < min_load and 
                        (carga_actual - comp_load) >= 5):  # Diferencia mínima de 5 órdenes
                        min_load = comp_load
                        mejor_target = comp_id

                if mejor_target:
                    reasignaciones.append((
                        orden.id,
                        mejor_target,
                        f"Balanceo de carga (de {carga_actual} a {min_load} órdenes)"
                    ))
                    ordenes_ya_reasignadas.add(orden.id)
                    ordenes_movidas_de_esta_maquina += 1

                    # ACTUALIZAR CARGAS
                    machine_loads[current_machine_id] -= 1
                    machine_loads[mejor_target] = machine_loads.get(mejor_target, 0) + 1
                    carga_actual -= 1  # Actualizar variable local también

        logger.info(f"Reasignaciones calculadas: {len(reasignaciones)} "
                    f"({len([r for r in reasignaciones if 'Requiere' in r[2]])} por capacidad, "
                    f"{len([r for r in reasignaciones if 'Balanceo' in r[2]])} por balanceo)")

        return reasignaciones