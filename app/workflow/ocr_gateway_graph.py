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
        self.graph.add_edge("exact_gtin_search", END)
        self.graph.add_edge("semantic_search", END)

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
