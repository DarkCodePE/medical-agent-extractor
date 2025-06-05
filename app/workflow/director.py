# app/workflow/director.py

from typing import Dict, Any
from langgraph.graph import StateGraph
import logging

# Import graph builders
# from app.workflow.document_extraction_graph import DocumentExtractionGraph
from app.workflow.medication_extraction_graph import MedicationExtractionGraph
from app.workflow.ocr_gateway_graph import OCRGatewayGraph

logger = logging.getLogger(__name__)


class GraphDirector:
    """
    Director class that orchestrates graph building and provides access to different workflows
    """

    @staticmethod
    def medication_extraction() -> StateGraph:
        """
        Build and return the medication extraction workflow graph

        Returns:
            Compiled medication extraction workflow
        """
        logger.info("Building medication extraction workflow")
        builder = MedicationExtractionGraph()
        return builder.build()

    @staticmethod
    def ocr_extraction() -> StateGraph:
        """
        Build and return the OCR gateway extraction workflow graph

        Returns:
            Compiled OCR extraction workflow
        """
        logger.info("Building OCR gateway extraction workflow")
        builder = OCRGatewayGraph()
        return builder.build()
