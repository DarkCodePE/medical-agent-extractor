from typing import Dict, Any, Optional, List
from pathlib import Path
import logging
import base64
from io import BytesIO

from fastapi import UploadFile
from mistralai import Mistral, ImageURLChunk, TextChunk
from langchain_core.messages import SystemMessage, HumanMessage
import os
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class MedicationExtractorAgent:
    """
    Agent for extracting medication information from prescription images using Mistral OCR.
    Handles image extraction, text processing, and content structuring.
    """

    def __init__(self):
        """Initialize MedicationExtractorAgent with Mistral client"""
        self.mistral_api_key = os.getenv("MISTRAL_API_KEY")
        if not self.mistral_api_key:
            raise ValueError("MISTRAL_API_KEY environment variable is required")

        self.client = Mistral(api_key=self.mistral_api_key)
        logger.info("MedicationExtractorAgent initialized with Mistral API")

    async def extract_medication_info(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main extraction function - processes medication images using Mistral OCR and extracts content.

        Args:
            state: Current state dictionary containing file(s)

        Returns:
            Updated state with extracted text and structured content
        """
        logger.info("Starting medication image extraction process")
        files = state.get("files", [])

        if not files:
            logger.warning("No files provided for extraction")
            return {"error": "No files provided"}

        all_extracted_texts = []
        all_structured_contents = []
        file_names = []

        # Process each image file
        for file in files:
            # Extract text from image using Mistral OCR
            extracted_text = await self._process_image_with_mistral_ocr(file)
            all_extracted_texts.append(extracted_text)

            # Structure the extracted content
            structured_content = await self._structure_medication_content(extracted_text)
            all_structured_contents.append(structured_content)

            file_names.append(file.filename)

        logger.info(f"Successfully processed {len(files)} medication images")

        # Return updated state
        return {
            "extracted_texts": all_extracted_texts,
            "structured_contents": all_structured_contents,
            "file_names": file_names,
        }

    async def _process_image_with_mistral_ocr(self, file: UploadFile) -> str:
        """Process image with Mistral OCR API."""
        logger.info(f"Processing image with Mistral OCR: {file.filename}")

        # Reset file position to beginning
        await file.seek(0)
        image_content = await file.read()

        try:
            # Encode image as base64 for Mistral API
            encoded = base64.b64encode(image_content).decode()
            base64_data_url = f"data:image/jpeg;base64,{encoded}"

            # Process image with OCR
            image_response = self.client.ocr.process(
                document=ImageURLChunk(image_url=base64_data_url),
                model="mistral-ocr-latest"
            )

            # Extract text from the OCR response
            if image_response.pages and len(image_response.pages) > 0:
                text = image_response.pages[0].markdown
                logger.info(f"Successfully extracted {len(text)} characters from image")
                return text
            else:
                logger.warning("No text extracted from image")
                return ""

        except Exception as e:
            logger.error(f"Error in Mistral OCR processing: {str(e)}")
            raise

    async def _structure_medication_content(self, text: str) -> Dict[str, Any]:
        """
        Process the extracted text to identify medication information.

        Args:
            text: Raw extracted text from OCR

        Returns:
            Structured content with medication information
        """
        logger.info("Structuring extracted medication content")

        # Use Mistral to extract structured information from the OCR text
        try:
            # Prepare message for Mistral to extract medication information
            chat_response = self.client.chat.complete(
                model="mistral-large-latest",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            TextChunk(
                                text=(
                                    f"This is the OCR text extracted from a medication package or prescription:\n\n{text}\n\n"
                                    "Extract the following information in JSON format:\n"
                                    "- medication_name: The name of the medication\n"
                                    "- active_ingredients: List of active ingredients and their amounts\n"
                                    "- dosage: The recommended dosage\n"
                                    "- manufacturer: The company that makes the medication\n"
                                    "- expiration_date: When the medication expires\n"
                                    "- batch_number: The batch or lot number\n"
                                    "- instructions: Usage instructions\n\n"
                                    "The output should be strictly JSON with no extra commentary."
                                )
                            ),
                        ],
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )

            # Parse the structured response
            structured_content = chat_response.choices[0].message.content
            return structured_content

        except Exception as e:
            logger.error(f"Error structuring medication content: {str(e)}")
            return {
                "error": str(e),
                "raw_text": text
            }