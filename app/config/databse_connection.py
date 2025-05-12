import logging
import os
from typing import Dict, Any, Optional, List, Union
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()


class GtinDatabaseConnection:
    """Clase para manejar conexiones a la base de datos GTIN."""

    _instance = None  # Patrón Singleton

    @classmethod
    def get_instance(cls):
        """Obtiene la instancia única de la conexión a la base de datos."""
        if cls._instance is None:
            cls._instance = GtinDatabaseConnection()
        return cls._instance

    def __init__(self):
        """Inicializa la conexión para consulta de códigos GTIN."""
        # Parámetros de conexión desde variables de entorno
        self.server = os.getenv("DB_SERVER", "")
        self.database = os.getenv("DB_NAME", "")
        self.username = os.getenv("DB_USER", "")
        self.password = os.getenv("DB_PASSWORD", "")
        self.port = int(os.getenv("DB_PORT", "1433"))

        # Conexión completa desde variable de entorno (prioridad si está definida)
        self.connection_string = os.getenv("DB_CONNECTION_STRING", "")

        # Registrar información de conexión (sin contraseña)
        logger.info(
            f"Inicializando conexión GTIN con pyodbc: {self.server}:{self.port}, DB={self.database}, User={self.username}")

        self.connection = None

    def connect(self):
        """Establece la conexión a la base de datos SQL Server usando pyodbc."""
        try:
            if self.connection is None or not self.is_connected():
                logger.info("Estableciendo conexión con la base de datos para consulta de GTIN usando pyodbc...")

                import pyodbc

                # Usar la cadena de conexión completa si está disponible
                if self.connection_string:
                    self.connection = pyodbc.connect(self.connection_string)
                else:
                    # Construir la cadena de conexión con los parámetros individuales
                    conn_str = (
                        f"Driver={{ODBC Driver 17 for SQL Server}};"
                        f"Server=tcp:{self.server},{self.port};"
                        f"Database={self.database};"
                        f"Uid={self.username};"
                        f"Pwd={self.password};"
                        f"Encrypt=yes;"
                        f"TrustServerCertificate=no;"
                        f"Connection Timeout=30;"
                    )
                    self.connection = pyodbc.connect(conn_str)

                logger.info("Conexión a la base de datos GTIN establecida exitosamente")
            return self.connection
        except ImportError:
            logger.error("No se pudo importar pyodbc. Instálelo con: pip install pyodbc")
            raise
        except Exception as e:
            logger.error(f"Error al conectar con la base de datos usando pyodbc: {str(e)}")
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
            logger.info("Conexión GTIN cerrada")

    def execute_query(self, query, params=None):
        """Ejecuta una consulta SQL y devuelve los resultados."""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            logger.debug(f"Ejecutando consulta: {query}")
            if params:
                logger.debug(f"Con parámetros: {params}")
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Si la consulta es SELECT, procesar resultados
            if query.strip().upper().startswith("SELECT"):
                columns = [column[0] for column in cursor.description]
                results = []

                for row in cursor.fetchall():
                    # Convertir cada fila a un diccionario
                    results.append(dict(zip(columns, row)))

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
        try:
            query = "SELECT TOP 1 COUNT(*) AS count FROM registroclinico.ItemsGtin"
            result = self.execute_query(query)

            if result and len(result) > 0:
                count = result[0].get('count', 0)
                return count > 0
            return False
        except Exception as e:
            logger.error(f"Error al verificar datos en registroclinico.ItemsGtin: {str(e)}")
            return False


class GtinService:
    """Servicio para consultar información de medicamentos por código GTIN."""

    def __init__(self):
        """Inicializa el servicio con conexión a la base de datos."""
        self.db = GtinDatabaseConnection.get_instance()

    def query_gtin(self, gtin_code):
        """
        Consulta información de un medicamento por su código GTIN.

        Args:
            gtin_code: Código GTIN a consultar

        Returns:
            Diccionario con la información del medicamento o None si no se encuentra
        """
        logger.info(f"Consultando código GTIN: {gtin_code}")

        try:
            query = """
            SELECT TOP 1 
                GtinCode, 
                ItemId, 
                Name, 
                Description, 
                CategoryCode, 
                BrandName,
                ManufacturerName,
                ActiveIngredients
            FROM registroclinico.ItemsGtin 
            WHERE GtinCode = ?
            """

            results = self.db.execute_query(query, (gtin_code,))

            if results and len(results) > 0:
                return results[0]
            return None

        except Exception as e:
            logger.error(f"Error al consultar GTIN: {str(e)}")
            return None

    def search_products(self, search_term, limit=10):
        """
        Busca productos en la base de datos por término de búsqueda.

        Args:
            search_term: Término a buscar (nombre, marca, ingrediente activo)
            limit: Número máximo de resultados a devolver

        Returns:
            Lista de productos que coinciden con la búsqueda
        """
        try:
            query = f"""
            SELECT TOP {limit}
                GtinCode, 
                ItemId, 
                Name, 
                Description, 
                CategoryCode, 
                BrandName,
                ManufacturerName,
                ActiveIngredients
            FROM registroclinico.ItemsGtin 
            WHERE 
                Name LIKE ? OR 
                BrandName LIKE ? OR 
                ActiveIngredients LIKE ? OR
                Description LIKE ?
            ORDER BY Name
            """

            search_pattern = f"%{search_term}%"
            params = (search_pattern, search_pattern, search_pattern, search_pattern)

            results = self.db.execute_query(query, params)
            return results if results else []

        except Exception as e:
            logger.error(f"Error al buscar productos: {str(e)}")
            return []