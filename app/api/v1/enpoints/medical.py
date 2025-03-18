from typing import List, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
import logging

from app.workflow.medication_graph import medication_graph

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/medication",
    tags=["medication"],
)


@router.post("/extract")
async def extract_medication_info(
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
):
    """
    Extract medication information from uploaded prescription or medication package images

    Args:
        files: List of image files to process
        background_tasks: BackgroundTasks for async processing

    Returns:
        Job ID for tracking the extraction process
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

        # Start the workflow execution
        result = medication_graph.invoke(initial_state)

        return {
            "status": "success",
            "message": f"Successfully processed {len(files)} medication images",
            "results": result.get("processed_medications", [])
        }

    except Exception as e:
        logger.error(f"Error processing medication images: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing medication images: {str(e)}")