from typing import Dict, Any, List, Optional, TypedDict

from fastapi import UploadFile
from typing_extensions import NotRequired


class MedicationDetails(TypedDict):
    """Medication details extracted from the image"""
    medication_name: str
    active_ingredients: List[str]
    dosage: str
    manufacturer: str
    expiration_date: NotRequired[str]
    batch_number: NotRequired[str]
    instructions: NotRequired[str]
    barcode: NotRequired[str]


class MedicationStructuredContent(TypedDict):
    """Structured content from a medication image"""
    raw_text: str
    medication_info: MedicationDetails


class MedicationExtractionState(TypedDict):
    """State for medication extraction workflow"""
    files: List[UploadFile]
    file_names: NotRequired[List[str]]
    extracted_texts: NotRequired[List[str]]
    structured_contents: NotRequired[List[Dict[str, Any]]]
    error: NotRequired[str]