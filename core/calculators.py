import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Sequence, Union

from pydantic import BaseModel, model_validator
from schemas.db_models import SchedulableOrderModel, MachineModel, SchedulableOrdersFromMachine

logger = logging.getLogger(__name__)

# --- 1. MEJORA: Creamos una clase de configuración ---
class PlannerConfig(BaseModel):
    """Configuración para el calculador de fechas."""
    turnos_dia_semana: int = 1
    horas_por_turno_semana: int = 10
    turnos_sabado: int = 2
    dias_laborales: Optional[List[int]] = None  # Si es None, se asume Lun-Sab
    horas_por_turno_sabado: int = 8
    hora_inicio_turno1: int = 7
    eficiencia_maquina: float = 0.85  # 85% de eficiencia por defecto
    buffer_seguridad_pct: float = 0.01 # 1% de buffer
    costo_cambio_tinta_min: float = 5.0
    factor_cambio_material_completo: float = 1.0
    factor_cambio_material_parcial: float = 0.5
    bonificacion_mismo_cliente_pct: float = 0.7 # 30% de descuento

    @model_validator(mode='after')
    def set_default_dias_laborales(self) -> 'PlannerConfig':
        if self.dias_laborales is None:
            self.dias_laborales = [0, 1, 2, 3, 4, 5]  # Lun-Sab
        return self

class DateCalculator:
    """
    Clase que encapsula toda la lógica para calcular fechas probables de entrega.
    """
    def __init__(self, config: PlannerConfig):
        self.config = config

        self.minutos_laborables_por_dia: Dict[int, float] = {}
        minutos_semana = self.config.horas_por_turno_semana * 60 * self.config.turnos_dia_semana
        minutos_sabado = self.config.horas_por_turno_sabado * 60 * self.config.turnos_sabado

        for dia in range(7): # 0=Lunes, 6=Domingo
            if dia in self.config.dias_laborales:
                if dia == 5: # Sábado
                    self.minutos_laborables_por_dia[dia] = minutos_sabado
                else:
                    self.minutos_laborables_por_dia[dia] = minutos_semana
            else:
                self.minutos_laborables_por_dia[dia] = 0

    def _siguiente_dia_laboral(self, fecha: datetime) -> datetime:
        """Retorna el inicio del siguiente día laboral."""
        fecha_siguiente = (fecha + timedelta(days=1)).replace(hour=self.config.hora_inicio_turno1, minute=0, second=0)
        while fecha_siguiente.weekday() not in self.config.dias_laborales:
            fecha_siguiente += timedelta(days=1)
        return fecha_siguiente

    def _ajustar_horario_laboral(
            self, 
            fecha_inicio: datetime, 
            minutos_a_sumar: float
        ) -> datetime:
        """Ajusta una duración en minutos al calendario laboral de forma robusta."""
        fecha_actual = fecha_inicio
        minutos_restantes = minutos_a_sumar

        # Caso especial: si se trabaja 24/7, la lógica es mucho más simple.
        if all(self.minutos_laborables_por_dia.get(d, 0) == 1440 for d in range(7)):
            return fecha_actual + timedelta(minutes=minutos_restantes)

        # Bucle principal para consumir los minutos día por día
        while minutos_restantes > 0:
            dia_semana = fecha_actual.weekday()
            minutos_laborables_hoy = self.minutos_laborables_por_dia.get(dia_semana, 0)
            
            if minutos_laborables_hoy == 0:
                # Si no es un día laboral, saltar al inicio del siguiente.
                fecha_actual = (fecha_actual + timedelta(days=1)).replace(hour=self.config.hora_inicio_turno1, minute=0)
                continue
            
            # Calcular cuántos minutos quedan disponibles en el día actual
            hora_fin = self.config.hora_inicio_turno1 + (minutos_laborables_hoy / 60)
            fin_jornada_hoy = fecha_actual.replace(hour=int(hora_fin), minute=int((hora_fin * 60) % 60))
            
            minutos_disponibles_hoy = (fin_jornada_hoy - fecha_actual).total_seconds() / 60
            minutos_disponibles_hoy = max(0, minutos_disponibles_hoy)
            
            if minutos_restantes <= minutos_disponibles_hoy:
                # La tarea termina en el día actual.
                fecha_actual += timedelta(minutes=minutos_restantes)
                minutos_restantes = 0
            else:
                # La tarea consume todo el día y pasa al siguiente.
                minutos_restantes -= minutos_disponibles_hoy
                fecha_actual = (fecha_actual + timedelta(days=1)).replace(hour=self.config.hora_inicio_turno1, minute=0)
        
        return fecha_actual

    def _calcular_tiempo_cambio(
            self, 
            orden_anterior: Sequence[Union[SchedulableOrderModel, SchedulableOrdersFromMachine]], 
            orden_actual: Sequence[Union[SchedulableOrderModel, SchedulableOrdersFromMachine]], 
            machine: MachineModel
        ) -> float:
        """Calcula minutos de cambio, usando la configuración y acceso a atributos."""
        tiempo_base = machine.time_change_units or 15.0
        costo = 0.0
        try:
            materiales_ant = set(json.loads(orden_anterior.materiales)) if orden_anterior.materiales else set()
            materiales_act = set(json.loads(orden_actual.materiales)) if orden_actual.materiales else set()
            if materiales_ant != materiales_act:
                costo = tiempo_base * self.config.factor_cambio_material_completo
            else:
                costo = tiempo_base * self.config.factor_cambio_material_parcial
            
            costo += abs((orden_anterior.num_colores or 0) - (orden_actual.num_colores or 0)) * self.config.costo_cambio_tinta_min

            datos_ant = json.loads(orden_anterior.datos)
            datos_act = json.loads(orden_actual.datos)
            if datos_ant.get('id_cliente') == datos_act.get('id_cliente'):
                costo *= self.config.bonificacion_mismo_cliente_pct
        except (json.JSONDecodeError, TypeError):
            costo = tiempo_base
        return costo

    def calcular_fechas_probables(
            self, 
            ordenes_secuenciadas: Sequence[Union[SchedulableOrderModel, SchedulableOrdersFromMachine]], 
            fecha_inicio: datetime, 
            machine: MachineModel
        ) -> List[Dict]:
        """
        Función principal que calcula la fecha probable de entrega para cada orden. Ahora también retorna los tiempos desglosados para persistir en BD.
        """
        ordenes_con_fechas = []
        fecha_acumulada = fecha_inicio
        
        for i, orden in enumerate(ordenes_secuenciadas):
            # --- PASO 1: Calcular duración total de esta orden ---
            duracion_orden_minutos = 0.0
            
            # 1.1 Tiempo de setup (cambio entre órdenes)
            tiempo_setup = 0.0
            if i > 0:
                tiempo_setup = self._calcular_tiempo_cambio(ordenes_secuenciadas[i-1], orden, machine)

            # 1.2 Cambios internos (entre etiquetas del mismo pedido)
            num_etiquetas = orden.num_etiquetas or 1
            tiempo_cambios_internos = (num_etiquetas - 1) * (machine.time_change_units or 15.0)

            # 1.3 Tiempo de impresión (ajustado por eficiencia) convierte velocidad a metros/minuto
            velocidad_m_hora = machine.avg_velocity or 150.0
            velocidad_m_min = velocidad_m_hora / 60.0 # convertir a metros/minuto
            metros_totales = orden.total_metros_impresion or 0.0

            tiempo_impresion_teorico = (metros_totales / velocidad_m_min) if velocidad_m_min > 0 else 0
            tiempo_impresion_real = tiempo_impresion_teorico / self.config.eficiencia_maquina
            duracion_orden_minutos += tiempo_impresion_real
            
            # 1.4 Duración total sin buffer de seguridad
            duracion_total_orden = tiempo_setup + tiempo_cambios_internos + tiempo_impresion_real

            # 1.5 Buffer de seguridad (1%) se aplica a la duración de la orden actual, no al tiempo acumulado.
            tiempo_buffer = duracion_orden_minutos * self.config.buffer_seguridad_pct
            duracion_total_orden = duracion_orden_minutos + tiempo_buffer

            # --- LOGGING CRÍTICO PARA DEBUG ---
            logger.info(f"Orden {orden.id}: setup={tiempo_setup if i > 0 else 0:.1f}min, "
                        f"cambios={tiempo_cambios_internos:.1f}min, "
                        f"impresion={tiempo_impresion_real:.1f}min, "
                        f"buffer={duracion_total_orden - duracion_orden_minutos:.1f}min, "
                        f"TOTAL={duracion_total_orden:.1f}min ({duracion_total_orden/60:.1f}h)")
            
            # --- PASO 2: Calcular fecha probable ajustada al horario laboral ---
            fecha_fin_orden = self._ajustar_horario_laboral(fecha_acumulada, duracion_total_orden)

            # --- LOGGING DE FECHAS ---
            logger.info(f"  Inicio: {fecha_acumulada.strftime('%Y-%m-%d %H:%M')} -> "
                        f"Fin: {fecha_fin_orden.strftime('%Y-%m-%d %H:%M')}")
            
            # 6. Guardar resultados y actualizar la fecha para la siguiente iteración
            orden_dict = orden.model_dump()
            orden_dict['probable_fecha_entrega'] = fecha_fin_orden

            # Campos desglosados para persistir en BD
            orden_dict['tiempo_setup_min'] = round(tiempo_setup, 2)
            orden_dict['tiempo_cambios_internos_min'] = round(tiempo_cambios_internos, 2)
            orden_dict['tiempo_impresion_min'] = round(tiempo_impresion_real, 2)
            orden_dict['tiempo_buffer_min'] = round(tiempo_buffer, 2)
            orden_dict['tiempo_total_min'] = round(duracion_total_orden, 2)

            # Debug info (opcional, puedes removerlo después)
            orden_dict['debug_num_etiquetas'] = num_etiquetas

            ordenes_con_fechas.append(orden_dict)
            fecha_acumulada = fecha_fin_orden

        return ordenes_con_fechas