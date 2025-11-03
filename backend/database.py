from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, BigInteger
import os
from datetime import datetime

# Convert DATABASE_URL for asyncpg if necessary
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# Create the async engine and session
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


class Memory(Base):
    """Table to store important user memories"""
    __tablename__ = "memories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(100), index=True, nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), default="personal")
    timestamp = Column(DateTime, default=datetime.utcnow)
    last_recalled = Column(DateTime, nullable=True)


class DeviceData(Base):
    """Table to store device-specific data including connection info and history"""
    __tablename__ = "device_data"
    
    device_id = Column(String(100), primary_key=True)
    device_code = Column(String(6), unique=True, nullable=True)
    # Cambiado a BigInteger para soportar IDs de chat grandes/negativos
    telegram_chat_id = Column(BigInteger, unique=True, nullable=True, index=True)
    # Lambda para crear nuevos objetos por cada instancia
    user_memory = Column(JSON, default=lambda: {})
    conversation_history = Column(JSON, default=lambda: [])
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_connected = Column(DateTime, nullable=True)


async def init_db():
    """Create database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Base de datos inicializada correctamente")