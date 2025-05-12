import logging
import os
from typing import Dict, Any, Optional, List, Union
from dotenv import load_dotenv
import pymssql  # Usamos pymssql en lugar de pyodbc
import pandas as pd
from fastapi import Depends, HTTPException

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()


class GtinDatabaseConnection:
    """Clase para manejar la conexión a la base de datos SQL Server usando pymssql (alternativa a pyodbc)."""

    _instance = None  # Patrón Singleton

    @classmethod
    def get_instance(cls):
        """Obtiene la instancia única de la conexión a la base de datos."""
        if cls._instance is None:
            cls._instance = GtinDatabaseConnection()
        return cls._instance

    def __init__(self):
        """Inicializa la conexión a la base de datos usando pymssql."""
        # Parámetros de conexión desde variables de entorno o valores predeterminados
        self.server = os.getenv("DB_SERVER")
        self.database = os.getenv("DB_NAME")  # Asegúrate que este es el nombre correcto
        self.username = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.port = int(os.getenv("DB_PORT", "1433"))

        # Registrar información de conexión (sin contraseña)
        logger.info(
            f"Inicializando conexión GTIN con pymssql: {self.server}:{self.port}, DB={self.database}, User={self.username}")

        self.connection = None
        self.has_data = None  # Inicialmente desconocido

    def connect(self):
        """Establece la conexión a la base de datos usando pymssql."""
        try:
            if self.connection is None or not self.is_connected():
                logger.info("Estableciendo conexión con la base de datos para consulta de GTIN usando pymssql...")

                # Conectar usando pymssql
                self.connection = pymssql.connect(
                    server=self.server,
                    user=self.username,
                    password=self.password,
                    database=self.database,
                    port=self.port,
                    as_dict=True,  # Devuelve filas como diccionarios
                    charset='UTF-8'
                )

                logger.info("Conexión establecida exitosamente con pymssql")
            return self.connection
        except Exception as e:
            logger.error(f"Error al conectar con la base de datos usando pymssql: {str(e)}")
            import traceback
            logger.error(f"Detalles del error: {traceback.format_exc()}")
            raise

    def is_connected(self):
        """Verifica si la conexión está activa."""
        if self.connection is None:
            return False
        try:
            # Realizar una consulta simple para verificar la conexión
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1 AS test")
            cursor.fetchone()
            cursor.close()
            return True
        except:
            return False

    def disconnect(self):
        """Cierra la conexión a la base de datos."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Conexión cerrada")

    def execute_query(self, query, params=None):
        """Ejecuta una consulta SQL y devuelve los resultados."""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            logger.debug(f"Ejecutando consulta: {query}")
            if params:
                logger.debug(f"Con parámetros: {params}")

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Si la consulta es SELECT, procesar resultados
            if query.strip().upper().startswith("SELECT"):
                results = cursor.fetchall()
                logger.debug(f"Consulta devolvió {len(results)} resultados")
                return results
            else:
                # Para consultas que no devuelven resultados (INSERT, UPDATE, DELETE)
                conn.commit()
                return {"affected_rows": cursor.rowcount}
        except Exception as e:
            logger.error(f"Error al ejecutar consulta: {str(e)}")
            import traceback
            logger.error(f"Detalles del error: {traceback.format_exc()}")
            raise
        finally:
            if 'cursor' in locals():
                cursor.close()

    def check_has_data(self):
        """Verifica si la tabla ItemsGtin tiene datos."""
        # self.has_data ya no se usa aquí, se recalcula
        try:
            # Obtener el nombre de la base de datos de la instancia
            # Asegúrate de que self.database se inicialice correctamente en __init__
            target_database_name = 'solidaritymedicaldev_azure_db'
            if not target_database_name:
                logger.error("El nombre de la base de datos no está configurado en GtinDatabaseConnection.")
                return False

            # IMPORTANTE: CONECTAR SIN ESPECIFICAR LA BASE DE DATOS EN connect()
            # El método connect() debe estar modificado para NO pasar 'database=' a pymssql.connect()

            # Consulta con nombre completamente calificado
            query = f"SELECT COUNT(*) AS total FROM [registroclinico].[ItemsGtin]"

            logger.info(f"Ejecutando check_has_data con query: {query}")
            result = self.execute_query(
                query)  # execute_query usará la conexión ya establecida (o la creará sin DB específica)

            has_data_flag = result[0]["total"] > 0 if result else False
            logger.info(
                f"Verificación de datos en {target_database_name}.registroclinico.ItemsGtin: {'Con datos' if has_data_flag else 'Sin datos'}"
            )
            return has_data_flag
        except Exception as e:
            logger.error(f"Error al verificar datos en {self.database}.registroclinico.ItemsGtin: {str(e)}")
            # Considera relanzar el error o manejarlo de forma más específica
            return False


class GtinService:
    """Servicio para consulta y procesamiento de códigos GTIN."""

    def __init__(self):
        """Inicializa el servicio GTIN."""
        self.db = GtinDatabaseConnection.get_instance()

    def query_gtin(self, gtin_code: str) -> Optional[Dict[str, Any]]:
        """
        Consulta información detallada de un medicamento/producto utilizando su código GTIN.

        Args:
            gtin_code: El código GTIN o código de barras a consultar.

        Returns:
            Diccionario con la información del producto o None si no se encuentra.
        """
        try:
            logger.info(f"Consultando código GTIN: {gtin_code}")

            # Consulta SQL para buscar el código GTIN
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
                registroclinico.ItemsGtin
            WHERE 
                GtinCode = %s
            """  # Nota: pymssql usa %s en lugar de ? como marcador de posición

            # Ejecutar la consulta
            results = self.db.execute_query(query, (gtin_code,))

            # Procesar el resultado
            if not results:
                logger.info(f"No se encontró ningún producto con el código GTIN '{gtin_code}'.")
                return None

            # Devolver el primer resultado (debería ser único por código GTIN)
            logger.info(f"Se encontró producto para GTIN '{gtin_code}': {results[0]['Name']}")
            return results[0]

        except Exception as e:
            logger.error(f"Error al consultar GTIN: {str(e)}")
            raise

    def search_products(self, query_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Busca productos que coincidan con el texto de búsqueda.

        Args:
            query_text: Texto para buscar en nombre, denominación común, etc.
            limit: Límite de resultados a devolver.

        Returns:
            Lista de productos que coinciden con la búsqueda.
        """
        try:
            logger.info(f"Buscando productos con: '{query_text}'")

            # Preparar los parámetros con comodines para búsqueda parcial
            search_term = f"%{query_text}%"

            # Consulta SQL con búsqueda parcial en varios campos
            # Nota: pymssql usa %s en lugar de ? como marcador de posición
            search_query = """
            SELECT TOP %d
                Id,
                GtinCode,
                GtinCodeType,
                PharmacyType,
                ProductType,
                Name,
                CommonDenomination,
                Concentration,
                Form,
                BrandName,
                Presentation
            FROM 
                registroclinico.ItemsGtin
            WHERE 
                Name LIKE %s OR
                CommonDenomination LIKE %s OR
                BrandName LIKE %s OR
                GtinCode LIKE %s
            ORDER BY 
                Name
            """

            # Ejecutar la consulta
            results = self.db.execute_query(search_query, (limit, search_term, search_term, search_term, search_term))

            logger.info(f"Se encontraron {len(results)} productos para '{query_text}'")
            return results

        except Exception as e:
            logger.error(f"Error en búsqueda de productos: {str(e)}")
            raise


# Función para integrar con el workflow de procesamiento de imágenes
async def check_gtin_in_database(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Modified node for workflow that verifies if extracted barcodes are in the GTIN database.
    Now properly handles both 'barcode' and 'bar_code' fields from processed medications.

    Args:
        state: Current workflow state with processed medication data

    Returns:
        Updated state with enriched product information if found in database
    """
    try:
        logger.info("Checking medication barcodes in GTIN database")

        # Get processed medications
        processed_medications = state.get("processed_medications", [])
        if not processed_medications:
            logger.warning("No processed medications found to check GTIN codes")
            return state

        # Initialize GTIN service
        gtin_service = GtinService()

        # Check if database has data
        db = GtinDatabaseConnection.get_instance()
        has_data = db.check_has_data()
        logger.info(f"GTIN database has data: {has_data}")

        if not has_data:
            logger.info("GTIN database has no data, continuing without enrichment")
            return state

        # Store found products
        found_products = []

        # Process each medication
        for medication in processed_medications:
            # Try multiple possible field names for barcode
            # This handles different formats from OCR extraction
            medication_code = None

            # Check all possible barcode field names
            for field_name in ['barcode', 'bar_code', 'medication_code', 'code']:
                if field_name in medication and medication[field_name]:
                    medication_code = medication[field_name]
                    logger.info(f"Found medication code in field '{field_name}': {medication_code}")
                    break

            # If medication is a MedicationDetailsModel object and has bar_code attribute
            if hasattr(medication, 'bar_code') and getattr(medication, 'bar_code'):
                medication_code = getattr(medication, 'bar_code')
                logger.info(f"Found medication code in object attribute 'bar_code': {medication_code}")

            if medication_code:
                # Clean the barcode
                clean_code = medication_code.strip().replace('-', '').replace(' ', '')

                # Check if it's a valid numeric barcode of proper length
                if clean_code.isdigit() and len(clean_code) in [8, 12, 13, 14]:
                    # Query database
                    product = gtin_service.query_gtin(clean_code)

                    if product:
                        logger.info(f"Found GTIN in database: {clean_code} - {product['Name']}")
                        # Add product to list
                        found_products.append(product)

                        # Enrich medication with database info
                        medication["database_info"] = product

                        # Make sure bar_code is consistently available
                        medication["bar_code"] = clean_code
            else:
                logger.debug(f"No barcode found for medication: {medication.get('medication_name', 'Unknown')}")

        # Update state
        if found_products:
            logger.info(f"Found {len(found_products)} products in GTIN database")
            return {
                **state,
                "gtin_products": found_products,
                "gtin_found": True
            }
        else:
            logger.info("No GTIN codes found in database for processed medications")
            return {
                **state,
                "gtin_found": False
            }

    except Exception as e:
        logger.error(f"Error checking GTIN in database: {str(e)}")
        # Don't interrupt workflow, log error and continue
        return {
            **state,
            "gtin_error": str(e),
            "gtin_found": False
        }


# FastAPI Dependency para obtener el servicio GTIN
def get_gtin_service():
    """Dependency para obtener el servicio GTIN en FastAPI endpoints."""
    return GtinService()