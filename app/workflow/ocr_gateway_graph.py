# app/workflow/ocr_gateway_graph.py

from typing import Dict, Any, Literal
from langgraph.graph import StateGraph
from langgraph.constants import START, END
import logging

from app.agent.medication_processor import MedicationProcessor
from app.agent.ocr_gateway_extractor import OCRGatewayExtractor
from app.tools.check_gtin_in_database import check_gtin_in_database, check_gtin_in_database_v3

from app.workflow.builder.base import GraphBuilder
from app.agent.medication_extraction_state import MedicationExtractionState

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


class OCRGatewayGraph(GraphBuilder):
    """Builder para crear un flujo de trabajo con gateway OCR y verificación GTIN"""

    def __init__(self):
        """Inicializa el constructor de flujo con los agentes necesarios"""
        super().__init__()
        self.ocr_gateway = OCRGatewayExtractor()
        self.processor = MedicationProcessor()

    def init_graph(self) -> None:
        """Inicializa el grafo de estado con el tipo de estado de extracción de medicamentos"""
        self.graph = StateGraph(MedicationExtractionState)

    def add_nodes(self) -> None:
        """Agrega todos los nodos requeridos al grafo"""
        # Nodo de extracción de texto OCR
        self.graph.add_node("extract_text", self.ocr_gateway.extract_text)
        # Nodo de verificación GTIN
        self.graph.add_node("check_gtin", check_gtin_in_database_v3)
        # Nodo de procesamiento de medicamentos
        self.graph.add_node("process_medication_data", self.processor.process_medication_data)

    def add_edges(self) -> None:
        """Define todos los bordes en el grafo: primero procesamiento, luego verificación GTIN"""
        # Flujo: START -> extract_text -> process_medication_data -> check_gtin -> END
        self.graph.add_edge(START, "extract_text")
        self.graph.add_edge("extract_text", "process_medication_data")
        self.graph.add_edge("process_medication_data", "check_gtin")
        self.graph.add_edge("check_gtin", END)

    def conditional_edges(self) -> None:
        """Agrega lógica de enrutamiento condicional (no necesaria para este flujo simple)"""
        pass

    def error_handling(self) -> None:
        """Agrega manejo de errores al grafo (opcional)"""
        # Aquí se podría implementar manejo de errores específicos
        # Por ejemplo, redirigir a nodos de recuperación en caso de errores
        pass