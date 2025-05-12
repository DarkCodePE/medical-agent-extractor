from typing import List, Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query
import logging

from app.workflow.medication_graph import medication_graph
from app.workflow.ocr_graph import ocr_graph

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/medication",
    tags=["medication"],
)


@router.post("/extract")
async def extract_medication_info(
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
        provider: Optional[str] = Query(None, description="OCR provider to use (mistral or gemini)")
):
    """
    Extract text from uploaded images using OCR

    Args:
        files: List of image files to process
        background_tasks: BackgroundTasks for async processing
        provider: OCR provider to use (mistral or gemini)

    Returns:
        Extracted text results
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Validate file types
    for file in files:
        if not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {file.content_type}. Only image files are supported."
            )

    try:
        # Initialize the state with the files
        initial_state = {"files": files}
        if provider:
            initial_state["ocr_provider"] = provider

        # Start the workflow execution
        result = await ocr_graph.ainvoke(initial_state)
        logger.info(f"Result: {result}")
        return {
            "status": "success",
            "message": f"Successfully processed {len(files)} medication images",
            "results": result
        }

    except Exception as e:
        logger.error(f"Error processing medication images: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing medication images: {str(e)}")