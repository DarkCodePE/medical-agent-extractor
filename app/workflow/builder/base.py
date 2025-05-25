# app/workflow/builder/base.py

from abc import ABC, abstractmethod
from langgraph.graph import StateGraph
import logging

logger = logging.getLogger(__name__)


class GraphBuilder(ABC):
    """
    Abstract base class for graph builders that defines the building process
    """

    def __init__(self):
        """Initialize the graph builder"""
        self.graph = None

    @abstractmethod
    def init_graph(self) -> None:
        """Initialize the graph with appropriate state type"""
        pass

    @abstractmethod
    def add_nodes(self) -> None:
        """Add all required nodes to the graph"""
        pass

    @abstractmethod
    def add_edges(self) -> None:
        """Define all edges in the graph"""
        pass

    def conditional_edges(self) -> None:
        """Add any conditional routing logic (optional)"""
        pass

    def error_handling(self) -> None:
        """Add error handling to the graph (optional)"""
        pass

    def build(self) -> StateGraph:
        """
        Build the complete graph following the template method pattern
        """
        logger.info("Building graph")
        self.init_graph()
        self.add_nodes()
        self.add_edges()
        self.conditional_edges()
        self.error_handling()
        logger.info("Graph built successfully")
        return self.get_graph()

    def get_graph(self) -> StateGraph:
        """
        Get the built graph

        Returns:
            The complete state graph
        """
        if self.graph is None:
            raise ValueError("Graph has not been built yet. Call build() first.")
        return self.graph
