from typing import List, Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
import logging

from app.workflow.medication_graph import medication_graph
from app.workflow.ocr_graph import ocr_graph

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/medication",
    tags=["medication"],
)


# ================================
# MODELOS DE SWAGGER/PYDANTIC
# ================================

class MedicationData(BaseModel):
    """Modelo para datos extraídos de medicamento"""
    medication_name: Optional[str] = Field(None, description="Nombre comercial del medicamento", example="Bronpax")
    common_denomination: Optional[str] = Field(None, description="Denominación común o principio activo", example="Ambroxol")
    concentration: Optional[str] = Field(None, description="Concentración del medicamento", example="7.5 mg/mL")
    form: Optional[str] = Field(None, description="Forma farmacéutica completa", example="Solución oral")
    form_simple: Optional[str] = Field(None, description="Forma farmacéutica simplificada", example="Gotas")
    brand_name: Optional[str] = Field(None, description="Marca o laboratorio", example="Bronpax")
    country: Optional[str] = Field(None, description="País de origen", example="México")
    presentation: Optional[str] = Field(None, description="Presentación del producto", example="Frasco gotero x 30 mL")
    product_type: Optional[str] = Field(None, description="Tipo de producto", example="PRODUCTO FARMACEUTICO")
    fractions: Optional[str] = Field(None, description="Número de fracciones", example="1")
    gtin_code: Optional[str] = Field(None, description="Código GTIN si se encuentra", example="7501008123456")


class SearchStats(BaseModel):
    """Estadísticas de búsqueda semántica"""
    filters_applied: int = Field(description="Número de filtros aplicados", example=2)
    filter_names: List[str] = Field(description="Nombres de los filtros utilizados", example=["common_denomination", "form_simple"])
    search_strategy: str = Field(description="Estrategia de búsqueda utilizada", example="PRECISE_FILTERING")
    confidence_threshold: float = Field(description="Umbral de confianza aplicado", example=0.60)
    results_found: int = Field(description="Número de resultados encontrados", example=5)
    best_score: float = Field(description="Mejor puntuación de similitud", example=0.87)


class ProcessingResult(BaseModel):
    """Resultado del procesamiento de una imagen"""
    ocr_extracted_text: Optional[str] = Field(None, description="Texto extraído por OCR")
    processed_medications: Optional[MedicationData] = Field(None, description="Datos estructurados del medicamento")
    semantic_results: Optional[List[Dict[str, Any]]] = Field(None, description="Resultados de búsqueda semántica")
    semantic_best_match: Optional[Dict[str, Any]] = Field(None, description="Mejor coincidencia semántica")
    enrichment_applied: bool = Field(False, description="Si se aplicó enriquecimiento de datos")
    search_strategy: Optional[str] = Field(None, description="Estrategia de búsqueda utilizada")
    search_confidence: float = Field(0.0, description="Confianza de la búsqueda")
    confidence_threshold_used: float = Field(0.0, description="Umbral de confianza utilizado")
    search_stats: Optional[SearchStats] = Field(None, description="Estadísticas detalladas de búsqueda")
    gtin_validation: Optional[Dict[str, Any]] = Field(None, description="Resultado de validación GTIN")


class ErrorResponse(BaseModel):
    """Respuesta de error estándar"""
    detail: str = Field(description="Descripción del error", example="Error processing medication images: Invalid file format")


# ================================
# EJEMPLOS PARA SWAGGER
# ================================

class MedicationExtractionResponse(BaseModel):
    """Respuesta del endpoint de extracción de medicamentos"""
    status: str = Field(description="Estado de la operación", example="success")
    message: str = Field(description="Mensaje descriptivo", example="Successfully processed 1 medication images")
    results: ProcessingResult = Field(description="Resultados del procesamiento")
    
    class Config:
        schema_extra = {
            "example": {
                "status": "success",
                "message": "Successfully processed 1 medication images",
                "results": {
                    "ocr_extracted_text": "Bronpax Ambroxol 7.5 mg/mL Solución oral Frasco gotero x 30 mL",
                    "processed_medications": {
                        "medication_name": "Bronpax",
                        "common_denomination": "Ambroxol",
                        "concentration": "7.5 mg/mL",
                        "form": "Solución oral",
                        "form_simple": "Gotas",
                        "brand_name": "Bronpax",
                        "country": "México",
                        "presentation": "Frasco gotero x 30 mL",
                        "product_type": "PRODUCTO FARMACEUTICO",
                        "fractions": "1",
                        "gtin_code": None
                    },
                    "semantic_results": [
                        {
                            "medication_name": "Bronpax",
                            "common_denomination": "AMBROXOL",
                            "concentration": "7.5 mg/mL",
                            "similarity_score": 0.87,
                            "search_method": "semantic_filtered_2"
                        }
                    ],
                    "semantic_best_match": {
                        "medication_name": "Bronpax",
                        "common_denomination": "AMBROXOL",
                        "similarity_score": 0.87
                    },
                    "enrichment_applied": True,
                    "search_strategy": "PRECISE_FILTERING",
                    "search_confidence": 0.87,
                    "confidence_threshold_used": 0.60,
                    "search_stats": {
                        "filters_applied": 2,
                        "filter_names": ["common_denomination", "form_simple"],
                        "search_strategy": "PRECISE_FILTERING",
                        "confidence_threshold": 0.60,
                        "results_found": 5,
                        "best_score": 0.87
                    },
                    "gtin_validation": None
                }
            }
        }


@router.post("/extract", 
             response_model=MedicationExtractionResponse,
             responses={
                 200: {
                     "description": "Extracción exitosa de información de medicamento",
                     "model": MedicationExtractionResponse
                 },
                 400: {
                     "description": "Error en los datos de entrada",
                     "model": ErrorResponse
                 },
                 500: {
                     "description": "Error interno del servidor",
                     "model": ErrorResponse
                 }
             },
             summary="Extraer información de medicamentos desde imágenes",
             description="""
## 🏥 Extracción Inteligente de Medicamentos

Este endpoint utiliza **OCR + IA** para extraer y enriquecer información de medicamentos desde imágenes.

### 🔍 **Proceso Completo:**
1. **OCR Avanzado**: Extrae texto de imágenes usando Mistral o Gemini
2. **Estructuración IA**: Convierte texto en datos estructurados
3. **Búsqueda Semántica**: Enriquece con base de datos vectorial (Qdrant)
4. **Validación GTIN**: Verifica códigos de barras cuando están disponibles

### 🎯 **Estrategias de Búsqueda Adaptativas:**
- **PRECISE_FILTERING**: Con múltiples filtros (umbral 60%)
- **MODERATE_FILTERING**: Con un filtro (umbral 65%) 
- **SEMANTIC_ONLY**: Solo búsqueda semántica (umbral 70%)

### 📊 **Campos Extraídos:**
- Nombre comercial y principio activo
- Concentración y forma farmacéutica
- Marca, país, presentación
- Código GTIN (si disponible)

### 🛡️ **Robustez:**
- Fallback automático si fallan filtros
- Manejo de OCR incompleto
- Múltiples proveedores OCR disponibles
             """)
async def extract_medication_info(
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(..., description="Imágenes de medicamentos (PNG, JPG, JPEG, WEBP)"),
        provider: Optional[str] = Query(
            None, 
            description="Proveedor OCR a utilizar", 
            enum=["mistral", "gemini"],
            example="gemini"
        )
):
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
        graph = ocr_graph.compile()
        result = await graph.ainvoke(initial_state)
        logger.info(f"Result: {result}")
        
        # Formatear respuesta según el modelo de Swagger
        # Convertir MedicationDetailsModel a MedicationData si es necesario
        processed_medications = result.get("processed_medications")
        if processed_medications and hasattr(processed_medications, '__dict__'):
            # Es un objeto Pydantic, convertir a dict para MedicationData
            medication_dict = {
                "medication_name": getattr(processed_medications, 'medication_name', None),
                "common_denomination": getattr(processed_medications, 'common_denomination', None),
                "concentration": getattr(processed_medications, 'concentration', None),
                "form": getattr(processed_medications, 'form', None),
                "form_simple": getattr(processed_medications, 'form_simple', None),
                "brand_name": getattr(processed_medications, 'brand_name', None),
                "country": getattr(processed_medications, 'country', None),
                "presentation": getattr(processed_medications, 'presentation', None),
                "product_type": getattr(processed_medications, 'product_type', None),
                "fractions": getattr(processed_medications, 'fractions', None),
                "gtin_code": getattr(processed_medications, 'bar_code', None)  # bar_code -> gtin_code
            }
            result["processed_medications"] = MedicationData(**medication_dict)
        
        # Formatear el texto OCR extraído
        extracted_texts = result.get("extracted_texts", [])
        if extracted_texts:
            result["ocr_extracted_text"] = "\n".join(extracted_texts)
        
        return MedicationExtractionResponse(
            status="success",
            message=f"Successfully processed {len(files)} medication images",
            results=ProcessingResult(**result)
        )

    except Exception as e:
        logger.error(f"Error processing medication images: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing medication images: {str(e)}")