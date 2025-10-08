import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from main import app
from api.v1.dependencies import get_agent_instance
from schemas.api_models import CommandResponse

# El cliente de prueba para nuestra aplicación FastAPI
client = TestClient(app)

# --- Mock del Agente de Producción ---
# Creamos un mock asíncrono que simulará ser nuestro ProductionAgent.
# Esto evita hacer llamadas reales a la API de OpenAI durante las pruebas.
mock_agent = AsyncMock()

# Usamos la potente función de FastAPI para sobreescribir la dependencia.
# Ahora, cuando el endpoint pida `get_agent_instance`, FastAPI le dará nuestro mock.
app.dependency_overrides[get_agent_instance] = lambda: mock_agent

@pytest.mark.parametrize("user_input, agent_response, expected_status, expected_message_part", [
    (
        "Pon la máquina Titán en mantenimiento",
        {"action": "ignore_machine", "parameters": {"machine_ids": ["Titán"]}},
        200,
        "mantenimiento"
    ),
    (
        "Dale prioridad a la orden 555777",
        {"action": "prioritize_order", "parameters": {"order_id": "555777", "reorder_rest": False}},
        200,
        "priorizada exitosamente"
    ),
    (
        "cuál es el estado de la máquina A",
        {"action": "query_machine_status", "parameters": {"machine_id": "A"}},
        200,
        "Estado de 'Máquina A'"
    ),
    (
        "no entiendo nada",
        {"action": "unknown_request", "parameters": {"user_request": "no entiendo nada"}},
        200,
        "no reconocida" # El despachador responderá que la acción no es reconocida
    ),
    (
        "falla interna",
        {"action": "error", "message": "Fallo simulado del LLM"},
        200, # El endpoint maneja el error y devuelve una respuesta controlada
        "Fallo simulado del LLM"
    )
])
def test_process_command_endpoint(user_input, agent_response, expected_status, expected_message_part):
    """
    Prueba parametrizada para el endpoint /process.
    Verifica que el endpoint orquesta correctamente la llamada al agente y al despachador.
    """
    # Configuramos el valor de retorno de nuestro mock para esta prueba específica
    mock_agent.process_command.return_value = agent_response
    
    # Hacemos la llamada a la API
    response = client.post(
        "/api/v1/commands/process", # <-- URL actualizada
        json={"text": user_input}
    )
    
    # Verificamos los resultados
    assert response.status_code == expected_status
    data = response.json()
    assert expected_message_part in data["message"]
    
    # Verificamos que nuestro mock fue llamado exactamente una vez con el texto correcto
    mock_agent.process_command.assert_called_once_with(user_input)
    mock_agent.process_command.reset_mock() # Limpiamos el mock para la siguiente prueba

def test_health_check_endpoint():
    """Prueba el endpoint de health check."""
    response = client.get("/api/v1/commands/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"