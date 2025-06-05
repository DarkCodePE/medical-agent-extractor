# app/services/medication_vector_service.py

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.tools.check_gtin_in_database import GtinDatabaseConnection, GtinService
import os

logger = logging.getLogger(__name__)
# Load environment variables
load_dotenv()


class MedicationVectorService:
    """
    Servicio para vectorización de medicamentos desde la tabla ItemsGtin.
    Permite búsquedas semánticas cuando no hay código GTIN disponible.
    """

    def __init__(self):
        """Inicializa el servicio con clientes necesarios."""
        try:
            QDRANT_URL = os.getenv("QDRANT_URL")
            QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

            # Initialize Qdrant client
            self.qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

            # Initialize OpenAI embeddings
            self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

            # 🔥 USAR LA MISMA CONEXIÓN DE BD QUE YA FUNCIONA
            self.db_connection = GtinDatabaseConnection.get_instance()
            self.gtin_service = GtinService()

            # Collection name for medication vectors
            self.collection_name = "medical_store"

            # Ensure collection exists
            self._ensure_collection_exists()

            logger.info("MedicationVectorService initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing MedicationVectorService: {str(e)}")
            raise

    def _ensure_collection_exists(self):
        """Asegura que la colección de vectores de medicamentos existe."""
        try:
            collections = self.qdrant_client.get_collections().collections
            collection_names = [collection.name for collection in collections]

            if self.collection_name not in collection_names:
                # Crear la colección con el tamaño apropiado para el modelo de embeddings
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=1536,  # Size for text-embedding-3-small
                        distance=models.Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
            else:
                logger.info(f"Qdrant collection already exists: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error ensuring Qdrant collection exists: {str(e)}")
            raise

    def _create_searchable_text(self, medication_data: Dict[str, Any]) -> str:
        """
        Crea un texto optimizado para búsqueda semántica a partir de los datos del medicamento.

        Args:
            medication_data: Datos del medicamento desde la BD

        Returns:
            Texto formateado para vectorización
        """
        # Extraer campos relevantes para búsqueda
        name = medication_data.get('Name', '').strip()
        common_denomination = medication_data.get('CommonDenomination', '').strip()
        concentration = medication_data.get('Concentration', '').strip()
        form = medication_data.get('Form', '').strip()
        form_simple = medication_data.get('FormSimple', '').strip()
        brand_name = medication_data.get('BrandName', '').strip()
        presentation = medication_data.get('Presentation', '').strip()
        product_type = medication_data.get('ProductType', '').strip()

        # Crear texto estructurado para mejor búsqueda semántica
        searchable_parts = []

        # Nombre principal (más peso en la búsqueda)
        if name:
            searchable_parts.append(f"Medicamento: {name}")

        # Ingrediente activo
        if common_denomination:
            searchable_parts.append(f"Principio activo: {common_denomination}")

        # Concentración
        if concentration:
            searchable_parts.append(f"Concentración: {concentration}")

        # Formas farmacéuticas
        if form:
            searchable_parts.append(f"Forma: {form}")
        if form_simple and form_simple != form:
            searchable_parts.append(f"Tipo: {form_simple}")

        # Marca
        if brand_name:
            searchable_parts.append(f"Marca: {brand_name}")

        # Presentación
        if presentation:
            searchable_parts.append(f"Presentación: {presentation}")

        # Tipo de producto
        if product_type:
            searchable_parts.append(f"Categoría: {product_type}")

        # Crear sinónimos y variaciones para mejor matching
        synonyms = []
        if 'comprimido' in form.lower():
            synonyms.append("tableta pastilla píldora")
        if 'jarabe' in form.lower():
            synonyms.append("líquido oral suspensión")
        if 'inyectable' in form.lower():
            synonyms.append("ampolla vial inyección")
        if 'colirio' in form_simple.lower():
            synonyms.append("gotas oftálmicas ojos")

        searchable_text = " | ".join(searchable_parts)
        if synonyms:
            searchable_text += " | Sinónimos: " + " ".join(synonyms)

        return searchable_text

    async def vectorize_all_medications(self, batch_size: int = 100) -> Dict[str, Any]:
        """
        Vectoriza todos los medicamentos de la tabla ItemsGtin en lotes.
        🔥 CORREGIDO: Problema con IDs de Qdrant

        Args:
            batch_size: Tamaño de lote para procesamiento

        Returns:
            Estadísticas del proceso de vectorización
        """
        try:
            logger.info("🚀 Iniciando vectorización de todos los medicamentos")

            # Verificar que la base de datos tenga datos
            if not self.db_connection.check_has_data():
                logger.warning("❌ Base de datos GTIN no tiene datos para vectorizar")
                return {"error": "No hay datos en la base de datos GTIN"}

            # 🔥 CONSULTA ACTUALIZADA - Usando la misma estructura que funciona
            logger.info("Consultando medicamentos desde [registroclinico].[ItemsGtin]...")

            query = """
            SELECT 
                Id,
                GtinCode,
                GtinCodeType,
                PharmacyType,
                ProductType,
                Name,
                CommonDenomination,
                Concentration,
                Form,
                FormSimple,
                BrandName,
                Country,
                Presentation,
                CodeRsList,
                Fractions,
                State
            FROM 
                [registroclinico].[ItemsGtin]
            WHERE 
                (State = 'ACTIVO' OR State IS NULL)
                AND Name IS NOT NULL 
                AND Name != ''
            ORDER BY Id
            """

            logger.info(f"Ejecutando consulta  SQL...")
            all_medications = self.db_connection.execute_query(query)
            total_medications = len(all_medications)

            logger.info(f"✅ Encontrados {total_medications} medicamentos para vectorizar")

            if total_medications == 0:
                return {"error": "No se encontraron medicamentos activos para vectorizar"}

            # Procesar en lotes
            points_to_upsert = []
            processed_count = 0
            failed_count = 0
            skipped_count = 0

            for i, medication in enumerate(all_medications):
                try:
                    # Validar que el medicamento tenga datos mínimos
                    if not medication.get('Name') or not medication.get('Name').strip():
                        skipped_count += 1
                        logger.debug(f"Skipping medication ID {medication.get('Id')} - no name")
                        continue

                    # Crear texto para búsqueda
                    searchable_text = self._create_searchable_text(medication)

                    if not searchable_text.strip():
                        skipped_count += 1
                        logger.debug(f"Skipping medication ID {medication.get('Id')} - no searchable text")
                        continue

                    # Generar embedding
                    vector = await self.embeddings.aembed_query(searchable_text)

                    # 🔥 CORREGIDO: Usar ID como entero en lugar de string
                    medication_id = int(medication['Id'])  # Convertir a entero

                    # Crear punto para Qdrant
                    point = models.PointStruct(
                        id=medication_id,  # 🔥 CORREGIDO: Usar entero en lugar de string
                        vector=vector,
                        payload={
                            "gtin_code": medication.get('GtinCode'),
                            "gtin_code_type": medication.get('GtinCodeType'),
                            "pharmacy_type": medication.get('PharmacyType'),
                            "product_type": medication.get('ProductType'),
                            "medication_name": medication.get('Name'),
                            "common_denomination": medication.get('CommonDenomination'),
                            "concentration": medication.get('Concentration'),
                            "form": medication.get('Form'),
                            "form_simple": medication.get('FormSimple'),
                            "brand_name": medication.get('BrandName'),
                            "country": medication.get('Country'),
                            "presentation": medication.get('Presentation'),
                            "code_rs_list": medication.get('CodeRsList'),
                            "fractions": medication.get('Fractions'),
                            "state": medication.get('State'),
                            "searchable_text": searchable_text,
                            "vectorized_at": datetime.utcnow().isoformat(),
                            "db_id": medication['Id']  # Mantener el ID original en el payload
                        }
                    )

                    points_to_upsert.append(point)
                    processed_count += 1

                    # Procesar lote cuando esté lleno
                    if len(points_to_upsert) >= batch_size:
                        await self._upsert_batch(points_to_upsert)
                        points_to_upsert = []
                        logger.info(f"📦 Procesado lote: {processed_count}/{total_medications} medicamentos")

                    # Log progreso cada 50 items
                    if (i + 1) % 50 == 0:
                        logger.info(f"🔄 Progreso: {i + 1}/{total_medications} medicamentos analizados")

                except Exception as e:
                    logger.error(f"❌ Error procesando medicamento ID {medication.get('Id')}: {str(e)}")
                    failed_count += 1
                    continue

            # Procesar lote final
            if points_to_upsert:
                await self._upsert_batch(points_to_upsert)
                logger.info(f"📦 Procesado lote final: {len(points_to_upsert)} medicamentos")

            logger.info(f"✅ Vectorización completada:")
            logger.info(f"   📈 Procesados exitosamente: {processed_count}")
            logger.info(f"   ❌ Fallos: {failed_count}")
            logger.info(f"   ⏩ Omitidos: {skipped_count}")
            logger.info(f"   📊 Total en BD: {total_medications}")

            return {
                "success": True,
                "total_in_database": total_medications,
                "total_processed": processed_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "collection_name": self.collection_name,
                "database_used": "solidaritymedicaldev_azure_db"
            }

        except Exception as e:
            logger.error(f"💥 Error en vectorización masiva: {str(e)}")
            import traceback
            logger.error(f"🔍 Stack trace: {traceback.format_exc()}")
            raise

    async def _upsert_batch(self, points: List[models.PointStruct]):
        """Inserta un lote de puntos en Qdrant."""
        try:
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.debug(f"✅ Insertado lote de {len(points)} puntos en Qdrant")
        except Exception as e:
            logger.error(f"❌ Error insertando lote en Qdrant: {str(e)}")
            raise

    async def search_medications_semantic(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Busca medicamentos usando búsqueda semántica.

        Args:
            query: Texto de búsqueda (nombre, ingrediente, etc.)
            limit: Número máximo de resultados

        Returns:
            Lista de medicamentos encontrados con scores de similitud
        """
        try:
            logger.info(f"🔍 Búsqueda semántica de medicamentos: '{query}'")

            # Crear embedding de la consulta
            query_vector = await self.embeddings.aembed_query(query)

            # Buscar en Qdrant
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=0.5  # Filtrar resultados con baja similitud
            )

            # Formatear resultados
            medications = []
            for result in search_results:
                payload = result.payload
                medications.append({
                    "db_id": payload.get("db_id"),
                    "gtin_code": payload.get("gtin_code"),
                    "gtin_code_type": payload.get("gtin_code_type"),
                    "pharmacy_type": payload.get("pharmacy_type"),
                    "product_type": payload.get("product_type"),
                    "medication_name": payload.get("medication_name"),
                    "common_denomination": payload.get("common_denomination"),
                    "concentration": payload.get("concentration"),
                    "form": payload.get("form"),
                    "form_simple": payload.get("form_simple"),
                    "brand_name": payload.get("brand_name"),
                    "country": payload.get("country"),
                    "presentation": payload.get("presentation"),
                    "code_rs_list": payload.get("code_rs_list"),
                    "fractions": payload.get("fractions"),
                    "state": payload.get("state"),
                    "similarity_score": result.score,
                    "search_method": "semantic",
                    "vectorized_at": payload.get("vectorized_at")
                })

            logger.info(f"✅ Encontrados {len(medications)} medicamentos por búsqueda semántica")
            return medications

        except Exception as e:
            logger.error(f"❌ Error en búsqueda semántica: {str(e)}")
            return []

    def get_collection_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas de la colección de vectores."""
        try:
            collection_info = self.qdrant_client.get_collection(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "vectors_count": collection_info.vectors_count,
                "status": collection_info.status,
                "config": {
                    "vector_size": collection_info.config.params.vectors.size,
                    "distance": collection_info.config.params.vectors.distance
                },
                "database_source": "solidaritymedicaldev_azure_db"
            }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {str(e)}")
            return {"error": str(e)}

    async def update_medication_vector(self, gtin_code: str) -> bool:
        """
        Actualiza el vector de un medicamento específico.
        🔥 CORREGIDO: Problema con IDs de Qdrant

        Args:
            gtin_code: Código GTIN del medicamento a actualizar

        Returns:
            True si se actualizó exitosamente
        """
        try:
            # Obtener datos actualizados de la BD
            medication_data = self.gtin_service.query_gtin(gtin_code)

            if not medication_data:
                logger.warning(f"No se encontró medicamento con GTIN: {gtin_code}")
                return False

            # Crear texto actualizado
            searchable_text = self._create_searchable_text(medication_data)

            # Generar nuevo embedding
            vector = await self.embeddings.aembed_query(searchable_text)

            # 🔥 CORREGIDO: Usar ID como entero
            medication_id = int(medication_data['Id'])

            # Actualizar en Qdrant
            point = models.PointStruct(
                id=medication_id,  # 🔥 CORREGIDO: Entero en lugar de string
                vector=vector,
                payload={
                    "gtin_code": medication_data.get('GtinCode'),
                    "gtin_code_type": medication_data.get('GtinCodeType'),
                    "pharmacy_type": medication_data.get('PharmacyType'),
                    "product_type": medication_data.get('ProductType'),
                    "medication_name": medication_data.get('Name'),
                    "common_denomination": medication_data.get('CommonDenomination'),
                    "concentration": medication_data.get('Concentration'),
                    "form": medication_data.get('Form'),
                    "form_simple": medication_data.get('FormSimple'),
                    "brand_name": medication_data.get('BrandName'),
                    "country": medication_data.get('Country'),
                    "presentation": medication_data.get('Presentation'),
                    "code_rs_list": medication_data.get('CodeRsList'),
                    "fractions": medication_data.get('Fractions'),
                    "state": medication_data.get('State'),
                    "searchable_text": searchable_text,
                    "updated_at": datetime.utcnow().isoformat(),
                    "db_id": medication_data['Id']
                }
            )

            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )

            logger.info(f"✅ Actualizado vector para medicamento GTIN: {gtin_code}")
            return True

        except Exception as e:
            logger.error(f"❌ Error actualizando vector: {str(e)}")
            return False