import logging
import json
from typing import Dict, Any, List

from langchain_core.messages import SystemMessage, HumanMessage

from app.agent.medication_extraction_state import MedicationExtractionState, MedicationStructuredContent
from app.config.config import get_settings
from app.providers.llm_manager import LLMConfig, LLMManager, LLMType

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Define prompt templates for medication extraction
MEDICATION_EXTRACTION_PROMPT = """
You are an AI assistant specializing in extracting structured information from medication packaging and prescriptions.

**Input Data:**
{extracted_text}

Analyze the input text from the medication packaging or prescription and extract the following details:

1. **Medication Name**: The primary name/brand of the medication
2. **Active Ingredients**: List all active ingredients with their amounts
3. **Dosage**: The dosage information (strength, frequency, etc.)
4. **Manufacturer**: The company that produces the medication
5. **Expiration Date**: When the medication expires (if available)
6. **Batch Number**: Lot or batch identification (if available)
7. **Instructions**: Usage directions and important warnings
8. **Barcode**: Any barcode number that appears in the text

If any information is not present in the text, indicate it as null.
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
        self.primary_llm = self.llm_manager.get_llm(LLMType.GPT_4O_MINI)

    async def process_medication_data(self, state: MedicationExtractionState) -> Dict[str, Any]:
        """
        Process extracted text to structure medication information.

        Args:
            state: Current workflow state with extracted texts

        Returns:
            Updated state with processed medication data
        """
        extracted_texts = state.get("extracted_texts", [])
        if not extracted_texts:
            return {"error": "No extracted texts available for processing"}

        processed_results = []

        for idx, text in enumerate(extracted_texts):
            try:
                # Structure the medication data with LLM
                structured_llm = self.primary_llm.with_structured_output(MedicationStructuredContent)
                system_instructions = MEDICATION_EXTRACTION_PROMPT.format(
                    extracted_text=text,
                )

                result = structured_llm.invoke([
                    SystemMessage(content=system_instructions),
                    HumanMessage(
                        content="Extract the key medication information from this OCR text and return it in a structured format.")
                ])

                processed_results.append(result)
                logger.info(f"Successfully processed medication data for image {idx + 1}")

            except Exception as e:
                logger.error(f"Error processing medication data for image {idx + 1}: {str(e)}")
                processed_results.append({
                    "error": str(e),
                    "raw_text": text
                })

        return {"processed_medications": processed_results}