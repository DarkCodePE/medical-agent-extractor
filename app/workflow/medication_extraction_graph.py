# app/workflow/medication_extraction_graph.py

from typing import Dict, Any
from langgraph.graph import StateGraph
from langgraph.constants import START, END
import logging

from app.agent.extraction_agent import ExtractorAgent
from app.agent.medication_extractor import MedicationExtractorAgent
from app.agent.medication_processor import MedicationProcessor
from app.agent.medication_extraction_state import MedicationExtractionState, PageExtractionState
from app.workflow.builder.base import GraphBuilder

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MedicationExtractionGraph(GraphBuilder):
    """Builder for creating medication extraction workflow graph"""

    def __init__(self):
        """Initialize workflow builder with necessary agents"""
        super().__init__()
        self.extractor = ExtractorAgent()

    def init_graph(self) -> None:
        """Initialize the state graph with the medication extraction state type"""
        self.graph = StateGraph(PageExtractionState)

    def add_nodes(self) -> None:
        """Add all required nodes to the graph"""
        # Add the medication extraction node
        self.graph.add_node("extract_medication_info", self.extractor.validate_page)

    def add_edges(self) -> None:
        """Define all edges in the graph"""
        # Start -> extract_medication_info
        self.graph.add_edge(START, "extract_medication_info")
        self.graph.add_edge("extract_medication_info", END)
    