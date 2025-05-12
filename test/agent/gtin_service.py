import unittest
import sys
import os
import logging
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Añadir directorio raíz al path para poder importar módulos de la aplicación
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Cargar variables de entorno antes de importar el servicio
load_dotenv()

# Intentar importar después de configurar el entorno
try:
    from app.tools.check_gtin_in_database import GtinDatabaseConnection, GtinService
except Exception as e:
    logger.error(f"Error al importar módulos: {str(e)}")
    raise


class TestGtinConnection(unittest.TestCase):
    """Pruebas para la conexión a la base de datos GTIN"""

    def setUp(self):
        """Configuración inicial para las pruebas"""
        try:
            # Crear instancia de conexión
            self.db_connection = GtinDatabaseConnection.get_instance()
            self.gtin_service = GtinService()

            # Imprimir información de conexión (ocultar contraseña para seguridad)
            connection_info = (
                f"Servidor: {self.db_connection.server}, "
                f"Puerto: {self.db_connection.port}, "
                f"BD: {self.db_connection.database}, "
                f"Usuario: {self.db_connection.username}"
            )
            logger.info(f"Información de conexión: {connection_info}")

        except Exception as e:
            logger.error(f"Error en setUp: {str(e)}")
            raise

    def test_connection(self):
        """Prueba básica de conexión a la base de datos"""
        try:
            # Intentar establecer conexión
            conn = self.db_connection.connect()
            self.assertIsNotNone(conn, "La conexión no debería ser None")

            # Verificar que está conectado
            is_connected = self.db_connection.is_connected()
            self.assertTrue(is_connected, "La conexión debería estar activa")

            logger.info("Conexión a la base de datos establecida correctamente")
        except Exception as e:
            logger.error(f"Error en test_connection: {str(e)}")
            self.fail(f"La prueba de conexión falló con error: {str(e)}")
        finally:
            # Cerrar conexión si existe
            self.db_connection.disconnect()

    def test_check_has_data(self):
        """Prueba la verificación de datos en la tabla ItemsGtin"""
        try:
            # Verificar si hay datos
            has_data = self.db_connection.check_has_data()

            # No afirmamos un resultado específico, solo registramos el resultado
            logger.info(f"Verificación de datos en ItemsGtin: {'Con datos' if has_data else 'Sin datos'}")

            # Probar si la consulta se ejecuta sin errores
            query = "SELECT TOP 1 * FROM registroclinico.ItemsGtin"
            result = self.db_connection.execute_query(query)

            if result:
                logger.info(f"Primera fila de ItemsGtin: {result[0]}")
            else:
                logger.warning("No se encontraron resultados en la tabla ItemsGtin")

        except Exception as e:
            logger.error(f"Error en test_check_has_data: {str(e)}")
            # Registrar el error pero no fallar la prueba, ya que queremos ver todos los detalles
            logger.error(f"Detalles del error: {str(e)}")

            # Intentar ejecutar una consulta simple para diagnosticar
            try:
                conn = self.db_connection.connect()
                cursor = conn.cursor()
                cursor.execute("SELECT 1 AS test")
                test_result = cursor.fetchone()
                logger.info(f"Consulta simple de prueba: {test_result}")
                cursor.close()
            except Exception as inner_e:
                logger.error(f"Error en consulta simple: {str(inner_e)}")

            self.fail(f"La prueba de verificación de datos falló con error: {str(e)}")

    def test_query_gtin(self):
        """Prueba la consulta de un código GTIN"""
        try:
            # Probar con un código GTIN de ejemplo (puede no existir)
            test_gtin = "7501287617019"  # Un código GTIN de ejemplo

            result = self.gtin_service.query_gtin(test_gtin)

            if result:
                logger.info(f"Producto encontrado para GTIN '{test_gtin}': {result['Name']}")
            else:
                logger.info(f"No se encontró ningún producto con el código GTIN '{test_gtin}'")

            # Probar la búsqueda de productos
            search_term = "PARACETAMOL"
            search_results = self.gtin_service.search_products(search_term, limit=5)

            logger.info(f"Búsqueda de '{search_term}' devolvió {len(search_results)} resultados")

            if search_results:
                for i, product in enumerate(search_results[:3]):  # Mostrar solo los primeros 3 para no saturar el log
                    logger.info(
                        f"Producto {i + 1}: {product.get('Name', 'Sin nombre')} - {product.get('GtinCode', 'Sin GTIN')}")

        except Exception as e:
            logger.error(f"Error en test_query_gtin: {str(e)}")
            self.fail(f"La prueba de consulta GTIN falló con error: {str(e)}")


if __name__ == "__main__":
    logger.info("Iniciando pruebas de conexión GTIN...")
    unittest.main()