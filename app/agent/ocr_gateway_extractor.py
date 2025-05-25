# app/agent/ocr_gateway_extractor.py

from typing import Dict, Any, List, Literal
from enum import Enum
import logging
import base64
from io import BytesIO
import os
from pathlib import Path

from fastapi import UploadFile
from mistralai import Mistral, ImageURLChunk
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class OCRProvider(str, Enum):
    """Enum for OCR providers"""
    MISTRAL = "mistral"
    GEMINI = "gemini"


class OCRGatewayExtractor:
    """
    Gateway agent that can select between different OCR providers (Mistral or Gemini)
    to extract text from images.
    """

    def __init__(self):
        """Initialize OCRGatewayExtractor with available providers"""
        # Check environment variables
        self.mistral_api_key = os.getenv("MISTRAL_API_KEY")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")

        # Initialize providers if keys are available
        self.available_providers = []

        if self.mistral_api_key:
            self.mistral_client = Mistral(api_key=self.mistral_api_key)
            self.available_providers.append(OCRProvider.MISTRAL)
            logger.info("Mistral OCR provider initialized")

        if self.google_api_key:
            genai.configure(api_key=self.google_api_key)
            self.gemini_model = genai.GenerativeModel(model_name="gemini-2.0-flash-lite")
            self.available_providers.append(OCRProvider.GEMINI)
            logger.info("Gemini OCR provider initialized")

        if not self.available_providers:
            logger.warning("No OCR providers available. Set MISTRAL_API_KEY or GOOGLE_API_KEY env variables.")
            raise ValueError("No OCR providers available. Set MISTRAL_API_KEY or GOOGLE_API_KEY env variables.")

        logger.info(f"OCRGatewayExtractor initialized with providers: {self.available_providers}")

    async def extract_text(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract text from images using the specified or default OCR provider

        Args:
            state: Current workflow state with files and optional provider specification

        Returns:
            Updated state with extracted texts
        """
        logger.info("Starting gateway OCR text extraction process")
        files = state.get("files", [])

        # Return updated state
        return {
            "files": files,
        }

    async def _process_with_mistral(self, file: UploadFile) -> str:
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
            image_response = self.mistral_client.ocr.process(
                document=ImageURLChunk(image_url=base64_data_url),
                model="mistral-ocr-latest"
            )

            # Extract text from the OCR response
            if image_response.pages and len(image_response.pages) > 0:
                text = image_response.pages[0].markdown
                logger.info(f"Successfully extracted {len(text)} characters from image using Mistral")
                return text
            else:
                logger.warning("No text extracted from image with Mistral")
                return ""

        except Exception as e:
            logger.error(f"Error in Mistral OCR processing: {str(e)}")
            return f"Error extracting text with Mistral: {str(e)}"

    async def _process_with_gemini(self, file: UploadFile) -> str:
        """Process image with Google Gemini model."""
        logger.info(f"Processing image with Gemini OCR: {file.filename}")

        try:
            # Reset file position to beginning
            await file.seek(0)
            image_content = await file.read()

            # Convert to PIL Image
            image = Image.open(BytesIO(image_content))

            # Prepare prompt for Gemini
            prompt = """Analyze the image provided and extract all readable text.
                Present the extracted content in a well-organized Markdown format. 
                Ensure proper formatting by using headings, bullet points, numbered lists, 
                and code blocks where appropriate to enhance clarity and readability. 
                Retain the structure of the original content, ensuring that sections, titles, 
                and important details are clearly separated. If the image contains any tables or 
                code snippets, format them correctly to preserve their meaning. 
                The output should be clear, concise, and easy to interpret."""

            # Generate content with Gemini
            inputs = [prompt, image]
            response = self.gemini_model.generate_content(inputs)

            extracted_text = response.text
            logger.info(f"Successfully extracted {len(extracted_text)} characters from image using Gemini")
            return extracted_text

        except Exception as e:
            logger.error(f"Error in Gemini OCR processing: {str(e)}")
            return f"Error extracting text with Gemini: {str(e)}"