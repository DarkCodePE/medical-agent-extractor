# app/workflow/medication_search_workflow.py

import logging
from typing import Dict, Any, Literal, List
from app.tools.check_gtin_in_database import check_gtin_in_database_v3, GtinService
from app.services.medication_vector_service import MedicationVectorService

logger = logging.getLogger(__name__)


async def search_medications_semantic(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo para búsqueda semántica cuando no hay código GTIN válido.

    Args:
        state: Estado actual con medicamentos procesados

    Returns:
        Estado actualizado con resultados de búsqueda semántica
    """
    logger.info("Iniciando búsqueda semántica de medicamentos")


    processed_medication = state.get("processed_medications")

    # Inicializar servicio de vectores
    vector_service = MedicationVectorService()

    # Construir query de búsqueda combinando campos disponibles
    search_terms = []

    medication_name = getattr(processed_medication, 'medication_name', None)
    if medication_name:
        search_terms.append(medication_name)

    common_denomination = getattr(processed_medication, 'common_denomination', None)
    if common_denomination:
        search_terms.append(common_denomination)

    concentration = getattr(processed_medication, 'concentration', None)
    if concentration:
        search_terms.append(concentration)

    form_simple = getattr(processed_medication, 'form_simple', None)
    if form_simple:
        search_terms.append(form_simple)

    brand_name = getattr(processed_medication, 'brand_name', None)
    if brand_name:
        search_terms.append(brand_name)

    # Crear query de búsqueda
    search_query = " ".join(search_terms)
    logger.info(f"Búsqueda semántica con query: '{search_query}'")

    # Realizar búsqueda semántica
    semantic_results = await vector_service.search_medications_semantic(
        query=search_query,
        limit=5
    )
    # Tomar el mejor resultado (mayor similitud)
    best_match = semantic_results[0]
    logger.info(
        f"Mejor coincidencia semántica: {best_match['medication_name']} (score: {best_match['similarity_score']:.3f})")

    # Enriquecer el medicamento procesado con la mejor coincidencia
    if best_match['similarity_score'] > 0.7:  # Umbral de confianza
        logger.info("Enriqueciendo medicamento con datos de búsqueda semántica")

        # Actualizar campos desde el mejor resultado
        if not getattr(processed_medication, 'common_denomination', None) and best_match.get('common_denomination'):
            processed_medication.common_denomination = best_match['common_denomination']

        if not getattr(processed_medication, 'concentration', None) and best_match.get('concentration'):
            processed_medication.concentration = best_match['concentration']

        if not getattr(processed_medication, 'form', None) and best_match.get('form'):
            processed_medication.form = best_match['form']

        if not getattr(processed_medication, 'form_simple', None) and best_match.get('form_simple'):
            processed_medication.form_simple = best_match['form_simple']

        if not getattr(processed_medication, 'brand_name', None) and best_match.get('brand_name'):
            processed_medication.brand_name = best_match['brand_name']

        if not getattr(processed_medication, 'country', None) and best_match.get('country'):
            processed_medication.country = best_match['country']

        if not getattr(processed_medication, 'presentation', None) and best_match.get('presentation'):
            processed_medication.presentation = best_match['presentation']

        if not getattr(processed_medication, 'product_type', None) and best_match.get('product_type'):
            processed_medication.product_type = best_match['product_type']

        if not getattr(processed_medication, 'fractions', None) and best_match.get('fractions'):
            processed_medication.fractions = best_match['fractions']

    return {
        "processed_medications": processed_medication,
        "semantic_results": semantic_results,
        "semantic_best_match": best_match,
        "enrichment_applied": best_match['similarity_score'] > 0.7
    }


async def check_vectorization_status() -> Dict[str, Any]:
    """
    Función auxiliar para verificar el estado de vectorización.

    🎯 PROPÓSITO:
    - Verificar si la colección de vectores tiene datos
    - Obtener estadísticas básicas de la colección
    - Determinar si está lista para búsquedas semánticas

    🔍 QUÉ HACE:
    1. Inicializa el MedicationVectorService
    2. Llama a get_collection_stats()
    3. Verifica si vectors_count > 0
    4. Retorna información estructurada

    Returns:
        Diccionario con información sobre el estado de la vectorización
    """
    try:
        from app.services.medication_vector_service import MedicationVectorService

        # Crear instancia del servicio
        vector_service = MedicationVectorService()

        # Obtener estadísticas de la colección Qdrant
        stats = vector_service.get_collection_stats()

        # Determinar si está vectorizada
        vectors_count = stats.get('vectors_count', 0)
        is_vectorized = vectors_count > 0

        return {
            "is_vectorized": is_vectorized,
            "vectors_count": vectors_count,
            "collection_name": stats.get('collection_name'),
            "status": stats.get('status'),
            "error": stats.get('error')
        }

    except Exception as e:
        return {
            "is_vectorized": False,
            "vectors_count": 0,
            "error": str(e)
        }