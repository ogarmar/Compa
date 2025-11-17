from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, BigInteger, Boolean, ForeignKey, UniqueConstraint
import os
from datetime import datetime, timedelta
import secrets

# --- Configuración del motor (sin cambios) ---
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


# --- Tabla 'memories' (sin cambios) ---
class Memory(Base):
    """Table to store important user memories"""
    __tablename__ = "memories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(100), index=True, nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), default="personal")
    timestamp = Column(DateTime, default=datetime.utcnow)
    last_recalled = Column(DateTime, nullable=True)


# --- Tabla 'device_data' (MODIFICADA) ---
class DeviceData(Base):
    """Table to store device-specific data including connection info and history"""
    __tablename__ = "device_data"
    
    device_id = Column(String(100), primary_key=True)
    device_code = Column(String(6), unique=True, nullable=True)
    
    # !!! ELIMINADO !!!
    # telegram_chat_id = Column(BigInteger, unique=True, nullable=True, index=True)
    # Esta columna es la que causaba el UniqueViolationError.
    # La reemplazamos con la tabla UserConnections.
    
    user_memory = Column(JSON, default=lambda: {})
    conversation_history = Column(JSON, default=lambda: [])
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_connected = Column(DateTime, nullable=True)


# --- Tabla 'user_sessions' (sin cambios) ---
class UserSession(Base):
    """Table for phone authentication sessions"""
    __tablename__ = "user_sessions"
    
    id = Column(String(100), primary_key=True, default=lambda: secrets.token_urlsafe(32))
    phone_number = Column(String(20), index=True, nullable=False) # Mantenemos esto para el login
    device_id = Column(String(100), index=True, nullable=True)
    session_token = Column(String(200), unique=True, nullable=False)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=30))
    last_activity = Column(DateTime, default=datetime.utcnow)


# --- Tabla 'phone_verifications' (sin cambios) ---
class PhoneVerification(Base):
    """Table for phone number verification codes"""
    __tablename__ = "phone_verifications"
    
    id = Column(String(100), primary_key=True)
    phone_number = Column(String(20), index=True, nullable=False)
    verification_code = Column(String(200), nullable=False) # Mantenemos el String(200)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(minutes=10))
    attempts = Column(Integer, default=0)
    verified = Column(Boolean, default=False)

# --- ¡NUEVA TABLA! 'user_connections' ---
class UserConnections(Base):
    """
    NUEVA TABLA: Vincula un chat_id de Telegram con MÚLTIPLES dispositivos.
    Esta es la tabla muchos-a-muchos que permite los alias.
    """
    __tablename__ = "user_connections"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_chat_id = Column(BigInteger, index=True, nullable=False)
    device_id = Column(String(100), ForeignKey("device_data.device_id", ondelete="CASCADE"), nullable=False)
    alias = Column(String(50), index=True) # El nombre (ej. "Mama", "Abuelo")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Restricción: Un usuario no puede tener el mismo alias para dos dispositivos,
    # y un usuario no puede tener dos alias para el mismo dispositivo.
    __table_args__ = (
        UniqueConstraint('telegram_chat_id', 'device_id', name='uq_chat_device'),
        UniqueConstraint('telegram_chat_id', 'alias', name='uq_chat_alias'),
    )

# --- ¡NUEVA TABLA! 'family_messages' ---
class FamilyMessages(Base):
    """
    NUEVA TABLA: Reemplaza el archivo family_messages.json.
    Ahora cada mensaje está vinculado a un dispositivo específico.
    """
    __tablename__ = "family_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(100), ForeignKey("device_data.device_id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_chat_id = Column(BigInteger, nullable=False)
    sender_name = Column(String(100))
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    read = Column(Boolean, default=False)


# --- Función 'init_db' (sin cambios) ---
async def init_db():
    """Create database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Base de datos inicializada correctamente")