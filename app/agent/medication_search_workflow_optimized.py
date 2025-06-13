# app/agent/medication_search_workflow_optimized.py

import logging
from typing import Dict, Any, List, Optional
from app.tools.check_gtin_in_database import GtinService
from app.services.medication_vector_service import MedicationVectorService

logger = logging.getLogger(__name__)


async def search_medications_semantic_optimized(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo optimizado para búsqueda semántica con filtros de metadata inteligentes.
    
    Estrategia híbrida:
    - Filtros categóricos: common_denomination, product_type, form_simple (exactos)
    - Query semántica: concentration, medication_name, brand_name (aproximados)
    
    Args:
        state: Estado actual con medicamentos procesados
        
    Returns:
        Estado actualizado con resultados de búsqueda semántica optimizada
    """
    logger.info("🧠 Iniciando búsqueda semántica optimizada con filtros inteligentes")
    
    processed_medication = state.get("processed_medications")
    vector_service = MedicationVectorService()
    
    # PASO 1: Construir FILTROS (solo datos categóricos confiables)
    filters = {}
    
    common_denomination = getattr(processed_medication, 'common_denomination', None)
    if common_denomination and common_denomination.strip():
        filters["common_denomination"] = common_denomination.upper()
        logger.info(f"🎯 Filtro por common_denomination: {common_denomination}")
        
    product_type = getattr(processed_medication, 'product_type', None)
    if product_type and product_type.strip():
        filters["product_type"] = product_type.upper()
        logger.info(f"🎯 Filtro por product_type: {product_type}")
        
    form_simple = getattr(processed_medication, 'form_simple', None)
    if form_simple and form_simple.strip():
        filters["form_simple"] = form_simple.upper()
        logger.info(f"🎯 Filtro por form_simple: {form_simple}")
    
    # PASO 2: Construir QUERY (incluye datos numéricos/aproximados)
    search_terms = []
    
    medication_name = getattr(processed_medication, 'medication_name', None)
    if medication_name and medication_name.strip():
        search_terms.append(medication_name)
        
    # common_denomination también va en query para matching semántico
    if common_denomination and common_denomination.strip():
        search_terms.append(common_denomination)
        
    concentration = getattr(processed_medication, 'concentration', None)
    if concentration and concentration.strip():
        search_terms.append(concentration)  # ← Concentración en query, NO en filtros
        
    brand_name = getattr(processed_medication, 'brand_name', None)
    if brand_name and brand_name.strip():
        search_terms.append(brand_name)
        
    form = getattr(processed_medication, 'form', None)
    if form and form.strip():
        search_terms.append(form)
    
    search_query = " ".join(search_terms)
    logger.info(f"🔍 Query textual: '{search_query}'")
    
    # PASO 3: Determinar estrategia de búsqueda basada en filtros disponibles
    if len(filters) >= 2:
        # Estrategia PRECISA: Múltiples filtros disponibles
        search_strategy = "PRECISE_FILTERING"
        confidence_threshold = 0.75
        search_limit = 3
        logger.info("🎯 Estrategia PRECISA: Múltiples filtros disponibles")
        
    elif len(filters) == 1:
        # Estrategia MODERADA: Un filtro disponible
        search_strategy = "MODERATE_FILTERING"
        confidence_threshold = 0.80
        search_limit = 4
        logger.info("🎯 Estrategia MODERADA: Un filtro disponible")
        
    else:
        # Estrategia CONSERVADORA: Sin filtros
        search_strategy = "SEMANTIC_ONLY"
        confidence_threshold = 0.85
        search_limit = 5
        logger.info("🎯 Estrategia CONSERVADORA: Sin filtros categóricos")
    
    # PASO 4: Ejecutar búsqueda única con estrategia seleccionada
    semantic_results = await vector_service.search_medications_semantic(
        query=search_query,
        limit=search_limit,
        filters=filters if filters else None
    )
    
    # PASO 5: Evaluar resultados y aplicar enriquecimiento
    best_match = None
    enrichment_applied = False
    
    if semantic_results:
        best_match = semantic_results[0]
        similarity_score = best_match.get('similarity_score', 0.0)
        
        logger.info(f"Mejor resultado: {best_match.get('medication_name')} (score: {similarity_score:.3f}, threshold: {confidence_threshold})")
        
        if similarity_score >= confidence_threshold:
            logger.info(f"✅ Aplicando enriquecimiento con {search_strategy}")
            enrichment_applied = True
            
            # Enriquecer medicamento con mejor coincidencia
            if not processed_medication.medication_name and best_match.get('medication_name'):
                processed_medication.medication_name = best_match['medication_name']
                logger.info(f"Completado medication_name: {best_match['medication_name']}")
                
            if not processed_medication.common_denomination and best_match.get('common_denomination'):
                processed_medication.common_denomination = best_match['common_denomination']
                logger.info(f"Completado common_denomination: {best_match['common_denomination']}")
                
            if not processed_medication.concentration and best_match.get('concentration'):
                processed_medication.concentration = best_match['concentration']
                logger.info(f"Completado concentration: {best_match['concentration']}")
                
            if not processed_medication.form and best_match.get('form'):
                processed_medication.form = best_match['form']
                logger.info(f"Completado form: {best_match['form']}")
                
            if not processed_medication.form_simple and best_match.get('form_simple'):
                processed_medication.form_simple = best_match['form_simple']
                logger.info(f"Completado form_simple: {best_match['form_simple']}")
                
            if not processed_medication.brand_name and best_match.get('brand_name'):
                processed_medication.brand_name = best_match['brand_name']
                logger.info(f"Completado brand_name: {best_match['brand_name']}")
                
            if not processed_medication.country and best_match.get('country'):
                processed_medication.country = best_match['country']
                logger.info(f"Completado country: {best_match['country']}")
                
            if not processed_medication.presentation and best_match.get('presentation'):
                processed_medication.presentation = best_match['presentation']
                logger.info(f"Completado presentation: {best_match['presentation']}")
                
            if not processed_medication.product_type and best_match.get('product_type'):
                processed_medication.product_type = best_match['product_type']
                logger.info(f"Completado product_type: {best_match['product_type']}")
                
            if not processed_medication.fractions and best_match.get('fractions'):
                processed_medication.fractions = str(best_match['fractions'])
                logger.info(f"Completado fractions: {best_match['fractions']}")
        else:
            logger.info(f"❌ No se aplica enriquecimiento: {similarity_score:.3f} < {confidence_threshold}")
    else:
        logger.warning("❌ No se encontraron resultados semánticos")
    
    # PASO 6: Generar estadísticas de la búsqueda
    search_stats = {
        "filters_applied": len(filters),
        "filter_names": list(filters.keys()) if filters else [],
        "search_strategy": search_strategy,
        "confidence_threshold": confidence_threshold,
        "results_found": len(semantic_results),
        "best_score": best_match.get('similarity_score', 0.0) if best_match else 0.0
    }
    
    logger.info(f"📊 Estadísticas de búsqueda: {search_stats}")
    
    return {
        "processed_medications": processed_medication,
        "semantic_results": semantic_results,
        "semantic_best_match": best_match,
        "enrichment_applied": enrichment_applied,
        "search_strategy": search_strategy,
        "search_confidence": best_match.get('similarity_score', 0.0) if best_match else 0.0,
        "confidence_threshold_used": confidence_threshold,
        "search_stats": search_stats
    }