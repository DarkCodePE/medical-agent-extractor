from typing import Dict, Any, List, Optional, TypedDict

from fastapi import UploadFile
from typing_extensions import NotRequired


class MedicationDetails(TypedDict):
    """Medication details extracted from the inventory image"""
    medication_code: str
    lot_number: str
    medication_name: str
    description: str


class MedicationStructuredContent(TypedDict):
    """Structured content from a medication inventory image"""
    raw_text: str
    medication_info: MedicationDetails


class MedicationExtractionState(TypedDict):
    """State for medication extraction workflow"""
    files: List[UploadFile]
    file_names: List[str]
    extracted_texts: List[str]
    structured_contents: List[Dict[str, Any]]
    processed_medications: MedicationStructuredContent
    error: str
    ocr_provider:str