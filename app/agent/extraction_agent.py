from datetime import datetime
from io import BytesIO
from typing import Dict, Any, Optional, Tuple
import logging
import re

from PIL import Image
from fastapi import UploadFile

from app.agent.medication_extraction_state import PageExtractionState
from app.agent.ocr_gateway_extractor import OCRProvider
from app.providers.llm_manager import LLMConfig, LLMManager, LLMType
import google.generativeai as genai
import os
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class ExtractorAgent:
    def __init__(self, settings=None):
        """
             Initialize the extractor with configuration settings.
             Args:
                 settings (dict): Configuration settings.
             """
        self.settings = settings
        llm_config = LLMConfig(
            temperature=0.0,
        )
        self.llm_manager = LLMManager(llm_config)
        self.primary_llm = self.llm_manager.get_llm(LLMType.GEMINI)
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=self.google_api_key)
        self.gemini_model = genai.GenerativeModel(model_name="gemini-2.0-flash-lite")

    async def validate_page(self, state: PageExtractionState) -> dict:
        """Process image with Google Gemini model."""
        file = state["file"]
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
            response = await self.gemini_model.generate_content_async(inputs)

            extracted_text = response.text
            logger.info(f"Successfully extracted {len(extracted_text)} characters from image using Gemini")
            return {
                "extracted_texts": [extracted_text],
            }

        except Exception as e:
            logger.error(f"Error in Gemini OCR processing: {str(e)}")
            return f"Error extracting text with Gemini: {str(e)}"
