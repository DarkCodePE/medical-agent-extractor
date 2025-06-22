import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from app.agent.medication_extraction_state import MedicationExtractionState, MedicationStructuredContent, \
    MedicationDetails
from app.config.config import get_settings
from app.providers.llm_manager import LLMConfig, LLMManager, LLMType

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def format_expiration_date(raw_date: str) -> Optional[str]:
    """
    Formatea fecha de expiración al formato yyyy-MM-dd.
    
    Soporta varios formatos de entrada:
    - "05-2026" -> "2026-05-01"
    - "12/2025" -> "2025-12-01"
    - "2026-05" -> "2026-05-01"
    - "05/26" -> "2026-05-01" (asume 20XX para años de 2 dígitos)
    - "15/03/2025" -> "2025-03-15"
    - "2025-03-15" -> "2025-03-15" (ya está en formato correcto)
    
    Args:
        raw_date: Fecha en formato crudo extraída por OCR
        
    Returns:
        Fecha formateada en formato yyyy-MM-dd o None si no se puede parsear
    """
    if not raw_date or not isinstance(raw_date, str):
        return None
        
    # Limpiar la fecha removiendo espacios extra
    date_str = raw_date.strip()
    
    try:
        # Patrón 1: MM-YYYY o MM/YYYY (ej: "05-2026", "12/2025")
        pattern1 = r'^(\d{1,2})[-/](\d{4})$'
        match1 = re.match(pattern1, date_str)
        if match1:
            month, year = match1.groups()
            return f"{year}-{month.zfill(2)}-01"
        
        # Patrón 2: YYYY-MM (ej: "2026-05")
        pattern2 = r'^(\d{4})-(\d{1,2})$'
        match2 = re.match(pattern2, date_str)
        if match2:
            year, month = match2.groups()
            return f"{year}-{month.zfill(2)}-01"
            
        # Patrón 3: MM/YY (año de 2 dígitos, ej: "05/26")
        pattern3 = r'^(\d{1,2})/(\d{2})$'
        match3 = re.match(pattern3, date_str)
        if match3:
            month, year_short = match3.groups()
            # Asumir 20XX para años de 2 dígitos
            year = f"20{year_short}"
            return f"{year}-{month.zfill(2)}-01"
            
        # Patrón 4: DD/MM/YYYY o DD-MM-YYYY (ej: "15/03/2025")
        pattern4 = r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$'
        match4 = re.match(pattern4, date_str)
        if match4:
            day, month, year = match4.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
        # Patrón 5: YYYY-MM-DD (ya está en formato correcto)
        pattern5 = r'^(\d{4})-(\d{1,2})-(\d{1,2})$'
        match5 = re.match(pattern5, date_str)
        if match5:
            year, month, day = match5.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
        # Patrón 6: Formatos con texto (ej: "May 2026", "Dic 2025")
        pattern6 = r'^([A-Za-z]{3,})\s*(\d{4})$'
        match6 = re.match(pattern6, date_str.lower())
        if match6:
            month_text, year = match6.groups()
            # Mapeo de meses en español e inglés
            month_mapping = {
                'jan': '01', 'ene': '01', 'enero': '01', 'january': '01',
                'feb': '02', 'febrero': '02', 'february': '02',
                'mar': '03', 'marzo': '03', 'march': '03',
                'apr': '04', 'abr': '04', 'abril': '04', 'april': '04',
                'may': '05', 'mayo': '05',
                'jun': '06', 'junio': '06', 'june': '06',
                'jul': '07', 'julio': '07', 'july': '07',
                'aug': '08', 'ago': '08', 'agosto': '08', 'august': '08',
                'sep': '09', 'sept': '09', 'septiembre': '09', 'september': '09',
                'oct': '10', 'octubre': '10', 'october': '10',
                'nov': '11', 'noviembre': '11', 'november': '11',
                'dec': '12', 'dic': '12', 'diciembre': '12', 'december': '12'
            }
            
            month_num = month_mapping.get(month_text[:3])
            if month_num:
                return f"{year}-{month_num}-01"
        
        logger.warning(f"No se pudo parsear fecha de expiración: '{raw_date}'")
        return None
        
    except Exception as e:
        logger.error(f"Error parseando fecha de expiración '{raw_date}': {str(e)}")
        return None

# Define Pydantic model for structured output
class MedicationDetailsModel(BaseModel):
    """Medication details extracted from the image"""
    # Basic fields from OCR
    bar_code: Optional[str] = Field(None, description="The GTIN/barcode of the medication")
    lot_number: Optional[str] = Field(None, description="The lot or batch number of the medication")
    expiration_date: Optional[str] = Field(None, description="When the medication expires")
    database_id: Optional[int] = Field(None, description="Database ID when found in GTIN database")

    # Database-aligned fields
    product_type: Optional[str] = Field(None, description="The product type of the medication (e.g., ALIMENTO,COSMETICO,DISPOSITIVO MEDICO, EQUIPO MEDICO, EQUIPO PROTECCION PERSONAL,INSUMO MEDICO, OTROS NO FARMACEUTICOS, PRODUCTO FARMACEUTICO, PRODUCTO SANITARIO/HIGIENE PERSONAL)")
    medication_name: str = Field(..., description="The brand name of the medication (e.g., LAGRICEL OFTENO)")
    common_denomination: Optional[str] = Field(None, description="The active ingredient (e.g., HIALURONATO SODICO)")
    concentration: Optional[str] = Field(None, description="The concentration of active ingredient (e.g., 4 mg/mL)")
    form: Optional[str] = Field(None, description="The pharmaceutical form (e.g., SOLUCION OFTALMICA)")
    form_simple: Optional[str] = Field(None, description="The simple form (e.g., COLIRIO)")
    brand_name: Optional[str] = Field(None, description="The manufacturer/brand name (e.g., LABOFTA)")
    country: Optional[str] = Field(None, description="Country of origin")
    presentation: Optional[str] = Field(None, description="How the product is packaged (e.g., CAJA UNIDOSIS)")
    fractions: Optional[str] = Field(None, description="The number of primary, indivisible units that make up the retail product being described.")


# Define prompt templates for medication extraction
MEDICATION_EXTRACTION_PROMPT_V2 = """
Extract structured information from medication inventory tables and medication packaging.

**Input Data:**
{extracted_text}

Carefully analyze the input text and extract the following details, ensuring the format matches database records:

- **Bar Code/GTIN**: Extract and clean the identification code of the medication, removing spaces if possible (e.g., "736085280005").

- **Lot Number**: Find the production batch number using indicators like "Lote:", "Lot:", "Batch:", "No. Lote", "Lab. N°", "LS", or any alphanumeric code that appears to be a batch/lot identifier (typically combinations of letters and numbers like "LT240815", "ABC123", "LS339", etc.). Look for patterns near packaging information, manufacturing details, or laboratory references. Be flexible with format detection.

- **Expiration Date**: Look for expiration dates using terms like "Cad:", "Exp:", "Expiry:", "Vence:", "Vencimiento:", "Fecha de vencimiento:", "Best by", "Valid until", or any date patterns (MM/YYYY, DD/MM/YYYY, DD-MM-YYYY, etc.). Also search for dates that appear to be future dates which could indicate expiration. Check areas near storage instructions or regulatory information.

- **Medication Name**: The complete brand name as presented on the packaging.

- **Common Denomination**: Extract the active ingredient or generic name separately.

- **Concentration**: Identify the dosage strength and accompanying units.

- **Form**: (Detailed Pharmaceutical Form) Extract the specific, technical, or official description of the pharmaceutical dosage form. This often combines the physical state and intended route/area of administration.

- **Form Simple**:  (Simplified or Common Form Type): Extract a more common, user-friendly, or broader categorical term for the dosage form. This may be a direct common name, a general application type, or a simplification of the form.

- **Brand Name**: State the manufacturer or brand company name.

- **Country**:  The primary country of manufacture or origin. If multiple countries are listed (e.g., for distribution in Bolivia, Ecuador, Peru, etc.), prioritize the country where the product is "Elaborado y distribuido en..." (e.g., "Chile" if "Elaborado y distribuido en Chile por Laboratorios SAVAL S.A.").

- **Presentation**: A brief description of how the product is packaged or its physical form/container if not covered by form. Examples: "Frasco gotario" (dropper bottle), "Caja con 10 ampollas", "Blister x 20 comprimidos". Infer from terms like "punta del gotario" (dropper tip) or "frasco" (bottle).

 **`fractions`**: The number of primary, indivisible units that make up the retail product being described.

- **Product type**: The product type of the medication (e.g., ALIMENTO,COSMETICO,DISPOSITIVO MEDICO, EQUIPO MEDICO, EQUIPO PROTECCION PERSONAL,INSUMO MEDICO, OTROS NO FARMACEUTICOS, PRODUCTO FARMACEUTICO, PRODUCTO SANITARIO/HIGIENE PERSONAL)

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
        
        # Formatear fecha de expiración si existe
        if result and hasattr(result, 'expiration_date') and result.expiration_date:
            original_date = result.expiration_date
            formatted_date = format_expiration_date(original_date)
            if formatted_date:
                result.expiration_date = formatted_date
                logger.info(f"📅 Fecha de expiración formateada: '{original_date}' → '{formatted_date}'")
            else:
                logger.warning(f"⚠️ No se pudo formatear fecha de expiración: '{original_date}'")
        
        state["processed_medications"] = result
        return state