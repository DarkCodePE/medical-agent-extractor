from typing import Dict, Any, List, Optional, TypedDict, Annotated, Union
from fastapi import UploadFile
from typing_extensions import NotRequired
import operator


class MedicationDetails(TypedDict):
    """Medication details extracted from the inventory image"""
    bar_code: str
    medication_name: str
    description: str
    common_denomination: str
    concentration: str
    form: str
    form_simple: str
    brand_name: str
    country: str
    presentation: str
    fractions: str
    product_type: str
    lot_number: str
    expiration_date: str


class MedicationStructuredContent(TypedDict):
    """Structured content from a medication inventory image"""
    raw_text: str
    medication_info: MedicationDetails


class DatabaseInfo(TypedDict):
    """Database information from GTIN lookup"""
    gtin_code: str
    medication_name: str
    common_denomination: str
    concentration: str
    form: str
    form_simple: str
    brand_name: str
    country: str
    presentation: str
    fractions: str
    product_type: str
    lot_number: str
    expiration_date: str


class PageExtractionState(TypedDict):
    file: UploadFile
    extracted_texts: List[str]


class MedicationExtractionState(TypedDict):
    """State for medication extraction workflow"""
    files: List[UploadFile]
    file_names: List[str]
    #extracted_texts: List[str]
    extracted_texts: Annotated[List[str], operator.add]
    structured_contents: List[Dict[str, Any]]
    processed_medications: MedicationDetails  # Solo datos extraídos del OCR
    processed_enrichment_medications: NotRequired[MedicationDetails]  # Datos finales enriquecidos
    error: str
    ocr_provider: str
    gtin_found: NotRequired[bool]
    database_info: NotRequired[DatabaseInfo]
    semantic_search_completed: NotRequired[bool]
    semantic_results: NotRequired[List[Dict[str, Any]]]
    semantic_match_found: NotRequired[bool]
    semantic_best_match: NotRequired[Dict[str, Any]]
    semantic_search_query: NotRequired[str]
    enrichment_applied: NotRequired[bool]
    # Campos agregados para el nodo de finalización
    final_data_source: NotRequired[str]
    enrichment_confidence: NotRequired[float]
    completeness_summary: NotRequired[Dict[str, bool]]
    completeness_percentage: NotRequired[float]
    missing_critical_fields: NotRequired[List[str]]
    workflow_completed: NotRequired[bool]
    # Campos agregados para búsqueda semántica optimizada
    search_strategy: NotRequired[str]
    search_confidence: NotRequired[float]
    confidence_threshold_used: NotRequired[float]
    search_stats: NotRequired[Dict[str, Any]]
    # Campos de trazabilidad del enriquecimiento
    enrichment_source_fields: NotRequired[Dict[str, str]]  # Qué campo vino de qué fuente
    ocr_vs_enriched_comparison: NotRequired[Dict[str, Any]]  # Comparación entre OCR y enriquecido
