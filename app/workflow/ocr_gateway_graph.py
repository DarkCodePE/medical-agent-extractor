# app/workflow/ocr_gateway_graph.py

from typing import Dict, Any, Literal
from langgraph.graph import StateGraph
from langgraph.constants import START, END
import logging

from langgraph.types import Send

from app.agent.medication_processor import MedicationProcessor
from app.agent.medication_search_workflow import search_medications_semantic
from app.agent.ocr_gateway_extractor import OCRGatewayExtractor
from app.tools.check_gtin_in_database import check_gtin_in_database_v3, GtinService

from app.workflow.builder.base import GraphBuilder
from app.agent.medication_extraction_state import MedicationExtractionState
from app.workflow.medication_extraction_graph import MedicationExtractionGraph

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def should_return_enriched_data(state: Dict[str, Any]) -> Literal["end"]:
    """
    Función simple para finalizar el flujo después de enriquecer los datos con información GTIN.

    Args:
        state: Estado actual con información completa

    Returns:
        "end" para terminar el flujo
    """
    logger.info("Finalizando flujo después de procesar datos y verificar GTIN")
    return "end"


def check_has_valid_gtin(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo que verifica si hay un código GTIN válido y si existe en la base de datos.

    Args:
        state: Estado actual del workflow con processed_medications

    Returns:
        Dict con gtin_found indicando si el código es válido y existe en la BD
    """
    logger.info("Verificando validez de código GTIN y existencia en base de datos")

    processed_medication = state.get("processed_medications")
    gtin_found = False

    if not processed_medication or not processed_medication.bar_code:
        logger.warning("No se encontró código de barras en processed_medications")
        return {"gtin_found": False}

    bar_code = processed_medication.bar_code
    logger.info(f"Código de barras original: {bar_code}")

    # Limpiar y validar formato del código
    clean_code = bar_code.strip().replace('-', '').replace(' ', '')
    logger.info(f"Código de barras limpio: {clean_code}")

    # Verificar formato válido de GTIN
    is_valid_format = clean_code.isdigit() and len(clean_code) in [8, 12, 13, 14]

    if not is_valid_format:
        logger.warning(f"Código GTIN '{clean_code}' no tiene formato válido")
        return {"gtin_found": False}

    logger.info(f"Código GTIN '{clean_code}' tiene formato válido, consultando base de datos...")

    try:
        # Inicializar servicio GTIN y consultar la base de datos
        gtin_service = GtinService()
        db_result = gtin_service.query_gtin(clean_code)

        if db_result:
            gtin_found = True
            logger.info(f"✅ GTIN '{clean_code}' encontrado en base de datos: {db_result.get('Name', 'Sin nombre')}")
        else:
            logger.info(f"❌ GTIN '{clean_code}' NO encontrado en base de datos")

    except Exception as e:
        logger.error(f"Error al consultar GTIN en base de datos: {str(e)}")
        # En caso de error de BD, consideramos que no se encontró
        gtin_found = False

    return {
        "gtin_found": gtin_found,
    }


def finalize_data_enrichment(state: MedicationExtractionState) -> Dict[str, Any]:
    """
    Nodo de finalización que combina y completa los datos del medicamento
    usando información de la base de datos GTIN y/o búsqueda semántica.
    
    Lógica:
    - Si se encontraron datos en BD GTIN: usar preferentemente esos datos
    - Si NO se encontraron datos en BD GTIN: usar datos de búsqueda semántica para completar campos faltantes
    - Siempre mantener datos extraídos del OCR cuando sean específicos (lote, fecha de vencimiento)
    
    Args:
        state: Estado actual del workflow
        
    Returns:
        Estado final con datos enriquecidos y consolidados
    """
    logger.info("🔄 Iniciando finalización y enriquecimiento de datos")
    
    processed_medication = state.get("processed_medications")
    gtin_found = state.get("gtin_found", False)
    database_info = state.get("database_info")
    semantic_results = state.get("semantic_results", [])
    semantic_best_match = state.get("semantic_best_match")
    enrichment_applied = state.get("enrichment_applied", False)
    
    logger.info(f"Estado inicial: GTIN encontrado={gtin_found}, Búsqueda semántica completada={len(semantic_results) > 0}")
    
    # CASO 1: Si se encontraron datos en la base de datos GTIN
    if gtin_found and database_info:
        logger.info("✅ Datos encontrados en BD GTIN - Priorizando información de base de datos")
        
        # Los datos ya fueron enriquecidos en el nodo exact_gtin_search
        # Solo agregamos información de contexto sobre la fuente de datos
        final_data_source = "database_gtin"
        enrichment_confidence = 1.0  # Máxima confianza en datos de BD
        
        logger.info(f"Medicamento finalizado con datos de BD: {processed_medication.medication_name}")
        
    # CASO 2: NO se encontraron datos en BD GTIN, usar búsqueda semántica
    elif not gtin_found and semantic_results and semantic_best_match:
        logger.info("🔍 No se encontraron datos en BD GTIN - Usando búsqueda semántica para completar datos")
        
        similarity_score = semantic_best_match.get('similarity_score', 0.0)
        enrichment_confidence = similarity_score
        
        # Completar campos faltantes con datos de búsqueda semántica si la confianza es suficiente
        if similarity_score > 0.7:  # Umbral de confianza
            logger.info(f"Completando datos faltantes con búsqueda semántica (confianza: {similarity_score:.3f})")
            
            # Completar solo campos que están vacíos o None desde OCR
            if not processed_medication.medication_name and semantic_best_match.get('medication_name'):
                processed_medication.medication_name = semantic_best_match['medication_name']
                logger.info(f"Completado medication_name: {semantic_best_match['medication_name']}")
                
            if not processed_medication.common_denomination and semantic_best_match.get('common_denomination'):
                processed_medication.common_denomination = semantic_best_match['common_denomination']
                logger.info(f"Completado common_denomination: {semantic_best_match['common_denomination']}")
                
            if not processed_medication.concentration and semantic_best_match.get('concentration'):
                processed_medication.concentration = semantic_best_match['concentration']
                logger.info(f"Completado concentration: {semantic_best_match['concentration']}")
                
            if not processed_medication.form and semantic_best_match.get('form'):
                processed_medication.form = semantic_best_match['form']
                logger.info(f"Completado form: {semantic_best_match['form']}")
                
            if not processed_medication.form_simple and semantic_best_match.get('form_simple'):
                processed_medication.form_simple = semantic_best_match['form_simple']
                logger.info(f"Completado form_simple: {semantic_best_match['form_simple']}")
                
            if not processed_medication.brand_name and semantic_best_match.get('brand_name'):
                processed_medication.brand_name = semantic_best_match['brand_name']
                logger.info(f"Completado brand_name: {semantic_best_match['brand_name']}")
                
            if not processed_medication.country and semantic_best_match.get('country'):
                processed_medication.country = semantic_best_match['country']
                logger.info(f"Completado country: {semantic_best_match['country']}")
                
            if not processed_medication.presentation and semantic_best_match.get('presentation'):
                processed_medication.presentation = semantic_best_match['presentation']
                logger.info(f"Completado presentation: {semantic_best_match['presentation']}")
                
            if not processed_medication.product_type and semantic_best_match.get('product_type'):
                processed_medication.product_type = semantic_best_match['product_type']
                logger.info(f"Completado product_type: {semantic_best_match['product_type']}")
                
            if not processed_medication.fractions and semantic_best_match.get('fractions'):
                processed_medication.fractions = str(semantic_best_match['fractions'])
                logger.info(f"Completado fractions: {semantic_best_match['fractions']}")
            
            final_data_source = "semantic_search"
            logger.info(f"✅ Medicamento enriquecido con búsqueda semántica (confianza: {similarity_score:.3f})")
        else:
            final_data_source = "ocr_only"
            enrichment_confidence = 0.0
            logger.info("❌ Búsqueda semántica con baja confianza - Manteniendo solo datos de OCR")
            
    # CASO 3: No se encontraron datos en ninguna fuente
    else:
        logger.warning("⚠️ No se encontraron datos complementarios - Solo datos extraídos por OCR")
        final_data_source = "ocr_only"
        enrichment_confidence = 0.0
    
    # Validar campos críticos
    missing_critical_fields = []
    if not processed_medication.medication_name:
        missing_critical_fields.append("medication_name")
    if not processed_medication.bar_code:
        missing_critical_fields.append("bar_code")
        
    if missing_critical_fields:
        logger.warning(f"⚠️ Campos críticos faltantes: {missing_critical_fields}")
    
    # Crear resumen de completitud de datos
    completeness_summary = {
        "medication_name": bool(processed_medication.medication_name),
        "common_denomination": bool(processed_medication.common_denomination),
        "concentration": bool(processed_medication.concentration),
        "form": bool(processed_medication.form),
        "brand_name": bool(processed_medication.brand_name),
        "bar_code": bool(processed_medication.bar_code),
        "lot_number": bool(processed_medication.lot_number),
        "expiration_date": bool(processed_medication.expiration_date),
        "presentation": bool(processed_medication.presentation),
        "country": bool(processed_medication.country)
    }
    
    completed_fields = sum(completeness_summary.values())
    total_fields = len(completeness_summary)
    completeness_percentage = (completed_fields / total_fields) * 100
    
    logger.info(f"📊 Completitud de datos: {completed_fields}/{total_fields} campos ({completeness_percentage:.1f}%)")
    logger.info(f"🏁 Finalización completada - Fuente principal: {final_data_source}")
    
    return {
        "processed_medications": processed_medication,
        "final_data_source": final_data_source,
        "enrichment_confidence": enrichment_confidence,
        "completeness_summary": completeness_summary,
        "completeness_percentage": completeness_percentage,
        "missing_critical_fields": missing_critical_fields,
        "workflow_completed": True
    }


class OCRGatewayGraph(GraphBuilder):
    """Builder para crear un flujo de trabajo con gateway OCR y verificación GTIN"""

    def __init__(self):
        """Inicializa el constructor de flujo con los agentes necesarios"""
        super().__init__()
        self.ocr_gateway = OCRGatewayExtractor()
        self.processor = MedicationProcessor()
        self.extract_page = None

    def init_graph(self) -> None:
        """Inicializa el grafo de estado con el tipo de estado de extracción de medicamentos"""
        self.graph = StateGraph(MedicationExtractionState)
        from .medication_extraction_graph import MedicationExtractionGraph
        extract_page = MedicationExtractionGraph()
        self.extract_page = extract_page.build().compile()

    def add_nodes(self) -> None:
        """Agrega todos los nodos requeridos al grafo"""
        # Nodo de extracción de texto OCR
        self.graph.add_node("extract_text", self.ocr_gateway.extract_text)
        # Nodo de verificación GTIN
        #self.graph.add_node("check_gtin", check_gtin_in_database_v3)
        self.graph.add_node("validate_page", self.extract_page)
        # Nodo de procesamiento de medicamentos
        self.graph.add_node("process_medication_data", self.processor.process_medication_data)
        # Nuevo nodo: Verificar si hay GTIN válido
        self.graph.add_node("check_gtin_validity", check_has_valid_gtin)
        # Nodos de búsqueda condicional
        self.graph.add_node("exact_gtin_search", check_gtin_in_database_v3)
        self.graph.add_node("semantic_search", search_medications_semantic)
        # Nodo de finalización
        self.graph.add_node("finalize_data_enrichment", finalize_data_enrichment)

    def add_edges(self) -> None:
        """Define todos los bordes en el grafo: primero procesamiento, luego verificación GTIN"""
        # Flujo: START -> extract_text -> process_medication_data -> check_gtin -> END
        #self.graph.add_edge(START, "extract_text")
        self.graph.add_conditional_edges(START,
                                         self.extract_pages_content,
                                         ["validate_page"]
                                         )
        self.graph.add_edge("validate_page", "process_medication_data")
        self.graph.add_edge("process_medication_data", "check_gtin_validity")
        self.graph.add_conditional_edges(
            "check_gtin_validity",
            self.route_search_method,
            {
                "exact_gtin_search": "exact_gtin_search",
                "semantic_search": "semantic_search"
            }
        )
        # Ambos nodos de búsqueda van al nodo de finalización
        self.graph.add_edge("exact_gtin_search", "finalize_data_enrichment")
        self.graph.add_edge("semantic_search", "finalize_data_enrichment")
        # El nodo de finalización termina el flujo
        self.graph.add_edge("finalize_data_enrichment", END)

    def conditional_edges(self) -> None:
        """Agrega lógica de enrutamiento condicional (no necesaria para este flujo simple)"""
        pass

    def error_handling(self) -> None:
        """Agrega manejo de errores al grafo (opcional)"""
        # Aquí se podría implementar manejo de errores específicos
        # Por ejemplo, redirigir a nodos de recuperación en caso de errores
        pass

    def route_search_method(self, state: MedicationExtractionState) -> Literal["exact_gtin_search", "semantic_search"]:
        """
        Función de enrutamiento condicional que decide entre búsqueda exacta o semántica.

        Args:
            state: Estado actual del workflow

        Returns:
            Nombre del siguiente nodo a ejecutar
        """
        has_valid_gtin = state.get("gtin_found", False)

        if has_valid_gtin:
            logger.info("Enrutando a búsqueda exacta por GTIN")
            return "exact_gtin_search"
        else:
            logger.info("Enrutando a búsqueda semántica")
            return "semantic_search"

    def extract_pages_content(self, state: MedicationExtractionState) -> list[Send]:
        """Creates Send objects for each PageContent in OverallState['page_contents'] for parallel validation."""

        return [
            Send("validate_page", {"file": file})
            for file in state["files"]
        ]
