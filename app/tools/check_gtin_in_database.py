import logging
import os
import time
from typing import Dict, Any, Optional, List, Union
from dotenv import load_dotenv
import pymssql
import pandas as pd
from fastapi import Depends, HTTPException

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants for connection retry
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


class GtinDatabaseConnection:
    """Class to handle SQL Server database connection using pymssql (alternative to pyodbc)."""

    _instance = None  # Singleton pattern

    @classmethod
    def get_instance(cls):
        """Get the singleton instance of the database connection."""
        if cls._instance is None:
            cls._instance = GtinDatabaseConnection()
        return cls._instance

    def __init__(self):
        """Initialize the database connection using pymssql."""
        # Connection parameters from environment variables or default values
        self.server = os.getenv("DB_SERVER")
        self.database = os.getenv("DB_NAME")
        self.username = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.port = int(os.getenv("DB_PORT", "1433"))
        self.connection_timeout = int(os.getenv("DB_CONNECTION_TIMEOUT", "30"))

        # Log connection info (without password)
        logger.info(
            f"Initializing GTIN connection with pymssql: {self.server}:{self.port}, DB={self.database}, User={self.username}")

        self.connection = None
        self.last_connection_time = 0
        self.connection_max_age = int(os.getenv("DB_CONNECTION_MAX_AGE", "300"))  # 5 minutes default

    def connect(self, force_new=False):
        """
        Establish connection to the database using pymssql with retry logic.

        Args:
            force_new: Force creation of a new connection even if one exists

        Returns:
            Active database connection
        """
        try:
            current_time = time.time()

            # Check if we need a new connection
            if (self.connection is None or
                    not self.is_connected() or
                    force_new or
                    (current_time - self.last_connection_time) > self.connection_max_age):

                # Close any existing connection
                if self.connection is not None:
                    try:
                        self.connection.close()
                    except:
                        pass
                    self.connection = None

                logger.info("Establishing connection to database for GTIN query using pymssql...")

                # Try to connect with retries
                retry_count = 0
                last_exception = None

                while retry_count < MAX_RETRIES:
                    try:
                        # Connect using pymssql with timeout
                        self.connection = pymssql.connect(
                            server=self.server,
                            user=self.username,
                            password=self.password,
                            database=self.database,
                            port=self.port,
                            as_dict=True,  # Return rows as dictionaries
                            charset='UTF-8',
                            timeout=self.connection_timeout,
                            login_timeout=self.connection_timeout
                        )

                        # Update last connection time
                        self.last_connection_time = time.time()
                        logger.info("Connection established successfully with pymssql")
                        break

                    except Exception as e:
                        last_exception = e
                        retry_count += 1
                        logger.warning(f"Connection attempt {retry_count} failed: {str(e)}")

                        if retry_count < MAX_RETRIES:
                            logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                            time.sleep(RETRY_DELAY)
                        else:
                            logger.error(f"Failed to connect after {MAX_RETRIES} attempts")
                            raise

            return self.connection

        except Exception as e:
            logger.error(f"Error connecting to database using pymssql: {str(e)}")
            import traceback
            logger.error(f"Error details: {traceback.format_exc()}")
            raise

    def is_connected(self):
        """Check if the connection is active."""
        if self.connection is None:
            return False
        try:
            # Run a simple query to verify connection
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1 AS test")
            cursor.fetchone()
            cursor.close()
            return True
        except:
            return False

    def disconnect(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Connection closed")

    def execute_query(self, query, params=None):
        """Execute a SQL query and return the results with retry logic."""
        retry_count = 0
        last_exception = None

        while retry_count < MAX_RETRIES:
            try:
                conn = self.connect(force_new=(retry_count > 0))
                cursor = conn.cursor()

                logger.debug(f"Executing query: {query}")
                if params:
                    logger.debug(f"With parameters: {params}")

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                # If query is SELECT, process results
                if query.strip().upper().startswith("SELECT"):
                    results = cursor.fetchall()
                    logger.debug(f"Query returned {len(results)} results")
                    return results
                else:
                    # For queries that don't return results (INSERT, UPDATE, DELETE)
                    conn.commit()
                    return {"affected_rows": cursor.rowcount}

            except Exception as e:
                last_exception = e
                retry_count += 1
                logger.warning(f"Query execution attempt {retry_count} failed: {str(e)}")

                # Close connection on error to ensure clean state for retry
                self.disconnect()

                if retry_count < MAX_RETRIES:
                    logger.info(f"Retrying query in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Failed to execute query after {MAX_RETRIES} attempts")
                    logger.error(f"Error executing query: {str(e)}")
                    import traceback
                    logger.error(f"Error details: {traceback.format_exc()}")
                    raise
            finally:
                if 'cursor' in locals() and cursor is not None:
                    cursor.close()

    def check_has_data(self):
        """Check if the ItemsGtin table has data with better error handling."""
        try:
            target_database_name = 'solidaritymedicaldev_azure_db'
            if not target_database_name:
                logger.error("Database name not configured in GtinDatabaseConnection.")
                return False

            # Use try-except to handle database availability issues
            try:
                # Query with fully qualified name
                query = f"SELECT COUNT(*) AS total FROM [registroclinico].[ItemsGtin]"

                logger.info(f"Executing check_has_data with query: {query}")
                result = self.execute_query(query)

                has_data_flag = result[0]["total"] > 0 if result else False
                logger.info(
                    f"Data verification in {target_database_name}.registroclinico.ItemsGtin: {'Has data' if has_data_flag else 'No data'}"
                )
                return has_data_flag

            except Exception as db_error:
                # Log the specific error but return False instead of raising
                logger.error(f"Database error in check_has_data: {str(db_error)}")
                return False

        except Exception as e:
            logger.error(f"Error checking data in {self.database}.registroclinico.ItemsGtin: {str(e)}")
            return False


class GtinService:
    """Service for querying and processing GTIN codes."""

    def __init__(self):
        """Initialize the GTIN service."""
        self.db = GtinDatabaseConnection.get_instance()

    def query_gtin(self, gtin_code: str) -> Optional[Dict[str, Any]]:
        """
        Query detailed information about a medication/product using its GTIN code.

        Args:
            gtin_code: The GTIN or barcode to query.

        Returns:
            Dictionary with product information or None if not found.
        """
        try:
            logger.info(f"Querying GTIN code: {gtin_code}")

            # SQL query to find the GTIN code
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
            """  # Note: pymssql uses %s instead of ? as placeholder

            # Execute the query
            results = self.db.execute_query(query, (gtin_code,))

            # Process the result
            if not results:
                logger.info(f"No product found with GTIN code '{gtin_code}'.")
                return None

            # Return the first result (should be unique by GTIN code)
            logger.info(f"Product found for GTIN '{gtin_code}': {results[0]['Name']}")
            return results[0]

        except Exception as e:
            logger.error(f"Error querying GTIN: {str(e)}")
            # Return None instead of raising to avoid workflow interruption
            return None

    def search_products(self, query_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for products matching the search text.

        Args:
            query_text: Text to search in name, common denomination, etc.
            limit: Limit of results to return.

        Returns:
            List of products matching the search.
        """
        try:
            logger.info(f"Searching products with: '{query_text}'")

            # Prepare parameters with wildcards for partial search
            search_term = f"%{query_text}%"

            # SQL query with partial search in multiple fields
            # Note: pymssql uses %s instead of ? as placeholder
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

            # Execute the query
            results = self.db.execute_query(search_query, (limit, search_term, search_term, search_term, search_term))

            logger.info(f"Found {len(results)} products for '{query_text}'")
            return results

        except Exception as e:
            logger.error(f"Error in product search: {str(e)}")
            # Return empty list instead of raising to avoid workflow interruption
            return []


async def check_gtin_in_database_v3(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simplified workflow node that checks if the extracted barcode is in the database.

    Args:
        state: Current workflow state with processed medication data

    Returns:
        Updated state with database information if barcode found
    """
    logger.info("Checking medication barcodes in GTIN database")

    # Get processed medications - handle as a single item, not a list
    processed_medication = state["processed_medications"]
    logger.info(f"processed_medications: {processed_medication}")
    # Initialize GTIN service
    gtin_service = GtinService()
    db = GtinDatabaseConnection.get_instance()
    has_data = db.check_has_data()
    logger.info(f"GTIN database has data: {has_data}")

    # Extract barcode - directly access bar_code attribute
    # barcode = processed_medication.bar_code
    # logger.info(f"GTIN database has data: {barcode}")
    # Clean barcode and query database
    # clean_code = barcode.strip().replace('-', '').replace(' ', '')
    # product = gtin_service.query_gtin(clean_code)
    # Process info stata
    # processed_medication = state["processed_medications"]
    # logger.info(f"processed_medications: {processed_medication}")
    product_info_from_db = None
    gtin_found_for_this_item = False

    if processed_medication.bar_code:
        clean_code = processed_medication.bar_code.strip().replace('-', '').replace(' ', '')
        if clean_code.isdigit() and len(clean_code) in [8, 12, 13, 14]:
            logger.info(f"Querying database for clean GTIN: {clean_code}")
            db_result = gtin_service.query_gtin(clean_code)  # Renombrado para claridad

            if db_result:
                product_info_from_db = db_result  # Guardamos la info cruda para el estado
                gtin_found_for_this_item = True
                logger.info(f"GTIN {clean_code} found in DB: {db_result.get('Name')}")

                # --- ENRICHMENT LOGIC ---
                if db_result.get("Name"):
                    processed_medication.medication_name = db_result["Name"]
                if db_result.get("CommonDenomination"):
                    processed_medication.common_denomination = db_result["CommonDenomination"]
                if db_result.get("Concentration"):
                    processed_medication.concentration = db_result["Concentration"]
                if db_result.get("Form"):
                    processed_medication.form = db_result["Form"]
                if db_result.get("FormSimple"):
                    processed_medication.form_simple = db_result["FormSimple"]
                if db_result.get("BrandName"):
                    processed_medication.brand_name = db_result["BrandName"]
                if db_result.get("Country"):
                    processed_medication.country = db_result["Country"]
                if db_result.get("Presentation"):
                    processed_medication.presentation = db_result["Presentation"]
                if db_result.get("Fractions") is not None:  # Puede ser numérico o string
                    processed_medication.fractions = str(db_result["Fractions"])

                # Campos que vienen principalmente de la BD
                if db_result.get("ProductType"):
                    processed_medication.product_type = db_result["ProductType"]
                # if db_result.get("CodeRsList"):
                #     processed_medication.code_rs_list = db_result["CodeRsList"]
                # if db_result.get("State"):  # 'State' de la tabla ItemsGtin
                #     processed_medication.product_status_in_db = db_result["State"]

                # Los campos lot_number y expiration_date se mantienen del OCR
                # a menos que tengas una lógica específica para actualizarlos desde la BD (raro).

                logger.info(f"Enriched processed_medications: {processed_medication.model_dump_json(indent=2)}")
            else:
                logger.info(f"GTIN {clean_code} NOT found in DB.")
        else:
            logger.warning(f"Barcode '{processed_medication.bar_code}' is not valid for DB query.")
    else:
        logger.warning("No barcode present in processed_medications to query.")

    return {
        "processed_medications": processed_medication,
        "database_info": product_info_from_db,
        "gtin_found": gtin_found_for_this_item
    }

async def check_gtin_in_database(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Workflow node that checks if the sing to use the structured medication_code.

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
            logger.warning("No processed medications to check GTIN codes")
            return state

        # GTIN service
        gtin_service = GtinService()

        # Check if database has data
        db = GtinDatabaseConnection.get_instance()

        # Use try-except to gracefully handle database unavailability
        try:
            has_data = db.check_has_data()
            logger.info(f"GTIN database has data: {has_data}")
        except Exception as db_error:
            logger.error(f"Error checking database: {str(db_error)}")
            # Continue workflow even if database check fails
            return {
                **state,
                "gtin_error": str(db_error),
                "gtin_found": False
            }

        if not has_data:
            logger.info("GTIN database has no data, continuing without enrichment")
            return {
                **state,
                "gtin_found": False
            }

        # List to store found products
        found_products = []

        # Process each medication - handle both dict and object formats
        medications_to_process = []

        # Handle different potential formats of the processed_medications
        if isinstance(processed_medications, list):
            medications_to_process = processed_medications
        elif isinstance(processed_medications, dict):
            medications_to_process = [processed_medications]
        else:
            # Might be a Pydantic model or other object
            medications_to_process = [processed_medications]

        for medication in medications_to_process:
            # Try all possible barcode field names
            medication_code = None

            # For dict-like access
            if hasattr(medication, 'get') and callable(getattr(medication, 'get')):
                # Check all possible barcode field names for dict-like objects
                for field_name in ['barcode', 'bar_code', 'medication_code', 'code', 'gtin']:
                    if medication.get(field_name):
                        medication_code = medication.get(field_name)
                        logger.info(f"Found medication code in field '{field_name}': {medication_code}")
                        break

            # For object attribute access
            else:
                # Check all possible barcode field names for object attributes
                for field_name in ['barcode', 'bar_code', 'medication_code', 'code', 'gtin']:
                    if hasattr(medication, field_name) and getattr(medication, field_name):
                        medication_code = getattr(medication, field_name)
                        logger.info(f"Found medication code in object attribute '{field_name}': {medication_code}")
                        break

            # If still no code found, try __dict__ approach as fallback
            if medication_code is None and hasattr(medication, '__dict__'):
                med_dict = medication.__dict__
                for field_name in ['barcode', 'bar_code', 'medication_code', 'code', 'gtin']:
                    if field_name in med_dict and med_dict[field_name]:
                        medication_code = med_dict[field_name]
                        logger.info(f"Found medication code in __dict__ '{field_name}': {medication_code}")
                        break

            if medication_code:
                # Clean the barcode
                clean_code = medication_code.strip().replace('-', '').replace(' ', '')

                # Check if it's a valid numeric barcode of appropriate length
                if clean_code.isdigit() and len(clean_code) in [8, 12, 13, 14]:
                    try:
                        # Query database
                        product = gtin_service.query_gtin(clean_code)

                        if product:
                            logger.info(f"Found GTIN in database: {clean_code} - {product['Name']}")
                            # Add product to list
                            found_products.append(product)

                            # Try to enrich the medication with database info
                            try:
                                if hasattr(medication, 'get') and callable(getattr(medication, 'get')):
                                    # Dict-like object - use update if available
                                    if hasattr(medication, 'update') and callable(getattr(medication, 'update')):
                                        medication.update({"database_info": product})
                                    else:
                                        medication["database_info"] = product
                                elif hasattr(medication, '__dict__'):
                                    # Object with attributes
                                    setattr(medication, 'database_info', product)
                            except Exception as attr_error:
                                logger.warning(f"Could not attach database_info: {str(attr_error)}")
                    except Exception as query_error:
                        logger.error(f"Error querying GTIN {clean_code}: {str(query_error)}")
                        # Continue with other medications
                        continue
            else:
                med_name = "Unknown"
                # Try to get medication name for better logging
                if hasattr(medication, 'get') and callable(getattr(medication, 'get')):
                    med_name = medication.get('medication_name', "Unknown")
                elif hasattr(medication, 'medication_name'):
                    med_name = medication.medication_name

                logger.debug(f"No barcode found for medication: {med_name}")

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

# FastAPI Dependency for getting GTIN service
def get_gtin_service():
    """Dependency to get GTIN service in FastAPI endpoints."""
    return GtinService()