from fastapi import APIRouter
from api.v1.endpoints import commands

api_router = APIRouter()

# Incluimos el router de comandos bajo una etiqueta más descriptiva
api_router.include_router(
    commands.router,
    prefix="/commands",
    tags=["AI Command Processing"] 
)
