from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, DateTime, func, Boolean, ForeignKey
from datetime import datetime, timezone
from typing import Optional

# Clase base para nuestros modelos ORM
class Base(DeclarativeBase):
    pass

class Machine(Base):
    """
    Representa la tabla de máquinas en la base de datos.
    """
    __tablename__ = "maquina"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)

    name: Mapped[str] = mapped_column("nombre", String(255))
    created_at: Mapped[DateTime] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column("updated_at", DateTime, onupdate=func.now())
    rolls: Mapped[Optional[int]] = mapped_column("rodillos", Integer, nullable=True)

    max_width: Mapped[int] = mapped_column("ancho_maximo", Integer)
    inks: Mapped[int] = mapped_column("numero_tintas", Integer)
    exact_register: Mapped[bool] = mapped_column("registro_exacto", Boolean)
    plant: Mapped[int] = mapped_column("planta", Integer)

    pseudonym: Mapped[Optional[str]] = mapped_column("seudonimo", String(100), nullable=True)
    share_rolls: Mapped[Optional[str]] = mapped_column("comparte_rodillos", nullable=True)
    time_change_units: Mapped[float] = mapped_column("tiempo_cambio_unidad", Float)
    avg_velocity: Mapped[float] = mapped_column("velocidad_promedio", Float)
    estatus: Mapped[str] = mapped_column("estatus", String(50), default="activa")
    functional_inks: Mapped[int] = mapped_column("tintas_funcionando", Integer)

class Mermas(Base):
    """
    Representa la tabla de 'registro_mermas' en la base de datos.
    """
    __tablename__ = "registro_mermas"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column("pedido_id", Integer, nullable=False)
    process: Mapped[str] = mapped_column("proceso", String(50), nullable=False)
    reason_id: Mapped[int] = mapped_column("razon_id", Integer, nullable=False)
    quantity: Mapped[float] = mapped_column("cantidad", Float, nullable=False)
    observations: Mapped[Optional[str]] = mapped_column("observaciones", String(255), nullable=True)
    user_id: Mapped[int] = mapped_column("usuario_id", Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column("updated_at", DateTime, onupdate=func.now())

class RazonMermas(Base):
    """
    Representa la tabla de 'razon_mermas' en la base de datos.
    """
    __tablename__ = "razon_mermas"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    name: Mapped[str] = mapped_column("nombre", String(100))
    description: Mapped[Optional[str]] = mapped_column("descripcion", String(255), nullable=True)
    active: Mapped[bool] = mapped_column("activo", Boolean, default=1)
    created_at: Mapped[DateTime] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column("updated_at", DateTime, onupdate=func.now())

class Pedidos(Base):
    """
    Representa una parte de la tabla de 'pedido' en la base de datos.
    """
    __tablename__ = "pedido"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    created_at: Mapped[DateTime] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column("updated_at", DateTime, onupdate=func.now())
    user_id: Mapped[int] = mapped_column("usuario", Integer, nullable=False)
    product_id: Mapped[int] = mapped_column("producto_id", Integer, nullable=False)
    total_kg: Mapped[float] = mapped_column("cantidad", Float, nullable=False)
    status: Mapped[int] = mapped_column("status", Integer, nullable=False)

class Productos(Base):
    """
    Representa una parte de la tabla de 'productos' en la base de datos.
    """
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column("id_producto", Integer, primary_key=True)
    product_type_id: Mapped[int] = mapped_column("id_tipo_producto", Integer, nullable=False)
    name: Mapped[str] = mapped_column("nombre", String(255), nullable=False)
    created_at: Mapped[DateTime] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column("updated_at", DateTime, onupdate=func.now())

class Etiqueta(Base):
    """
    Representa una parte de la tabla de 'etiqueta' en la base de datos.
    """
    __tablename__ = "etiqueta"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    gross_weight: Mapped[float] = mapped_column("peso_bruto", Float, nullable=False)
    net_weight: Mapped[float] = mapped_column("peso_neto", Float, nullable=False)
    purchase_id: Mapped[int] = mapped_column("compra_id", Integer, nullable=False)
    order_id: Mapped[int] = mapped_column("pedido_id", Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column("updated_at", DateTime, onupdate=func.now())
    user_id: Mapped[int] = mapped_column("usuario_id", Integer, nullable=False)
    label_for: Mapped[str] = mapped_column("etiqueta_para", String(100), nullable=False)
    show: Mapped[bool] = mapped_column("mostrar", Boolean, default=True)
    printing_meters: Mapped[float] = mapped_column("metros_impresion", Float, nullable=False)

class SubEtiqueta1(Base):
    """
    Representa una parte de la tabla de 'sub_etiqueta_1' en la base de datos.
    """
    __tablename__ = "sub_etiqueta_1"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    net_weight_impression: Mapped[float] = mapped_column("peso_neto_impresion", Float, nullable=False)
    created_at: Mapped[DateTime] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column("updated_at", DateTime, onupdate=func.now())
    user_id: Mapped[int] = mapped_column("usuario_id", Integer, nullable=False)
    order_id: Mapped[int] = mapped_column("pedido_id", Integer, nullable=False)
    show: Mapped[bool] = mapped_column("mostrar", Boolean, default=True)

class OrdenPedido(Base):
    """Representa la tabla 'orden_impresion_i_a_s' que define la secuencia de producción."""
    __tablename__ = "orden_impresion_i_a_s"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column("pedido_id", ForeignKey("pedido.id"))
    machine_id: Mapped[int] = mapped_column("maquina_id", ForeignKey("maquina.id"))
    order_production: Mapped[int] = mapped_column("orden", Integer, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column("razon", String(255), nullable=True)
    probable_delivery_date: Mapped[Optional[DateTime]] = mapped_column("probable_fecha_entrega", DateTime, nullable=False)
    # Se reemplazan los defaults del servidor por defaults del cliente (Python).
    # Usamos datetime.now(timezone.utc) para evitar problemas con zonas horarias.
    created_at: Mapped[datetime] = mapped_column(
        "created_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) # Se ejecuta al crear el objeto en Python
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updated_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), # Se ejecuta al crear
        onupdate=lambda: datetime.now(timezone.utc) # Se ejecuta al actualizar
    )

    # Nuevos campos para calculo de tiempo 
    tiempo_setup_min: Mapped[Optional[float]] = mapped_column("tiempo_setup_min", Float, nullable=True, default=0.0)
    tiempo_cambios_internos_min: Mapped[Optional[float]] = mapped_column("tiempo_cambios_internos_min", Float, nullable=True, default=0.0)
    tiempo_impresion_min: Mapped[Optional[float]] = mapped_column("tiempo_impresion_min", Float, nullable=True, default=0.0)
    tiempo_buffer_min: Mapped[Optional[float]] = mapped_column("tiempo_buffer_min", Float, nullable=True, default=0.0)
    tiempo_total_min: Mapped[Optional[float]] = mapped_column("tiempo_total_min", Float, nullable=True, default=0.0)