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


class MedicationRegistrationResponse(BaseModel):
    """Respuesta del registro de medicamento"""
    status: str = Field(description="Estado de la operación", example="success")
    message: str = Field(description="Mensaje descriptivo", example="Medicamento registrado exitosamente")
    medication_id: Optional[int] = Field(None, description="ID del medicamento en la base de datos", example=12345)
    gtin_code: str = Field(description="Código GTIN registrado", example="7750304964586")
    registered_at: str = Field(description="Timestamp del registro", example="2024-01-15T10:30:00Z")


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
                        "form": None,
                        "form_simple": "Gotas",
                        "brand_name": None,
                        "country": None,
                        "presentation": "20mL",
                        "product_type": None,
                        "fractions": None,
                        "gtin_code": None
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
                    gtin_code=getattr(medication_obj, 'bar_code', None)  # bar_code -> gtin_code
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
        
        return MedicationExtractionResponse(
            status="success",
            message=f"Successfully processed {len(files)} medication images",
            results=ProcessingResult(**result)
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

### 🔍 **Flujo Simplificado:**
1. **Recibe datos**: Acepta directamente `MedicationData` del endpoint `/extract`
2. **Preparación automática**: Mapea y valida los campos requeridos
3. **Registro completo**: Inserta en BD con flag `IsAiGenerated = true`
4. **Vectorización automática**: Actualiza Qdrant para futuras búsquedas

### 📊 **Validaciones Automáticas:**
- Determina tipo de GTIN por longitud del código
- Verifica que el GTIN no exista previamente
- Valida campos obligatorios automáticamente
- Marca como generado por IA para auditoría

### 🛡️ **Seguridad y Trazabilidad:**
- Solo acepta medicamentos aprobados por usuario
- Mantiene metadatos de enriquecimiento completos
- Registra confianza del algoritmo de enriquecimiento
- Flag `IsAiGenerated` para diferencial de registros manuales
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
            registered_at=datetime.utcnow().isoformat() + "Z"
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


