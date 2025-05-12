from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
import logging

from app.tools.check_gtin_in_database import GtinService, get_gtin_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/gtin",
    tags=["gtin"],
)


@router.get("/query/{gtin_code}")
async def get_product_by_gtin(
        gtin_code: str,
        gtin_service: GtinService = Depends(get_gtin_service)
):
    """
    Obtiene información de un producto por su código GTIN.

    Args:
        gtin_code: Código GTIN (código de barras) a consultar

    Returns:
        Información detallada del producto o error 404 si no se encuentra
    """
    try:
        product = gtin_service.query_gtin(gtin_code)
        if not product:
            raise HTTPException(status_code=404, detail=f"No se encontró producto con código GTIN: {gtin_code}")

        return {
            "status": "success",
            "message": f"Producto encontrado: {product['Name']}",
            "data": product
        }
    except Exception as e:
        logger.error(f"Error consultando GTIN {gtin_code}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al consultar GTIN: {str(e)}")


@router.get("/search")
async def search_products(
        query: str,
        limit: int = Query(10, ge=1, le=100),
        gtin_service: GtinService = Depends(get_gtin_service)
):
    """
    Busca productos que coincidan con el texto de búsqueda.

    Args:
        query: Texto para buscar en nombre, denominación común, etc.
        limit: Límite de resultados a devolver (1-100)

    Returns:
        Lista de productos que coinciden con la búsqueda
    """
    try:
        products = gtin_service.search_products(query, limit)

        return {
            "status": "success",
            "message": f"Se encontraron {len(products)} productos",
            "count": len(products),
            "data": products
        }
    except Exception as e:
        logger.error(f"Error buscando productos con '{query}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al buscar productos: {str(e)}")


@router.get("/stats")
async def get_inventory_stats(
        gtin_service: GtinService = Depends(get_gtin_service)
):
    """
    Obtiene estadísticas del inventario de productos GTIN.

    Returns:
        Estadísticas del inventario
    """
    try:
        stats = gtin_service.get_inventory_stats()

        return {
            "status": "success",
            "message": "Estadísticas de inventario obtenidas correctamente",
            "data": stats
        }
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de inventario: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener estadísticas: {str(e)}")