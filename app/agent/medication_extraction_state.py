import operator
from typing import Dict, Any, List, Optional, TypedDict

from fastapi import UploadFile
from typing_extensions import NotRequired, Annotated


class MedicationDetails(TypedDict):
    """Medication details extracted from the inventory image"""
    medication_code: NotRequired[str]
    lot_number: NotRequired[str]
    medication_name: str
    description: str  # Contains active ingredient, form, strength information
    expiration_date: NotRequired[str]
    quantity: NotRequired[int]
    price: NotRequired[float]

    # Parsed from description if available
    active_ingredient: NotRequired[str]
    dosage_form: NotRequired[str]  # e.g., "SOLUCION ORAL", "TABLETA"
    strength: NotRequired[str]  # e.g., "5 mg/5 mL", "0.25 mg"
    manufacturer: NotRequired[str]  # e.g., "MEGA LA", "FARMINDUSTRIA"


class SingleImageProcessingState(TypedDict):
    file: UploadFile # fastapi.UploadFile should already be imported
    ocr_provider: str


class MedicationStructuredContent(TypedDict):
    """Structured content from a medication inventory image"""
    raw_text: str
    medication_info: MedicationDetails


class MedicationExtractionState(TypedDict):
    """State for medication extraction workflow"""
    files: List[UploadFile] # Original list of files to process
    ocr_provider: str       # Choice of OCR provider for the batch

    # Fields to be aggregated from parallel OCR tasks
    file_names: Annotated[List[str], operator.add]
    extracted_texts: Annotated[List[str], operator.add]
    ocr_provider_used: Annotated[List[str], operator.add] # To track which provider was used for each file if it varies

    # Existing downstream fields
    structured_contents: NotRequired[List[Dict[str, Any]]]
    processed_medications: NotRequired[List[MedicationStructuredContent]] # Assuming MedicationStructuredContent is defined in the file
    error: NotRequired[str]