from typing import List, Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
import logging

from app.workflow.medication_graph import medication_graph
from app.workflow.ocr_graph import ocr_graph
from app.tools.check_gtin_in_database import GtinService
from app.services.medication_vector_service import MedicationVectorService

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
    lot_number: Optional[str] = Field(None, description="Número de lote del medicamento", example="LOTE001")
    expiration_date: Optional[str] = Field(None, description="Fecha de vencimiento del medicamento en formato yyyy-MM-dd", example="2025-12-01")
    database_id: Optional[int] = Field(None, description="ID del medicamento en la base de datos GTIN (si se encontró)", example=11535)


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
    processed_medications: Optional[MedicationData] = Field(None, description="Datos extraídos solo del OCR (originales)")
    processed_enrichment_medications: Optional[MedicationData] = Field(None, description="Datos finales enriquecidos con BD/búsqueda semántica")
    semantic_results: Optional[List[Dict[str, Any]]] = Field(None, description="Resultados de búsqueda semántica")
    semantic_best_match: Optional[Dict[str, Any]] = Field(None, description="Mejor coincidencia semántica")
    enrichment_applied: bool = Field(False, description="Si se aplicó enriquecimiento de datos")
    search_strategy: Optional[str] = Field(None, description="Estrategia de búsqueda utilizada")
    search_confidence: float = Field(0.0, description="Confianza de la búsqueda")
    confidence_threshold_used: float = Field(0.0, description="Umbral de confianza utilizado")
    search_stats: Optional[SearchStats] = Field(None, description="Estadísticas detalladas de búsqueda")
    gtin_validation: Optional[Dict[str, Any]] = Field(None, description="Resultado de validación GTIN")
    enrichment_source_fields: Optional[Dict[str, str]] = Field(None, description="Qué campo vino de qué fuente")
    ocr_vs_enriched_comparison: Optional[Dict[str, Any]] = Field(None, description="Comparación entre datos OCR vs enriquecidos")


class MedicationRegistrationRequest(BaseModel):
    """Modelo para registrar un medicamento enriquecido en la base de datos GTIN"""
    # Datos del medicamento
    medication_data: MedicationData = Field(..., description="Datos del medicamento extraído y enriquecido")
    gtin_code: str = Field(..., description="Código GTIN del medicamento", example="7750304964586")
    
    # Metadatos del proceso
    enrichment_source: str = Field(..., description="Fuente del enriquecimiento", example="semantic_search")
    enrichment_confidence: float = Field(..., description="Confianza del enriquecimiento", example=0.87)
    user_approved: bool = Field(True, description="Si fue aprobado por el usuario", example=True)
    
    # Campos opcionales con defaults
    gtin_code_type: Optional[str] = Field(None, description="Tipo de código GTIN (se determina automáticamente)", example="GTIN_13")
    pharmacy_type: Optional[str] = Field("M", description="Tipo de farmacia", example="M")
    code_rs_list: Optional[str] = Field(None, description="Código RS", example="EN04755")
    state: Optional[str] = Field("ACTIVO", description="Estado del medicamento", example="ACTIVO")
    
    class Config:
        json_schema_extra = {
            "example": {
                "medication_data": {
                    "medication_name": "Bronpax",
                    "common_denomination": "Ambroxol",
                    "concentration": "7.5 mg/mL",
                    "form": "Solución oral",
                    "form_simple": "Gotas",
                    "brand_name": "FARMINDUSTRIA",
                    "country": "PERÚ",
                    "presentation": "20mL",
                    "product_type": "PRODUCTO FARMACEUTICO",
                    "fractions": "1",
                    "gtin_code": None,
                    "lot_number": "LT240815",
                    "expiration_date": "2025-12-01",
                    "database_id": 11535
                },
                "gtin_code": "7750304964586",
                "enrichment_source": "semantic_search",
                "enrichment_confidence": 0.87,
                "user_approved": True,
                "pharmacy_type": "M",
                "state": "ACTIVO"
            }
        }


class SkuRegistrationRequest(BaseModel):
    """Modelo para registrar un SKU de medicamento"""
    # Datos del medicamento (debe existir en ItemsGtin)
    item_gtin_id: int = Field(..., description="ID del medicamento en ItemsGtin", example=11535)
    gtin_code: str = Field(..., description="Código GTIN del medicamento", example="7750304964586")
    
    # Datos específicos del SKU
    lot_number: str = Field(..., description="Número de lote del medicamento", example="LT240815")
    expiration_date: str = Field(..., description="Fecha de expiración en formato yyyy-MM-dd", example="2025-12-01")
    quantity: int = Field(..., description="Cantidad disponible", example=100)
    price: float = Field(0.0, description="Precio unitario", example=15.50)
    
    # Metadatos del proceso
    pharmacy_id: int = Field(..., description="ID de la farmacia", example=1)
    uploader_id: int = Field(..., description="ID del usuario que sube el SKU", example=1)
    received_date: Optional[str] = Field(None, description="Fecha de recepción en formato yyyy-MM-dd", example="2024-01-15")
    
    # Campos opcionales
    code: Optional[str] = Field(None, description="Código interno del SKU", example="SKU001")
    description: Optional[str] = Field(None, description="Descripción adicional", example="Lote de prueba")
    is_active: bool = Field(True, description="Si el SKU está activo", example=True)
    
    class Config:
        json_schema_extra = {
            "example": {
                "item_gtin_id": 11535,
                "gtin_code": "7750304964586",
                "lot_number": "LT240815",
                "expiration_date": "2025-12-01",
                "quantity": 100,
                "price": 15.50,
                "pharmacy_id": 1,
                "uploader_id": 1,
                "received_date": "2024-01-15",
                "code": "SKU001",
                "description": "Lote de prueba",
                "is_active": True
            }
        }


class SkuRegistrationResponse(BaseModel):
    """Respuesta del registro de SKU"""
    status: str = Field(description="Estado de la operación", example="success")
    message: str = Field(description="Mensaje descriptivo", example="SKU registrado exitosamente")
    sku_id: Optional[int] = Field(None, description="ID del SKU en la base de datos", example=12345)
    item_gtin_id: int = Field(description="ID del medicamento en ItemsGtin", example=11535)
    gtin_code: str = Field(description="Código GTIN", example="7750304964586")
    lot_number: str = Field(description="Número de lote", example="LT240815")
    registered_at: str = Field(description="Timestamp del registro", example="2024-01-15T10:30:00Z")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "SKU 'LT240815' registrado exitosamente",
                "sku_id": 12345,
                "item_gtin_id": 11535,
                "gtin_code": "7750304964586",
                "lot_number": "LT240815",
                "registered_at": "2024-01-15T10:30:00Z"
            }
        }


class CompleteMedicationRegistrationRequest(BaseModel):
    """Modelo para registro completo: extracción + medicamento + SKU"""
    # Datos para extracción
    files: List[UploadFile] = Field(..., description="Imágenes de medicamentos")
    provider: Optional[str] = Field(None, description="Proveedor OCR", enum=["mistral", "gemini"])
    
    # Datos para registro de medicamento (si no existe)
    gtin_code: Optional[str] = Field(None, description="Código GTIN si se conoce", example="7750304964586")
    user_approved: bool = Field(True, description="Si fue aprobado por el usuario")
    
    # Datos para registro de SKU
    quantity: int = Field(..., description="Cantidad disponible", example=100)
    price: float = Field(0.0, description="Precio unitario", example=15.50)
    pharmacy_id: int = Field(..., description="ID de la farmacia", example=1)
    uploader_id: int = Field(..., description="ID del usuario que sube", example=1)
    received_date: Optional[str] = Field(None, description="Fecha de recepción", example="2024-01-15")
    code: Optional[str] = Field(None, description="Código interno del SKU", example="SKU001")
    description: Optional[str] = Field(None, description="Descripción adicional")
    is_active: bool = Field(True, description="Si el SKU está activo")


class CompleteMedicationRegistrationResponse(BaseModel):
    """Respuesta del registro completo"""
    status: str = Field(description="Estado de la operación", example="success")
    message: str = Field(description="Mensaje descriptivo")
    
    # Resultados de extracción
    extraction_results: Optional[ProcessingResult] = Field(None, description="Resultados de extracción")
    
    # Resultados de registro de medicamento
    medication_registration: Optional[Dict[str, Any]] = Field(None, description="Datos de registro de medicamento")
    
    # Resultados de registro de SKU
    sku_registration: Optional[Dict[str, Any]] = Field(None, description="Datos de registro de SKU")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Proceso completo exitoso: extracción + registro medicamento + registro SKU",
                "extraction_results": {
                    "processed_enrichment_medications": {
                        "medication_name": "Bronpax",
                        "common_denomination": "Ambroxol",
                        "expiration_date": "2025-12-01",
                        "lot_number": "LT240815"
                    }
                },
                "medication_registration": {
                    "medication_id": 11535,
                    "gtin_code": "7750304964586",
                    "is_ai_generated": true
                },
                "sku_registration": {
                    "sku_id": 12345,
                    "lot_number": "LT240815",
                    "quantity": 100
                }
            }
        }


class MedicationRegistrationResponse(BaseModel):
    """Respuesta del registro de medicamento"""
    status: str = Field(description="Estado de la operación", example="success")
    message: str = Field(description="Mensaje descriptivo", example="Medicamento registrado exitosamente como generado por IA")
    medication_id: Optional[int] = Field(None, description="ID del medicamento en la base de datos", example=12345)
    gtin_code: str = Field(description="Código GTIN registrado", example="7750304964586")
    registered_at: str = Field(description="Timestamp del registro", example="2024-01-15T10:30:00Z")
    is_ai_generated: bool = Field(True, description="Indica si fue generado por IA", example=True)
    enrichment_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos del proceso de enriquecimiento")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Medicamento 'Bronpax' registrado exitosamente como generado por IA",
                "medication_id": 12345,
                "gtin_code": "7750304964586",
                "registered_at": "2024-01-15T10:30:00Z",
                "is_ai_generated": True,
                "enrichment_metadata": {
                    "enrichment_source": "semantic_search",
                    "enrichment_confidence": 0.87,
                    "user_approved": True,
                    "auto_vectorized": True
                }
            }
        }


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
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Successfully processed 1 medication images",
                "results": {
                    "ocr_extracted_text": "Bronpax Ambroxol 7.5 mg/mL Solución oral Frasco gotero x 30 mL",
                    "processed_medications": {
                        "medication_name": "Bronpax",
                        "common_denomination": "Ambroxol",
                        "concentration": "7.5 mg/mL",
                        "form": None,
                        "form_simple": "Gotas",
                        "brand_name": None,
                        "country": None,
                        "presentation": "20mL",
                        "product_type": None,
                        "fractions": None,
                        "gtin_code": None,
                        "lot_number": "LT240815",
                        "expiration_date": "2025-12-01",
                        "database_id": None
                    },
                    "processed_enrichment_medications": {
                        "medication_name": "Bronpax",
                        "common_denomination": "Ambroxol",
                        "concentration": "7.5 mg/mL",
                        "form": "Solución oral",
                        "form_simple": "Gotas",
                        "brand_name": "FARMINDUSTRIA",
                        "country": "PERÚ",
                        "presentation": "20mL",
                        "product_type": "PRODUCTO FARMACEUTICO",
                        "fractions": "1",
                        "gtin_code": None,
                        "lot_number": "LT240815",
                        "expiration_date": "2025-12-01",
                        "database_id": 11535
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
                    "gtin_validation": None,
                    "enrichment_source_fields": {
                        "medication_name": "ocr_original",
                        "common_denomination": "ocr_original", 
                        "concentration": "ocr_original",
                        "form": "semantic_search",
                        "form_simple": "ocr_original",
                        "brand_name": "semantic_search",
                        "country": "semantic_search",
                        "presentation": "ocr_original",
                        "product_type": "semantic_search",
                        "fractions": "semantic_search"
                    },
                    "ocr_vs_enriched_comparison": {
                        "brand_name": {
                            "ocr_original": None,
                            "enriched": "FARMINDUSTRIA",
                            "was_enriched": True,
                            "source": "semantic_search"
                        },
                        "form": {
                            "ocr_original": None,
                            "enriched": "Solución oral",
                            "was_enriched": True,
                            "source": "semantic_search"
                        }
                    }
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
        def convert_medication_model(medication_obj):
            """Convierte MedicationDetailsModel a MedicationData"""
            if medication_obj and hasattr(medication_obj, '__dict__'):
                return MedicationData(
                    medication_name=getattr(medication_obj, 'medication_name', None),
                    common_denomination=getattr(medication_obj, 'common_denomination', None),
                    concentration=getattr(medication_obj, 'concentration', None),
                    form=getattr(medication_obj, 'form', None),
                    form_simple=getattr(medication_obj, 'form_simple', None),
                    brand_name=getattr(medication_obj, 'brand_name', None),
                    country=getattr(medication_obj, 'country', None),
                    presentation=getattr(medication_obj, 'presentation', None),
                    product_type=getattr(medication_obj, 'product_type', None),
                    fractions=getattr(medication_obj, 'fractions', None),
                    gtin_code=getattr(medication_obj, 'bar_code', None),  # bar_code -> gtin_code
                    lot_number=getattr(medication_obj, 'lot_number', None),
                    expiration_date=getattr(medication_obj, 'expiration_date', None),
                    database_id=getattr(medication_obj, 'database_id', None)
                )
            return medication_obj
        
        # Convertir ambas versiones si existen
        processed_medications = result.get("processed_medications")
        processed_enrichment_medications = result.get("processed_enrichment_medications")
        
        if processed_medications:
            result["processed_medications"] = convert_medication_model(processed_medications)
            
        if processed_enrichment_medications:
            result["processed_enrichment_medications"] = convert_medication_model(processed_enrichment_medications)
        
        # Formatear el texto OCR extraído
        extracted_texts = result.get("extracted_texts", [])
        if extracted_texts:
            result["ocr_extracted_text"] = "\n".join(extracted_texts)
        
        # Filtrar solo los campos válidos para ProcessingResult
        valid_fields = {
            "ocr_extracted_text": result.get("ocr_extracted_text"),
            "processed_medications": result.get("processed_medications"),
            "processed_enrichment_medications": result.get("processed_enrichment_medications"),
            "semantic_results": result.get("semantic_results"),
            "semantic_best_match": result.get("semantic_best_match"),
            "enrichment_applied": result.get("enrichment_applied", False),
            "search_strategy": result.get("search_strategy"),
            "search_confidence": result.get("search_confidence", 0.0),
            "confidence_threshold_used": result.get("confidence_threshold_used", 0.0),
            "search_stats": result.get("search_stats"),
            "gtin_validation": result.get("gtin_validation"),
            "enrichment_source_fields": result.get("enrichment_source_fields"),
            "ocr_vs_enriched_comparison": result.get("ocr_vs_enriched_comparison")
        }
        
        return MedicationExtractionResponse(
            status="success",
            message=f"Successfully processed {len(files)} medication images",
            results=ProcessingResult(**valid_fields)
        )

    except Exception as e:
        logger.error(f"Error processing medication images: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing medication images: {str(e)}")


@router.post("/register-enriched",
             response_model=MedicationRegistrationResponse,
             responses={
                 200: {
                     "description": "Medicamento registrado exitosamente en la base de datos GTIN",
                     "model": MedicationRegistrationResponse
                 },
                 400: {
                     "description": "Datos de entrada inválidos o medicamento ya existe",
                     "model": ErrorResponse
                 },
                 500: {
                     "description": "Error interno del servidor",
                     "model": ErrorResponse
                 }
             },
             summary="Registrar medicamento enriquecido en base de datos GTIN",
             description="""
## 📝 Registro de Medicamento Enriquecido con IA

Este endpoint registra directamente un medicamento enriquecido en la base de datos GTIN, 
preparando automáticamente los datos y marcándolo como generado por IA.

### 🔍 **Flujo Completo:**
1. **Recibe datos**: `MedicationData` (del endpoint `/extract`) + metadatos de enriquecimiento
2. **Validación automática**: Verifica GTIN único, campos obligatorios y aprobación del usuario
3. **Preparación inteligente**: Determina tipo GTIN automáticamente y mapea campos
4. **Registro en BD**: Inserta con flag `IsAiGenerated = true` para auditoría
5. **Vectorización automática**: Actualiza Qdrant para mejorar futuras búsquedas semánticas

### 📊 **Validaciones y Procesamiento Automático:**
- ✅ Determina tipo de GTIN por longitud del código (GTIN_8/12/13/14)
- ✅ Verifica que el GTIN no exista previamente en la base de datos
- ✅ Valida campos obligatorios: `medication_name`, `common_denomination`, `gtin_code`
- ✅ Requiere aprobación explícita del usuario (`user_approved: true`)
- ✅ Marca automáticamente como generado por IA para auditoría

### 🎯 **Campos Automáticos/Opcionales:**
- **Automáticos**: `gtin_code_type`, `IsAiGenerated = true`
- **Con defaults**: `pharmacy_type = "M"`, `state = "ACTIVO"`, `fractions = "1"`
- **Opcionales**: `code_rs_list`, campos vacíos se almacenan como cadena vacía

### 🛡️ **Seguridad y Trazabilidad Completa:**
- 🔐 Solo acepta medicamentos con `user_approved = true`
- 📊 Mantiene metadatos completos de enriquecimiento y confianza
- 🏷️ Flag `IsAiGenerated` diferencia registros automáticos vs manuales
- 📈 Actualización automática de vectores semánticos para mejorar el sistema
- ⚡ Respuesta incluye confirmación de vectorización y metadatos de auditoría

### 📋 **Estructura de Entrada:**
```json
{
  "medication_data": { /* Datos del medicamento del endpoint /extract */ },
  "gtin_code": "código GTIN extraído o validado",
  "enrichment_source": "semantic_search | ocr_extraction | database_gtin",
  "enrichment_confidence": 0.87,
  "user_approved": true
}
```
             """)
async def register_enriched_medication(
    request: MedicationRegistrationRequest
):
    """
    Registra un medicamento enriquecido directamente en la base de datos GTIN.
    
    Args:
        request: Datos del medicamento y metadatos de enriquecimiento
        
    Returns:
        Confirmación de registro exitoso
    """
    try:
        logger.info(f"🔄 Iniciando registro de medicamento enriquecido: {request.gtin_code}")
        
        # Validar que el usuario haya aprobado los datos
        if not request.user_approved:
            raise HTTPException(
                status_code=400, 
                detail="No se puede registrar medicamento sin aprobación del usuario"
            )
        
        # Validar campos obligatorios del medicamento
        if not request.medication_data.medication_name:
            raise HTTPException(status_code=400, detail="medication_name es obligatorio")
        if not request.medication_data.common_denomination:
            raise HTTPException(status_code=400, detail="common_denomination es obligatorio")
        if not request.gtin_code:
            raise HTTPException(status_code=400, detail="gtin_code es obligatorio")
        
        # Determinar tipo de GTIN automáticamente
        gtin_code_clean = request.gtin_code.strip().replace('-', '').replace(' ', '')
        gtin_type_mapping = {
            8: "GTIN_8",
            12: "GTIN_12", 
            13: "GTIN_13",
            14: "GTIN_14"
        }
        gtin_type = request.gtin_code_type or gtin_type_mapping.get(len(gtin_code_clean), "GTIN_13")
        
        # Inicializar servicio GTIN
        gtin_service = GtinService()
        
        # Verificar que el GTIN no exista previamente
        existing_medication = gtin_service.query_gtin(gtin_code_clean)
        if existing_medication:
            logger.warning(f"⚠️ GTIN {gtin_code_clean} ya existe en la base de datos")
            raise HTTPException(
                status_code=400,
                detail=f"El medicamento con GTIN {gtin_code_clean} ya existe en la base de datos"
            )
        
        # Preparar datos para inserción
        med_data = request.medication_data
        medication_insert_data = {
            'GtinCode': gtin_code_clean,
            'GtinCodeType': gtin_type,
            'PharmacyType': request.pharmacy_type,
            'ProductType': med_data.product_type or "PRODUCTO FARMACEUTICO",
            'Name': med_data.medication_name,
            'CommonDenomination': med_data.common_denomination,
            'Concentration': med_data.concentration or "",
            'Form': med_data.form or "",
            'FormSimple': med_data.form_simple or "",
            'BrandName': med_data.brand_name or "",
            'Country': med_data.country or "",
            'Presentation': med_data.presentation or "",
            'CodeRsList': request.code_rs_list,
            'Fractions': med_data.fractions or "1",
            'State': request.state,
            'IsAiGenerated': True  # Marcar como generado por IA
        }
        
        # Ejecutar inserción usando el método específico del servicio
        result = gtin_service.insert_medication(medication_insert_data)
        
        # Verificar que se insertó correctamente
        verification_result = gtin_service.query_gtin(gtin_code_clean)
        if not verification_result:
            raise HTTPException(
                status_code=500,
                detail="Error al verificar la inserción del medicamento"
            )
        
        medication_id = verification_result.get('Id')
        
        logger.info(f"✅ Medicamento registrado exitosamente: ID={medication_id}, GTIN={gtin_code_clean}, IsAiGenerated=true")
        
        # 🔄 Vectorización automática del nuevo medicamento
        try:
            logger.info(f"🔄 Iniciando vectorización automática del medicamento recién registrado")
            vector_service = MedicationVectorService()
            vectorization_success = await vector_service.update_medication_vector(gtin_code_clean)
            
            if vectorization_success:
                logger.info(f"✅ Medicamento vectorizado exitosamente en Qdrant")
            else:
                logger.warning(f"⚠️ Error en vectorización automática, pero medicamento fue registrado en BD")
        
        except Exception as vector_error:
            logger.error(f"❌ Error en vectorización automática: {str(vector_error)}")
            logger.info("🔄 El medicamento fue registrado correctamente, solo falló la vectorización")
        
        from datetime import datetime
        return MedicationRegistrationResponse(
            status="success",
            message=f"Medicamento '{med_data.medication_name}' registrado exitosamente como generado por IA",
            medication_id=medication_id,
            gtin_code=gtin_code_clean,
            registered_at=datetime.utcnow().isoformat() + "Z",
            is_ai_generated=True,
            enrichment_metadata={
                "enrichment_source": request.enrichment_source,
                "enrichment_confidence": request.enrichment_confidence,
                "user_approved": request.user_approved,
                "auto_vectorized": vectorization_success if 'vectorization_success' in locals() else False,
                "pharmacy_type": request.pharmacy_type,
                "gtin_code_type": gtin_type
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"❌ Error registrando medicamento enriquecido: {str(e)}")
        import traceback
        logger.error(f"🔍 Stack trace: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error interno al registrar medicamento: {str(e)}"
        )


@router.post("/register-sku",
             response_model=SkuRegistrationResponse,
             responses={
                 200: {
                     "description": "SKU registrado exitosamente en la base de datos",
                     "model": SkuRegistrationResponse
                 },
                 400: {
                     "description": "Datos de entrada inválidos o SKU ya existe",
                     "model": ErrorResponse
                 },
                 500: {
                     "description": "Error interno del servidor",
                     "model": ErrorResponse
                 }
             },
             summary="Registrar SKU de medicamento en base de datos",
             description="""
## 📦 Registro de SKU de Medicamento

Este endpoint registra un SKU (Stock Keeping Unit) específico de un medicamento en la tabla `ItemGtinSkus`.

### 🔍 **Información del SKU:**
- **Lote específico**: Número de lote del medicamento
- **Fecha de expiración**: Cuándo vence el lote
- **Cantidad disponible**: Stock actual
- **Precio unitario**: Costo por unidad
- **Farmacia**: Dónde se almacena el SKU

### 📊 **Validaciones:**
- ✅ Verifica que el `item_gtin_id` existe en `ItemsGtin`
- ✅ Verifica que no exista un SKU con el mismo lote para el mismo GTIN
- ✅ Valida formato de fechas (yyyy-MM-dd)
- ✅ Requiere campos obligatorios: lote, expiración, cantidad, farmacia

### 🎯 **Casos de Uso:**
- **Nuevo lote**: Registrar stock recién recibido
- **Actualización**: Agregar más unidades a un lote existente
- **Control de inventario**: Seguimiento de fechas de vencimiento

### 📋 **Estructura de Entrada:**
```json
{
  "item_gtin_id": 11535,
  "gtin_code": "7750304964586",
  "lot_number": "LT240815",
  "expiration_date": "2025-12-01",
  "quantity": 100,
  "price": 15.50,
  "pharmacy_id": 1,
  "uploader_id": 1
}
```
             """)
async def register_sku(
    request: SkuRegistrationRequest
):
    """
    Registra un SKU de medicamento en la tabla ItemGtinSkus.
    
    Args:
        request: Datos del SKU a registrar
        
    Returns:
        Confirmación de registro exitoso
    """
    try:
        logger.info(f"🔄 Iniciando registro de SKU: GTIN={request.gtin_code}, Lote={request.lot_number}")
        
        # Inicializar servicio GTIN
        gtin_service = GtinService()
        
        # Verificar que el ItemGtin existe
        existing_medication = gtin_service.query_gtin(request.gtin_code)
        if not existing_medication:
            raise HTTPException(
                status_code=400,
                detail=f"El medicamento con GTIN {request.gtin_code} no existe en la base de datos"
            )
        
        # Verificar que el item_gtin_id coincide con el GTIN
        if existing_medication.get('Id') != request.item_gtin_id:
            raise HTTPException(
                status_code=400,
                detail=f"El item_gtin_id {request.item_gtin_id} no coincide con el GTIN {request.gtin_code}"
            )
        
        # Verificar que no existe un SKU con el mismo lote para este GTIN
        existing_sku = gtin_service.get_sku_by_lot_and_gtin(request.lot_number, request.item_gtin_id)
        if existing_sku:
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe un SKU con el lote '{request.lot_number}' para el GTIN {request.gtin_code}"
            )
        
        # Preparar datos para inserción
        from datetime import datetime
        
        sku_insert_data = {
            'UploaderId': request.uploader_id,
            'Code': request.code or f"SKU_{request.lot_number}",
            'Lot': request.lot_number,
            'PharmacyId': request.pharmacy_id,
            'ReceivedDate': request.received_date or datetime.now().strftime('%Y-%m-%d'),
            'ExpirationDate': request.expiration_date,
            'IsActive': request.is_active,
            'Quantity': request.quantity,
            'Price': request.price,
            'IsDeleted': False,
            'Name': existing_medication.get('Name', ''),
            'Description': request.description or f"SKU de {existing_medication.get('Name', '')}",
            'ItemGtinId': request.item_gtin_id,
            'InitialQuantity': request.quantity,
            'IsUpdated': False,
            'UpdateDate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Ejecutar inserción
        result = gtin_service.insert_sku(sku_insert_data)
        
        if not result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=f"Error al insertar SKU: {result.get('message')}"
            )
        
        logger.info(f"✅ SKU registrado exitosamente: Lote={request.lot_number}, GTIN={request.gtin_code}")
        
        return SkuRegistrationResponse(
            status="success",
            message=f"SKU '{request.lot_number}' registrado exitosamente",
            sku_id=result.get('sku_id'),
            item_gtin_id=request.item_gtin_id,
            gtin_code=request.gtin_code,
            lot_number=request.lot_number,
            registered_at=datetime.utcnow().isoformat() + "Z"
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"❌ Error registrando SKU: {str(e)}")
        import traceback
        logger.error(f"🔍 Stack trace: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error interno al registrar SKU: {str(e)}"
        )


# ================================
# EJEMPLOS DE USO PARA TESTING
# ================================

"""
## 🔧 Ejemplos de cURL para testing:

### 1. Medicamento completo con alta confianza (semantic_search):
curl -X POST "http://localhost:9088/api/medication/register-enriched" \
  -H "Content-Type: application/json" \
  -d '{
    "medication_data": {
      "medication_name": "Bronpax",
      "common_denomination": "Ambroxol",
      "concentration": "7.5 mg/mL",
      "form": "Solución oral",
      "form_simple": "Gotas",
      "brand_name": "FARMINDUSTRIA",
      "country": "PERÚ",
      "presentation": "20mL",
      "product_type": "PRODUCTO FARMACEUTICO",
      "fractions": "1"
    },
    "gtin_code": "7750304964586",
    "enrichment_source": "semantic_search",
    "enrichment_confidence": 0.87,
    "user_approved": true
  }'

### 2. Medicamento con datos mínimos (OCR extraction):
curl -X POST "http://localhost:9088/api/medication/register-enriched" \
  -H "Content-Type: application/json" \
  -d '{
    "medication_data": {
      "medication_name": "Paracetamol 500mg",
      "common_denomination": "Paracetamol",
      "concentration": "500 mg",
      "form_simple": "Tabletas"
    },
    "gtin_code": "1234567890123",
    "enrichment_source": "ocr_extraction",
    "enrichment_confidence": 0.65,
    "user_approved": true
  }'

### 3. Medicamento enriquecido desde BD GTIN existente:
curl -X POST "http://localhost:9088/api/medication/register-enriched" \
  -H "Content-Type: application/json" \
  -d '{
    "medication_data": {
      "medication_name": "Ibuprofeno",
      "common_denomination": "Ibuprofeno",
      "concentration": "400 mg",
      "form": "Tableta recubierta",
      "form_simple": "Tabletas",
      "brand_name": "LABORATORIO XYZ",
      "country": "COLOMBIA",
      "presentation": "10 tabletas",
      "product_type": "PRODUCTO FARMACEUTICO",
      "fractions": "1"
    },
    "gtin_code": "9876543210987",
    "enrichment_source": "database_gtin",
    "enrichment_confidence": 0.95,
    "user_approved": true
  }'

### 4. Registrar SKU de medicamento:
curl -X POST "http://localhost:9088/api/medication/register-sku" \
  -H "Content-Type: application/json" \
  -d '{
    "item_gtin_id": 11535,
    "gtin_code": "7750304964586",
    "lot_number": "LT240815",
    "expiration_date": "2025-12-01",
    "quantity": 100,
    "price": 15.50,
    "pharmacy_id": 1,
    "uploader_id": 1,
    "received_date": "2024-01-15",
    "code": "SKU001",
    "description": "Lote de prueba",
    "is_active": true
  }'

### 5. SKU con datos mínimos:
curl -X POST "http://localhost:9088/api/medication/register-sku" \
  -H "Content-Type: application/json" \
  -d '{
    "item_gtin_id": 11535,
    "gtin_code": "7750304964586",
    "lot_number": "LOTE2024",
    "expiration_date": "2026-05-01",
    "quantity": 50,
    "price": 12.00,
    "pharmacy_id": 1,
    "uploader_id": 1
  }'
"""


