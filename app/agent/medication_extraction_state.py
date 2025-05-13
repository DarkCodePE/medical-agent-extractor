from typing import Dict, Any, List, Optional, TypedDict

from fastapi import UploadFile
from typing_extensions import NotRequired


class MedicationDetails(TypedDict):
    """Medication details extracted from the inventory image"""
    bar_code: str
    lot_number: str
    medication_name: str
    description: str
    expiration_date:str
    quantity: str
    price:str

class MedicationStructuredContent(TypedDict):
    """Structured content from a medication inventory image"""
    raw_text: str
    medication_info: MedicationDetails

class DatabaseInfo(TypedDict):
    """Database information from GTIN lookup"""
    gtin_code: str
    medication_name: str
    active_ingredient: str
    concentration: str
    form: str
    form_simple: str
    brand: str
    country: str
    presentation: str
    product_type: str
    lot_number: NotRequired[str]
    expiration_date: NotRequired[str]

class MedicationExtractionState(TypedDict):
    """State for medication extraction workflow"""
    files: List[UploadFile]
    file_names: List[str]
    extracted_texts: List[str]
    structured_contents: List[Dict[str, Any]]
    processed_medications: MedicationDetails
    error: str
    ocr_provider:str
    gtin_found: NotRequired[bool]
    database_info: NotRequired[DatabaseInfo]