# app/workflow/director.py

from typing import Dict, Any
from langgraph.graph import StateGraph
import logging

# Import graph builders
# from app.workflow.document_extraction_graph import DocumentExtractionGraph
from app.workflow.medication_extraction_graph import MedicationExtractionGraph

logger = logging.getLogger(__name__)


class GraphDirector:
    """
    Director class that orchestrates graph building and provides access to different workflows
    """

    # @staticmethod
    # def document_extraction() -> StateGraph:
    #     """
    #     Build and return the document extraction workflow graph
    #
    #     Returns:
    #         Compiled document extraction workflow
    #     """
    #     logger.info("Building document extraction workflow")
    #     builder = DocumentExtractionGraph()
    #     builder.build()
    #     return builder.get_graph().compile()

    @staticmethod
    def medication_extraction() -> StateGraph:
        """
        Build and return the medication extraction workflow graph

        Returns:
            Compiled medication extraction workflow
        """
        logger.info("Building medication extraction workflow")
        builder = MedicationExtractionGraph()
        builder.build()
        return builder.get_graph().compile()