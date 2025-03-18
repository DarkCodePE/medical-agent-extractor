# app/db/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker, Session
import os
from dotenv import load_dotenv
from psycopg2 import connect, sql

# Determinar el entorno actual
environment = os.getenv("ENVIRONMENT", "development")
# Cargar el archivo .env adecuado
if environment == "production":
    load_dotenv(".env.prod")
else:
    load_dotenv(".env")

# Configuración de la base de datos
POSTGRES_HOST = os.getenv("DB_HOST", "localhost")
POSTGRES_PORT = os.getenv("DB_PORT", "5432")
POSTGRES_DB = os.getenv("DB_NAME")
POSTGRES_USER = os.getenv("DB_USER")
POSTGRES_PASSWORD = os.getenv("DB_PASSWORD")

# Parámetros del pool
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", 5))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", 10))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", 30))


def create_database_if_not_exists():
    """Crea la base de datos si no existe"""
    conn = connect(
        dbname="postgres",
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT
    )
    conn.autocommit = True
    cursor = conn.cursor()

    cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{POSTGRES_DB}'")
    exists = cursor.fetchone()

    if not exists:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(
            sql.Identifier(POSTGRES_DB)
        ))
        print(f"Base de datos '{POSTGRES_DB}' creada con éxito.")
    else:
        print(f"La base de datos '{POSTGRES_DB}' ya existe.")

    cursor.close()
    conn.close()


# URL de la base de datos
SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
# URL de la base de datos
SQLALCHEMY_DATABASE_URL_ASYNC = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Configuración del engine y creación de la sesión
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Crear el motor asíncrono
async_engine = create_async_engine(SQLALCHEMY_DATABASE_URL_ASYNC, echo=True)
async_session = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
    class_=AsyncSession
)


def init_db():
    """Inicializa la base de datos creando todas las tablas"""
    create_database_if_not_exists()
    from app.config.base import Base
    Base.metadata.create_all(bind=engine)


class Database:
    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal

    def get_db(self) -> Session:
        """
        Proporciona una sesión de base de datos como un generador.
        Para ser usado con FastAPI Depends.
        """
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()


# Instancia global de la base de datos
database = Database()


# Función de ayuda para obtener una sesión de base de datos
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
