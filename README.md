# Imprenta Inteligente API

API inteligente para gestión de producción en imprenta que interpreta comandos en lenguaje natural y los convierte en acciones estructuradas.

## Características

- **Interpretación de lenguaje natural**: Convierte texto plano en acciones estructuradas usando OpenAI GPT-4
- **Gestión de máquinas**: Configurar mantenimiento, deshabilitar unidades, consultar estado
- **Priorización de órdenes**: Reordenar cola de producción dinámicamente  
- **Consultas inteligentes**: Estado de órdenes, avance de producción, métricas de máquinas
- **Registro de datos**: Pesos de rollos, desperdicios, incidencias
- **Alertas inteligentes**: Detección automática de órdenes cercanas a completarse
- **Arquitectura desacoplada**: Capa de abstracción de datos para múltiples BD

## Arquitectura

```
impronta_inteligente_api/
├── api/v1/endpoints/     # Endpoints REST
├── core/                 # Configuración y agente LLM
├── dal/                  # Capa de abstracción de datos
├── tools/                # Herramientas de negocio
├── schemas/              # Modelos Pydantic
└── tests/                # Pruebas unitarias
```

### Flujo de Procesamiento

1. **Entrada**: Usuario envía comando en texto natural
2. **Interpretación**: LLM analiza intención y extrae parámetros
3. **Validación**: Sistema valida comando estructurado
4. **Ejecución**: Se ejecuta la herramienta correspondiente
5. **Respuesta**: Resultado estructurado al usuario

## Instalación y Configuración

### Prerrequisitos

- Python 3.9+
- Cuenta OpenAI con API Key
- (Opcional) PostgreSQL, Redis para funciones avanzadas

### Instalación

```bash
# Clonar repositorio
git clone <repository-url>
cd imprenta_inteligente_api

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tu OpenAI API Key
```

### Configuración Básica

Edita el archivo `.env`:

```bash
OPENAI_API_KEY=sk-tu-api-key-aqui
OPENAI_MODEL=gpt-4
DATABASE_TYPE=dummy  # Para MVP sin BD real
```

## Uso

### Iniciar el Servidor

```bash
# Desarrollo
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Producción
uvicorn main:app --host 0.0.0.0 --port 8000
```

### API Endpoints

- **POST /api/v1/commands/process-command**: Procesar comando en lenguaje natural
- **GET /api/v1/commands/test-commands**: Obtener ejemplos de comandos
- **GET /api/v1/commands/status**: Estado del sistema
- **GET /docs**: Documentación interactiva (Swagger)

### Ejemplos de Comandos

```json
// Mantenimiento de máquinas
{
  "text": "Pon la máquina Titán en mantenimiento"
}

// Deshabilitar unidades
{
  "text": "La máquina Heidelberg tiene 2 unidades que no funcionan"
}

// Priorizar órdenes
{
  "text": "Dale prioridad a la orden 123456 en máquina Heidelberg"
}

// Consultas
{
  "text": "¿Cuándo entra a impresión la orden 123456?"
}

// Registro de datos
{
  "text": "Registra 50kg en el rollo que salió de la máquina A"
}
```

### Respuesta de Ejemplo

```json
{
  "success": true,
  "message": "Máquina 'Titán' puesta en mantenimiento exitosamente",
  "data": {
    "machine_id": "Titán",
    "new_status": "maintenance",
    "timestamp": "2024-01-01T10:30:00"
  },
  "action_executed": "ignore_machine"
}
```

## Desarrollo

### Estructura de Comandos

El sistema interpreta comandos y los convierte en JSON estructurado:

```python
# Entrada del usuario
"Pon la máquina Titán en mantenimiento"

# Interpretación del LLM
{
  "action": "ignore_machine",
  "machine_id": "Titán"
}

# Ejecución
await scheduling_tools.ignore_machine("Titán")
```

### Agregar Nuevas Acciones

1. **Definir acción en el prompt** (`core/agent.py`)
2. **Implementar herramienta** (`tools/`)
3. **Agregar ejecutor** (`api/v1/endpoints/commands.py`)
4. **Actualizar DAL si es necesario** (`dal/`)

### Cambiar Base de Datos

```python
# En main.py o mediante inyección de dependencias
from dal.postgres_db import PostgresDB
# db_instance = DummyDB()  # MVP
db_instance = PostgresDB()  # Producción
```

## Testing

```bash
# Ejecutar pruebas
pytest

# Con cobertura
pytest --cov=app tests/

# Prueba específica
pytest tests/test_commands.py -v
```

### Pruebas Manuales

```bash
# Probar endpoint con curl
curl -X POST "http://localhost:8000/api/v1/commands/process-command" \
  -H "Content-Type: application/json" \
  -d '{"text": "Pon la máquina A en mantenimiento"}'
```

## Roadmap

### Fase 0: MVP (Completado)
- [x] API FastAPI básica
- [x] Integración con OpenAI GPT-4
- [x] Comandos básicos de gestión
- [x] Base de datos simulada (DummyDB)
- [x] Documentación y ejemplos

### Fase 1: Base de Datos Real (En desarrollo)
- [ ] Implementación PostgreSQL
- [ ] Migraciones con Alembic  
- [ ] Persistencia de datos real
- [ ] Métricas y reportes

### Fase 2: Funciones Avanzadas (En desarrollo)
- [ ] Integración WhatsApp (Twilio)
- [ ] Comparación de imágenes (OpenCV)
- [ ] Tareas asíncronas (Celery)
- [ ] Alertas inteligentes en tiempo real

### Fase 3: Producción (En desarrollo)
- [ ] Autenticación y autorización
- [ ] Logging estructurado
- [ ] Monitoreo y métricas
- [ ] Deployment con Docker

## Contribuir

1. Fork el proyecto
2. Crear rama para feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request

## Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para detalles.

## Soporte

Para soporte y preguntas:

- Crear un issue en GitHub
- Revisar la documentación en `/docs`
- Consultar ejemplos en `/test-commands`

---

**Desarrollado por KiaB.dev con amor para mejorar la industria de la impresión**