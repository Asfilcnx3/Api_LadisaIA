import uvicorn
from fastapi import FastAPI, Depends
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi.middleware.cors import CORSMiddleware
from DataAbstractionLayer.base import BaseDatabase
from api.v1.api import api_router
from core.config import settings
from api.v1.dependencies import get_db_instance
from fastapi import HTTPException
from schemas.api_models import HealthCheckResponse

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Imprenta Inteligente API",
    description="API para gestión inteligente de producción en imprenta mediante comandos/ordenes con lenguaje natural",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    root_path="/ladisa"
)

instrumentator = Instrumentator().instrument(app)

# Configurar CORS (Cross-Origin Resource Sharing)
# Es importante restringir los origines en un entorno de prooducción para mayor seguridad
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS if settings.ENVIRONMENT == "production" else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Incluir routers de la API v1
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/", tags=["root"])
async def root():
    """
    Endpoint raíz que devuelve información básica y la URL de la documentación.
    """
    return {
        "message": f"Bienvenido a {settings.PROJECT_NAME}",
        "version": settings.APP_VERSION,
        "docs_url": f"{settings.API_V1_STR}/docs",
        "health_url": f"{settings.API_V1_STR}/health"
    }

@app.get(
    "/health", 
    tags=["health"],
    response_model=HealthCheckResponse,
    summary="Verifica la salud del servicio y sus dependencias",
    description="Verifica la salud del servicio y sus dependencias"
)
async def health_check(db: BaseDatabase = Depends(get_db_instance)):
    """
    Realiza una comprobación de la salud del servicio
    - Verifica la conectividad con la base de datos.
    - Devuelve un estado general del sistema.
    """
    db_status = "connected"
    try:
        # Verificar conexión a la base de datos
        await db.check_connection()
    except Exception as e:
        db_status = "disconnected"
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "database_status": db_status,
                "error": str(e)
            }
        )
    return HealthCheckResponse(
        status="healthy",
        database_status=db_status,
        database_type=settings.DATABASE_TYPE
    )

# Bloque para ejecución en desarollo local
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )