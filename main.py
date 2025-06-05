from fastapi import FastAPI
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.enpoints import medical, vectorization
import logging
from app.config.database import init_db


app = FastAPI()

# Configurar el logger
logging.basicConfig(level=logging.INFO)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    medical.router
)
# 🆕 Agregar el controlador de vectorización
app.include_router(
    vectorization.router
)
# Inicializa la base de datos
#init_db()


# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "version": "1.0.0",
        "langsmith_enabled": True
    }


if __name__ == "__main__":
    import uvicorn

    # Ejecuta la aplicación
    uvicorn.run(app, host="0.0.0.0", port=9088, workers=2)