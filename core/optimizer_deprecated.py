import random
import json
import logging
from typing import Any, Dict, List, Set

# --- LIBRERÍAS DEL ALGORITMO GENÉTICO ---
from deap import base, creator, tools, algorithms

# Nuestros modelos Pydantic que vienen del servicio
from schemas.db_models import SchedulableOrderModel, MachineModel

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

    # Controla qué tan importante es poner trabajos complejos (muchas tintas) al principio.
    # Un valor más alto dará más prioridad a esta regla.
    HIGH_INK_PRIORITY_WEIGHT: float = 50000.0 

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
        
        for i, current_idx in enumerate(individual_indices):
            # Traducir el índice actual al ID del pedido y obtener el objeto
            current_order_id = self.idx_to_order_id[current_idx]
            current_order = self.ordenes_dict[current_order_id]

            if not current_order: continue

            # Penalización por cambio de materiales y setup
            if i > 0:
                previous_idx = individual_indices[i-1]
                previous_order_id = self.idx_to_order_id[previous_idx]
                previous_order = self.ordenes_dict[previous_order_id]
                
                costo_cambio = self._calcular_costo_cambio(previous_order, current_order)
                score += costo_cambio * self.config.SETUP_COST_WEIGHT
                tiempo_acumulado_minutos += costo_cambio
            
            tiempo_prod = self._estimar_tiempo_produccion(current_order.original)
            tiempo_acumulado_minutos += tiempo_prod
            
            # Penalización de tintas 
            functional_inks = self.maquina.functional_inks or self.maquina.inks
            num_colores_orden = len(current_order.colores)
            if num_colores_orden > functional_inks:
                score += (num_colores_orden - functional_inks) * self.config.INK_OVERCAPACITY_PENALTY # Penalización alta

            # Penalización por retraso (con manejo de None)
            dias_entrega = current_order.original.dias_restantes
            if dias_entrega is not None:
                plazo_minutos = dias_entrega * 1440
                if tiempo_acumulado_minutos > plazo_minutos:
                    retraso_minutos = tiempo_acumulado_minutos - plazo_minutos

                    # Asignar un peso de penalización basado en la urgencia
                    urgencia = clasificar_urgencia(current_order.original)
                    if urgencia in ['CRITICA_ATRASADA', 'ATRASADA']:
                        peso_penalizacion = 50.0 # Penalización muy alta
                    elif urgencia == 'URGENTE':
                        peso_penalizacion = 20.0 # Penalización alta
                    else:
                        peso_penalizacion = self.config.DELAY_PENALTY_WEIGHT # Penalización normal

                    score += retraso_minutos * peso_penalizacion

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

            # Penalización ALTA por cada tinta que se debe AÑADIR (estrategia "mala")
            costo_total += len(tintas_a_anadir) * self.config.INK_ADD_COST

            # Penalización BAJA por cada tinta que se debe QUITAR (estrategia "buena")
            costo_total += len(tintas_a_quitar) * self.config.INK_CLEAN_COST

            # 3. Bonificación por Cliente (ahora usa el atributo pre-calculado)
            if orden_anterior.id_cliente and orden_anterior.id_cliente == orden_actual.id_cliente:
                costo_total *= self.config.SAME_CLIENT_BONUS_FACTOR

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

    def optimizar(self, poblacion_size=50, generaciones=100, cxpb=0.7, mutpb=0.2) -> List[int]:
        """
        Ejecuta el motor del algoritmo genético de DEAP, devuelve la mejor secuencia de IDs de pedido.
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

    def priorizar_sin_reprogramar(self, orden_id: int):
        """Mueve la orden al principio sin optimizar, manejando errores."""
        # CORRECCIÓN: Manejo de error si la orden no está en la secuencia.
        if orden_id in self.secuencia:
            self.secuencia.remove(orden_id)
            self.secuencia.insert(0, orden_id)
            self.bloqueos[orden_id] = 'FORZADA'
            logger.info(f"Orden {orden_id} priorizada sin reprogramación.")
        else:
            logger.warning(f"Intento de priorizar orden {orden_id} que no está en la secuencia actual.")

    def priorizar_con_reoptimizacion(self, orden_id: int):
        """Saca la orden, optimiza el resto, y la pone al inicio."""
        if orden_id not in self.secuencia:
            logger.warning(f"Intento de priorizar con reoptimización orden {orden_id} no encontrada.")
            return

        self.secuencia.remove(orden_id)
        
        ordenes_libres_ids = [o_id for o_id in self.secuencia if o_id not in self.bloqueos]
        ordenes_libres_obj = [self.ordenes_dict[o_id] for o_id in ordenes_libres_ids]
        
        # Se pasa la información de la máquina correctamente.
        ag = AlgoritmoGeneticoFlexo(ordenes_libres_obj, self.maquina_info)
        secuencia_nueva_optimizada = ag.optimizar() # Se usa el método ahora existente.
        
        self.secuencia = (
            [o_id for o_id in self.secuencia if o_id in self.bloqueos and o_id != orden_id] +
            [orden_id] +
            secuencia_nueva_optimizada
        )
        self.bloqueos[orden_id] = 'ALTA'
        logger.info(f"Orden {orden_id} priorizada CON reoptimización del resto.")