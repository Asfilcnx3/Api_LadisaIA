import pytest
from DataAbstractionLayer.dummy_db import DummyDB

@pytest.fixture
def db() -> DummyDB:
    """Fixture de Pytest que proporciona una instancia limpia de DummyDB para cada prueba."""
    return DummyDB()

@pytest.mark.asyncio
async def test_get_machine_by_id(db: DummyDB):
    """Prueba que se puede obtener una máquina y que es un modelo Pydantic."""
    machine = await db.get_machine_by_id("Titán")
    assert machine is not None
    assert machine.id == "Titán" # <-- Se usa acceso por atributo, no por diccionario
    assert machine.name == "Máquina Titán"

@pytest.mark.asyncio
async def test_update_machine_status(db: DummyDB):
    """Prueba la actualización de estado de una máquina."""
    success = await db.update_machine_status("Titán", "maintenance")
    assert success is True
    machine = await db.get_machine_by_id("Titán")
    assert machine.status == "maintenance"

@pytest.mark.asyncio
async def test_prioritize_order(db: DummyDB):
    """Prueba la lógica de priorización de órdenes."""
    await db.prioritize_order(order_id="555777", reorder_rest=True)
    queue = await db.get_production_queue()
    assert queue[0].order_id == "555777"
    assert queue[0].sequence_order == 1 # Verificamos que la secuencia se reordenó

@pytest.mark.asyncio
async def test_register_roll_weight_logic(db: DummyDB):
    """Prueba la lógica de registro de peso, que requiere una orden activa."""
    # La máquina 'A' tiene la orden '789012' activa por defecto en DummyDB
    success = await db.register_roll_weight(machine_id="A", order_id="789012", weight_kg=50.5)
    assert success is True
    # Verificamos que el registro se creó (esto es una implementación interna, pero útil para probar)
    assert len(db._roll_weights) == 1
    assert db._roll_weights[0]["weight_kg"] == 50.5
    assert db._roll_weights[0]["order_id"] == "789012"