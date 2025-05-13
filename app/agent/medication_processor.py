import logging
import json
from typing import Dict, Any, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from app.agent.medication_extraction_state import MedicationExtractionState, MedicationStructuredContent, \
    MedicationDetails
from app.config.config import get_settings
from app.providers.llm_manager import LLMConfig, LLMManager, LLMType

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Define Pydantic model for structured output
class MedicationDetailsModel(BaseModel):
    """Medication details extracted from the image"""
    # Basic fields from OCR
    bar_code: Optional[str] = Field(None, description="The GTIN/barcode of the medication")
    lot_number: Optional[str] = Field(None, description="The lot or batch number of the medication")
    expiration_date: Optional[str] = Field(None, description="When the medication expires")

    # Database-aligned fields
    name: str = Field(..., description="The brand name of the medication (e.g., LAGRICEL OFTENO)")
    common_denomination: Optional[str] = Field(None, description="The active ingredient (e.g., HIALURONATO SODICO)")
    concentration: Optional[str] = Field(None, description="The concentration of active ingredient (e.g., 4 mg/mL)")
    form: Optional[str] = Field(None, description="The pharmaceutical form (e.g., SOLUCION OFTALMICA)")
    form_simple: Optional[str] = Field(None, description="The simple form (e.g., COLIRIO)")
    brand_name: Optional[str] = Field(None, description="The manufacturer/brand name (e.g., LABOFTA)")
    country: Optional[str] = Field(None, description="Country of origin")
    presentation: Optional[str] = Field(None, description="How the product is packaged (e.g., CAJA UNIDOSIS)")
    fractions: Optional[str] = Field(None, description="The number of primary, indivisible units that make up the retail product being described.")
    # Additional fields
    quantity: Optional[str] = Field(None, description="Available quantity or stock")
    price: Optional[str] = Field(None, description="The price of the medication")

# Define prompt templates for medication extraction
MEDICATION_EXTRACTION_PROMPT = """
You are an AI assistant specializing in extracting structured information from medication inventory tables and medication packaging.

**Input Data:**
{extracted_text}

Analyze the input text and extract the following details, paying special attention to format the data in a way that matches database records:

1. **Bar Code/GTIN**: The identification code of the medication (e.g., "7 36085 28000 5"). Clean to remove spaces when possible.

2. **Lot Number**: The production batch number (look for "Lote:", "Lot:", "Batch:", etc.)

3. **Expiration Date**: When the medication expires (look for "Cad:", "Exp:", "Expiry:", etc.)

4. **Name**: The complete brand name as it appears on the package (e.g., "LAGRICEL OFTENO", "PARACETAMOL FORTE")

5. **Common Denomination**: The active ingredient/generic name (e.g., "HIALURONATO SODICO", "PARACETAMOL")

6. **Concentration**: The dosage strength with units (e.g., "4 mg/mL", "500 mg")

7. **Form**: The pharmaceutical form in detail (e.g., "SOLUCION OFTALMICA", "TABLETA RECUBIERTA")

8. **Form Simple**: The simplified form type (e.g., "COLIRIO", "TABLETA", "CAPSULA", "JARABE")

9. **Brand Name**: The manufacturer or brand company name (e.g., "LABOFTA", "BAYER")

10. **Country**: Country of origin or manufacture if mentioned

11. **Presentation**: How the product is packaged (e.g., "CAJA UNIDOSIS", "FRASCO x 120 mL")

12. **Quantity**: Available quantity or inventory count if present

13. **Price**: The price of the medication if present

For each field, extract exactly as shown in the text or make a best guess based on context. If information isn't present, leave the field empty.

For active ingredients, clearly separate the ingredient name (common_denomination) from its concentration.
"""


MEDICATION_EXTRACTION_PROMPT_V2 = """
Extract structured information from medication inventory tables and medication packaging.

**Input Data:**
{extracted_text}

Carefully analyze the input text and extract the following details, ensuring the format matches database records:

- **Bar Code/GTIN**: Extract and clean the identification code of the medication, removing spaces if possible (e.g., "736085280005").

- **Lot Number**: Find the production batch number using indicators like "Lote:", "Lot:", "Batch:", etc.

- **Expiration Date**: Use terms like "Cad:", "Exp:", "Expiry:" to find when the medication expires.

- **Name**: The complete brand name as presented on the packaging.

- **Common Denomination**: Extract the active ingredient or generic name separately.

- **Concentration**: Identify the dosage strength and accompanying units.

- **Form**: (Detailed Pharmaceutical Form) Extract the specific, technical, or official description of the pharmaceutical dosage form. This often combines the physical state and intended route/area of administration.

- **Form Simple**:  (Simplified or Common Form Type): Extract a more common, user-friendly, or broader categorical term for the dosage form. This may be a direct common name, a general application type, or a simplification of the form.

- **Brand Name**: State the manufacturer or brand company name.

- **Country**:  The primary country of manufacture or origin. If multiple countries are listed (e.g., for distribution in Bolivia, Ecuador, Peru, etc.), prioritize the country where the product is "Elaborado y distribuido en..." (e.g., "Chile" if "Elaborado y distribuido en Chile por Laboratorios SAVAL S.A.").

- **Presentation**: A brief description of how the product is packaged or its physical form/container if not covered by form. Examples: "Frasco gotario" (dropper bottle), "Caja con 10 ampollas", "Blister x 20 comprimidos". Infer from terms like "punta del gotario" (dropper tip) or "frasco" (bottle).

 **`fractions`**: The number of primary, indivisible units that make up the retail product being described.

- **Price**: List the price if it is mentioned.

If specific information isn’t present, leave the field empty. Distinguish between the active ingredient and its concentration
"""

class MedicationProcessor:
    """
    Agent for processing medication information from prescription images.
    Handles structuring and normalizing data extracted from OCR.
    """

    def __init__(self, settings=None):
        """
        Initialize MedicationProcessor with settings.
        Args:
            settings: Optional application settings. If None, will load default settings.
        """
        self.settings = settings or get_settings()
        # Initialize LLM manager with specific configuration
        llm_config = LLMConfig(
            temperature=0.0,  # Use deterministic output for structured extraction
            streaming=False,
        )
        self.llm_manager = LLMManager(llm_config)
        # Get the primary LLM for processing
        self.primary_llm = self.llm_manager.get_llm(LLMType.GEMINI)

    async def process_medication_data(self, state: MedicationExtractionState) -> MedicationExtractionState:
        """
        Process extracted text to structure medication information.

        Args:
            state: Current workflow state with extracted texts

        Returns:
            Updated state with processed medication data
        """
        extracted_texts = state.get("extracted_texts", [])
        logger.info(f"Extracted texts: {extracted_texts}")

        structured_llm = self.primary_llm.with_structured_output(MedicationDetailsModel)
        logger.info("Using structured_llm")
        system_instructions = MEDICATION_EXTRACTION_PROMPT_V2.format(
            extracted_text=extracted_texts,
        )
        result = structured_llm.invoke([
            SystemMessage(content=system_instructions),
            HumanMessage(
                content="Extract the key medication information from this OCR text and return it in a structured format.")
        ])
        logger.info(f"Result structured_llm: {result}")
        state["processed_medications"] = result
        return state