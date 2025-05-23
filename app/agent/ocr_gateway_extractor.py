import logging
from enum import Enum
from typing import Dict, Any, List, Optional

from fastapi import UploadFile

from app.agent.medication_extraction_state import MedicationExtractionState, SingleImageProcessingState
# Assuming these clients are defined elsewhere and provide an async 'extract_text_from_image_bytes' method
# from app.utils.mistral_client import MistralClient # Placeholder
# from app.utils.gemini_client import GeminiClient # Placeholder

# Placeholder implementations for MistralClient and GeminiClient
# In a real scenario, these would be imported from their respective modules.
class MistralClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        if not self.api_key:
            logger.warning("Mistral API key not provided.")

    async def extract_text_from_image_bytes(self, image_bytes: bytes) -> str:
        logger.info("Mock MistralClient: Simulating text extraction.")
        # Simulate API call delay and response
        # await asyncio.sleep(1) 
        return "Mistral extracted text from image"

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        if not self.api_key:
            logger.warning("Gemini API key not provided.")

    async def extract_text_from_image_bytes(self, image_bytes: bytes) -> str:
        logger.info("Mock GeminiClient: Simulating text extraction.")
        # Simulate API call delay and response
        # await asyncio.sleep(1)
        return "Gemini extracted text from image"

logger = logging.getLogger(__name__)

class OCRProvider(Enum):
    MISTRAL = "mistral"
    GEMINI = "gemini"
    # Future providers can be added here

class OCRGatewayExtractor:
    def __init__(self, mistral_api_key: Optional[str] = None, gemini_api_key: Optional[str] = None):
        self.mistral_client = MistralClient(api_key=mistral_api_key)
        self.gemini_client = GeminiClient(api_key=gemini_api_key)
        
        self.available_providers: List[OCRProvider] = []
        if mistral_api_key:
            self.available_providers.append(OCRProvider.MISTRAL)
        if gemini_api_key:
            self.available_providers.append(OCRProvider.GEMINI)

        if not self.available_providers:
            logger.warning("No OCR providers configured with API keys. OCR functionality will be limited.")
        else:
            logger.info(f"Available OCR providers: {[p.value for p in self.available_providers]}")

    async def _process_with_mistral(self, file: UploadFile) -> str:
        logger.info(f"Processing {file.filename} with Mistral.")
        image_bytes = await file.read()
        await file.seek(0) # Reset file pointer if it needs to be read again
        return await self.mistral_client.extract_text_from_image_bytes(image_bytes)

    async def _process_with_gemini(self, file: UploadFile) -> str:
        logger.info(f"Processing {file.filename} with Gemini.")
        image_bytes = await file.read()
        await file.seek(0) # Reset file pointer if it needs to be read again
        return await self.gemini_client.extract_text_from_image_bytes(image_bytes)

    async def extract_text(self, state: MedicationExtractionState) -> Dict[str, Any]:
        """
        Original method to extract text from a list of files,
        now primarily for orchestrating or if batch processing is different.
        This method might be deprecated or refactored if all processing moves to map-reduce.
        """
        files = state['files']
        # For simplicity, this example processes only the first file if multiple are passed
        # and uses the first available provider.
        # A real implementation would iterate or handle multiple files/providers as needed.
        if not files:
            logger.warning("No files provided for OCR extraction.")
            return {"extracted_texts": ["Error: No files provided."]}

        file_to_process = files[0] # Example: process first file
        
        # Provider selection logic (simplified for this example)
        provider = None
        if self.available_providers:
            provider = self.available_providers[0] # Example: use first available
        
        if not provider:
            logger.error("No OCR providers available for extraction.")
            return {"extracted_texts": [f"Error: No OCR providers available for {file_to_process.filename}."]}

        logger.info(f"Extracting text from {file_to_process.filename} using {provider.value} (original method).")
        
        extracted_text_content = ""
        try:
            if provider == OCRProvider.MISTRAL:
                extracted_text_content = await self._process_with_mistral(file_to_process)
            elif provider == OCRProvider.GEMINI:
                extracted_text_content = await self._process_with_gemini(file_to_process)
            else:
                logger.error(f"Unsupported provider selected: {provider.value}")
                extracted_text_content = f"Error: Unsupported provider {provider.value}"
        except Exception as e:
            logger.error(f"Exception during text extraction for {file_to_process.filename} with {provider.value}: {str(e)}")
            extracted_text_content = f"Error processing file {file_to_process.filename}: {str(e)}"
        
        return {"extracted_texts": [extracted_text_content]} # Returning a list to be consistent

    async def extract_single_image_text(self, state: SingleImageProcessingState) -> Dict[str, Any]:
        """
        Extract text from a single image using the specified OCR provider.
        This method is designed to be used in a map operation.
        """
        file_to_process = state['file']
        logger.info(f"Starting single image OCR text extraction for: {file_to_process.filename}")
        
        provider_name = state.get("ocr_provider", self.available_providers[0].value if self.available_providers else None)
        
        provider = None
        if provider_name:
            try:
                provider = OCRProvider(provider_name.lower())
            except ValueError:
                logger.warning(f"Invalid provider specified in SingleImageProcessingState: {provider_name}. Using default.")
                if self.available_providers:
                    provider = self.available_providers[0]
        elif self.available_providers:
            provider = self.available_providers[0]

        if not provider or provider not in self.available_providers:
            logger.error(f"OCR Provider {provider_name or 'not specified'} is not available or configured. Available: {[p.value for p in self.available_providers]}")
            return {
                "extracted_texts": [f"Error: OCR Provider {provider_name or 'not specified'} not available."],
                "file_names": [file_to_process.filename],
                "ocr_provider_used": ["error"] 
            }

        logger.info(f"Using OCR provider: {provider.value} for single file: {file_to_process.filename}")

        extracted_text_content = ""
        try:
            if provider == OCRProvider.MISTRAL:
                extracted_text_content = await self._process_with_mistral(file_to_process)
            elif provider == OCRProvider.GEMINI: 
                extracted_text_content = await self._process_with_gemini(file_to_process)
            else:
                logger.error(f"Unsupported provider selected: {provider.value}")
                extracted_text_content = f"Error: Unsupported provider {provider.value}"
        except Exception as e:
            logger.error(f"Exception during single image processing for {file_to_process.filename} with {provider.value}: {str(e)}")
            extracted_text_content = f"Error processing file {file_to_process.filename}: {str(e)}"

        logger.info(f"Successfully extracted text from {file_to_process.filename} using {provider.value}")

        return {
            "extracted_texts": [extracted_text_content], 
            "file_names": [file_to_process.filename],    
            "ocr_provider_used": [provider.value]        
        }
