# app/api/vectorization.py

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Depends
from datetime import datetime
import logging

from app.services.medication_vector_service import MedicationVectorService
from app.agent.medication_search_workflow import check_vectorization_status

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/vectorization",
    tags=["vectorization"],
)

# Estado global para tracking del proceso de vectorización
_vectorization_status = {
    "is_running": False,
    "start_time": None,
    "progress": 0,
    "status": "idle",
    "last_result": None
}


def get_vector_service():
    """Dependency para obtener el servicio de vectorización."""
    return MedicationVectorService()


@router.get("/status")
async def get_vectorization_status():
    """
    Obtiene el estado actual de la vectorización y estadísticas de la colección.

    Returns:
        Estado completo del sistema de vectorización
    """
    try:
        # Obtener estadísticas de la colección
        collection_status = await check_vectorization_status()

        return {
            "status": "success",
            "message": "Estado de vectorización obtenido correctamente",
            "data": {
                "vectorization_process": _vectorization_status,
                "collection": collection_status,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error obteniendo estado de vectorización: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener estado: {str(e)}")


@router.post("/start")
async def start_vectorization(
        background_tasks: BackgroundTasks,
        force: bool = Query(False, description="Reemplazar vectores existentes"),
        batch_size: int = Query(50, ge=10, le=200, description="Tamaño de lote para procesamiento"),
        vector_service: MedicationVectorService = Depends(get_vector_service)
):
    """
    Inicia el proceso de vectorización de medicamentos.

    Args:
        force: Si True, reemplaza vectores existentes
        batch_size: Tamaño de lote para procesamiento (10-200)

    Returns:
        Confirmación de inicio del proceso
    """
    global _vectorization_status

    try:
        # Verificar si ya hay un proceso en ejecución
        if _vectorization_status["is_running"]:
            raise HTTPException(
                status_code=409,
                detail="Ya hay un proceso de vectorización en ejecución"
            )

        # Verificar si ya hay vectores y no se fuerza
        collection_status = await check_vectorization_status()

        if collection_status["is_vectorized"] and not force:
            return {
                "status": "info",
                "message": "La base de datos ya está vectorizada",
                "data": {
                    "vectors_count": collection_status["vectors_count"],
                    "suggestion": "Use force=true para reemplazar vectores existentes"
                }
            }

        # Iniciar proceso en background
        _vectorization_status.update({
            "is_running": True,
            "start_time": datetime.utcnow().isoformat(),
            "progress": 0,
            "status": "starting",
            "last_result": None
        })

        background_tasks.add_task(
            _run_vectorization_process,
            vector_service=vector_service,
            batch_size=batch_size,
            force=force
        )

        return {
            "status": "success",
            "message": "Proceso de vectorización iniciado exitosamente",
            "data": {
                "batch_size": batch_size,
                "force": force,
                "estimated_time": "10-30 minutos dependiendo del tamaño de la BD"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error iniciando vectorización: {str(e)}")
        _vectorization_status["is_running"] = False
        raise HTTPException(status_code=500, detail=f"Error al iniciar vectorización: {str(e)}")


@router.post("/stop")
async def stop_vectorization():
    """
    Detiene el proceso de vectorización actual.

    Returns:
        Confirmación de solicitud de detención
    """
    global _vectorization_status

    if not _vectorization_status["is_running"]:
        raise HTTPException(
            status_code=400,
            detail="No hay proceso de vectorización en ejecución"
        )

    _vectorization_status.update({
        "status": "stopping",
        "stop_requested": True
    })

    return {
        "status": "success",
        "message": "Solicitud de detención enviada",
        "data": {
            "note": "El proceso se detendrá después del lote actual"
        }
    }


@router.delete("/clear")
async def clear_vectorization(
        confirm: bool = Query(False, description="Confirmación requerida para operación destructiva"),
        vector_service: MedicationVectorService = Depends(get_vector_service)
):
    """
    Elimina todos los vectores de la colección.
    ⚠️ OPERACIÓN DESTRUCTIVA - Requiere confirmación explícita.

    Args:
        confirm: Debe ser True para confirmar la operación

    Returns:
        Resultado de la operación de limpieza
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Operación destructiva requiere confirm=true"
        )

    try:
        # Obtener estadísticas antes de limpiar
        stats_before = vector_service.get_collection_stats()
        vectors_before = stats_before.get('vectors_count', 0)

        if vectors_before == 0:
            return {
                "status": "info",
                "message": "La colección ya está vacía",
                "data": {"vectors_count": 0}
            }

        # Recrear la colección (esto la limpia)
        vector_service.qdrant_client.delete_collection(vector_service.collection_name)
        vector_service._ensure_collection_exists()

        logger.info(f"Colección {vector_service.collection_name} limpiada exitosamente")

        return {
            "status": "success",
            "message": "Vectorización limpiada exitosamente",
            "data": {
                "vectors_removed": vectors_before,
                "collection_recreated": True
            }
        }

    except Exception as e:
        logger.error(f"Error limpiando vectorización: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al limpiar vectorización: {str(e)}")


@router.get("/search")
async def test_semantic_search(
        query: str = Query(..., description="Texto de búsqueda"),
        limit: int = Query(5, ge=1, le=20, description="Número máximo de resultados"),
        vector_service: MedicationVectorService = Depends(get_vector_service)
):
    """
    Prueba la búsqueda semántica con una query específica.

    Args:
        query: Texto de búsqueda
        limit: Número máximo de resultados (1-20)

    Returns:
        Resultados de la búsqueda semántica
    """
    try:
        # Verificar que hay vectores disponibles
        collection_status = await check_vectorization_status()

        if not collection_status["is_vectorized"]:
            raise HTTPException(
                status_code=400,
                detail="La base de datos no está vectorizada. Ejecute vectorización primero."
            )

        # Realizar búsqueda de prueba
        results = await vector_service.search_medications_semantic(query, limit)

        return {
            "status": "success",
            "message": f"Búsqueda completada: {len(results)} resultados encontrados",
            "data": {
                "query": query,
                "results_count": len(results),
                "results": results,
                "collection_vectors": collection_status["vectors_count"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en búsqueda de prueba: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error en búsqueda: {str(e)}")


@router.get("/stats")
async def get_collection_stats(
        vector_service: MedicationVectorService = Depends(get_vector_service)
):
    """
    Obtiene estadísticas detalladas de la colección de vectores.

    Returns:
        Estadísticas completas de la colección
    """
    try:
        collection_stats = vector_service.get_collection_stats()

        return {
            "status": "success",
            "message": "Estadísticas obtenidas correctamente",
            "data": collection_stats
        }

    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener estadísticas: {str(e)}")


@router.put("/update/{gtin_code}")
async def update_medication_vector(
        gtin_code: str,
        vector_service: MedicationVectorService = Depends(get_vector_service)
):
    """
    Actualiza el vector de un medicamento específico.

    Args:
        gtin_code: Código GTIN del medicamento a actualizar

    Returns:
        Resultado de la actualización
    """
    try:
        success = await vector_service.update_medication_vector(gtin_code)

        if success:
            return {
                "status": "success",
                "message": f"Vector actualizado exitosamente para GTIN: {gtin_code}",
                "data": {"gtin_code": gtin_code, "updated": True}
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontró medicamento con GTIN: {gtin_code}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando vector: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al actualizar vector: {str(e)}")


async def _run_vectorization_process(
        vector_service: MedicationVectorService,
        batch_size: int = 50,
        force: bool = False
):
    """
    Proceso de vectorización que se ejecuta en background.
    """
    global _vectorization_status

    try:
        _vectorization_status.update({
            "status": "running",
            "progress": 0
        })

        logger.info(f"🚀 Iniciando vectorización con batch_size={batch_size}")

        result = await vector_service.vectorize_all_medications(batch_size=batch_size)

        _vectorization_status.update({
            "is_running": False,
            "status": "completed" if result.get('success') else "failed",
            "progress": 100,
            "last_result": result,
            "end_time": datetime.utcnow().isoformat()
        })

        if result.get('success'):
            logger.info(f"✅ Vectorización completada: {result['total_processed']} medicamentos")
        else:
            logger.error(f"❌ Vectorización falló: {result}")

    except Exception as e:
        logger.error(f"💥 Error en proceso de vectorización: {str(e)}")
        _vectorization_status.update({
            "is_running": False,
            "status": "error",
            "error": str(e),
            "end_time": datetime.utcnow().isoformat()
        })