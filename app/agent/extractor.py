from datetime import datetime
from io import BytesIO
from typing import Dict, Any, Optional, Tuple
import logging
import re

from PIL import Image
from fastapi import UploadFile

from app.providers.llm_manager import LLMConfig, LLMManager, LLMType

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Extractor:
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

    async def extract(self, file: UploadFile) -> str:
        """ Process image with Google Gemini model. """
        logger.info(f"Processing image with Gemini OCR: {file.filename}")
        # Reset file position to beginning
        await file.seek(0)
        image_content = await file.read()
        # Convert to PIL Image
        image = Image.open(BytesIO(image_content))