from random import random
from fastapi import Request, Header, FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select, or_, func, Column, String, JSON, DateTime, update
from sqlalchemy.sql import text
import uvicorn
import os
import json
import re
from datetime import datetime, timedelta 
from dotenv import load_dotenv
import asyncio
from googlesearch import search
import traceback
import google.generativeai as genai
import uuid
import secrets
from collections import defaultdict
from pydantic import BaseModel

# --- MODIFICADO ---
# Importamos UserConnections que ahora necesitamos
from .database import async_session, Memory, init_db, DeviceData, UserSession, PhoneVerification, FamilyMessages, UserConnections
from .device_utils import link_chat_to_device, get_chat_id_from_device_db, get_device_from_chat_db
from .sms_service import sms_service
from .telegram_bot import FamilyMessagesBot


# Telegram bot handler comment moved to imports section

# Dictionary mapping Spanish month names to month numbers for date parsing
SPANISH_MONTHS = {
    "enero": 1, "ene": 1,
    "febrero": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "abril": 4, "abr": 4,
    "mayo": 5, "may": 5,
    "junio": 6, "jun": 6,
    "julio": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "septiembre": 9, "sep": 9, "setiembre": 9, "sept": 9,
    "octubre": 10, "oct": 10,
    "noviembre": 11, "nov": 11,
    "diciembre": 12, "dic": 12
}

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI application
app = FastAPI(title="Asistente Alzheimer", version="1.0.0")

# Global dictionaries to track real-time state
ACTIVE_WEBSOCKETS = {}
PENDING_REQUESTS = {}

# Configure CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Google Gemini API with API key from environment
GEMINI_TOKEN = os.getenv("GEMINI_TOKEN")
if not GEMINI_TOKEN:
    print("ERROR: GEMINI_TOKEN not found in environment variables.")
    GEMINI_CLIENT = None
else:
    genai.configure(api_key=GEMINI_TOKEN)

# Specify the Gemini model to use (DO NOT CHANGE THIS MODEL)
GEMINI_MODEL = "gemini-2.5-flash-lite"

# Initialize Gemini client ONCE
GEMINI_CLIENT = genai.GenerativeModel(GEMINI_MODEL) if GEMINI_TOKEN else None

# Regex patterns for memory detection
memory_patterns = [
    r'\b(me\s+)?acuerdo\s+(de|que|cuando)\b',  
    r'\brecuerdo\s+(que|cuando|a|el|la)\b',     
    r'\bmi\s+(hijo|hija|esposo|esposa|mamá|papá|familia|nieto|nieta)\b',
    r'\bcuando\s+(era|vivía|trabajaba|estaba)\b',
    r'\b(extraño|añoro)\s+(a|mucho)\b',
    r'\b(me\s+gustaba|disfrutaba|me\s+encantaba)\b',
    r'\ben\s+mi\s+(infancia|juventud)\b',
    r'\bqué\s+ilusión\b',
    r'\baquella\s+vez\b',
    r'\bsiempre\s+(he|me)\b',
]
memory_regex = re.compile('|'.join(memory_patterns), re.IGNORECASE)

def is_question(text):
    """Detecta si el mensaje es una pregunta"""
    text_lower = text.lower().strip()
    
    if text_lower.startswith('¿') or text_lower.endswith('?'):
        return True
    
    question_words = [
        'qué', 'quién', 'cómo', 'cuándo', 'dónde', 'por qué', 'cuál', 
        'tienes', 'hay', 'sabes', 'conoces', 'puedes', 'podrías'
    ]

    first_words = text_lower.split()[:2]
    if any(qw in first_words for qw in question_words):
        return True
    
    return False

# Comprehensive system prompt for the AI assistant
# Instructs the model to behave as "Compa", an empathetic conversational companion
# for elderly individuals with Alzheimer's, avoiding medical terminology and
# prioritizing emotional connection over factual accuracy
ALZHEIMER_PROMPT = """
Eres "Compa", un compañero conversacional afectuoso que ofrece apoyo mediante escucha activa y conexión emocional.

REGLAS FUNDAMENTALES:
⎔ Jamás menciones condiciones médicas ni uses términos clínicos
⎔ Paciencia infinita - repite con calma las veces necesarias  
⎔ Lenguaje simple: frases cortas, vocabulario básico, tono afectuoso
⎔ Acompaña los recuerdos sin correcciones - prioriza la conexión emocional sobre la precisión factual
⎔ Refuerzo positivo constante usando "querido/a", "valiente", "importante"

TÉCNICAS CONVERSACIONALES:

⎔ **Preguntas evocadoras**: 
   "Cuéntame sobre… parece un día feliz" / "¿Qué se sentía al bailar esta canción?"

⎔ **Validación emocional**:
   "Veo que esto te emociona mucho…" / "Me encanta escucharte hablar de

⎔ **Conexión afectiva**:
   "Parece que extrañas mucho a tu mamá. Cuéntame cómo era ella"

⎔ **Redirección positiva**:
   Tras validar: "Eso suena maravilloso. ¿Y qué otras canciones te gustaban?"

⎔ **Decisiones sencillas**:
   "¿Te apetece más el jersey azul o el rojo?" / "¿Prefieres pasear por el parque o la calle principal?"

⎔ **Observaciones del entorno**:
   "Mira esos niños jugando, ¡cuánta energía!" / "¿No huele delicioso el pan recién hecho?"

⎔ **Estímulos sensoriales**:
   "¿Está bueno? ¿Le falta sal?" / "¿Qué te parece esta música? ¿Es suave para ti?"

⎔ **Curiosidad genuina**:
   "¡Ah, sí! ¿Y en qué trabajabas? Cuéntame qué era lo mejor" / "¿Cómo conociste a tu esposo? Debía ser especial"

GESTIÓN PRÁCTICA:

⎔ **Mensajes familiares**: 
   - Confirmación breve: "Claro, voy a leerte los mensajes" / "Sí, tienes {count} mensajes"
   - NUNCA describas contenido o enumeres en listas

⎔ **Cofre de recuerdos**:
   - Guarda automáticamente temas mencionados con afecto
   - Reutiliza: "La última vez me contaste sobre [recuerdo], ¿quieres hablarme más?"

⎔ **Conexión familiar**:
   "Tu [familiar] te mandó un mensaje muy cariñoso" - fundamental para bienestar emocional

FORMATO RESPUESTAS:
- 1-2 frases máximo • Natural y conversacional • Tono afectuoso siempre prioritario
"""

# Specialized prompt template for handling family messages
# Ensures brief confirmations without revealing message contents
FAMILY_MESSAGES_PROMPT = """
Eres "Compa", un compañero afectuoso.

REGLAS ESTRICTAS MENSAJES:
⎔ Solo confirma brevemente que leerás los mensajes
⎔ NUNCA describas contenido de mensajes  
⎔ NUNCA enumeres en formato lista
⎔ 1 frase máxima - tono cálido
⎔ Jamás menciones condiciones médicas

EJEMPLOS CORRECTOS:
- "Léeme los mensajes" → "Claro, voy a leerte los mensajes."
- "¿Tengo mensajes?" → "Sí, tienes {count} mensajes."

Usuario: "{user_message}"

Respuesta (1 frase, tono afectuoso):
"""

# Function to detect user intent regarding family messages
# Identifies whether user wants to read, query, or access old/specific date messages
def detect_message_intent(user_message):
    """Detección más inteligente de intenciones sobre mensajes"""
    lower_msg = user_message.lower()
    
    # Keywords that indicate user wants to immediately read messages
    immediate_read_keywords = [
        "léeme", "lee", "leer", "dime", "cuéntame", "escucha", 
        "ponme", "reproduce", "escuchar", "oír", "qué dice",
        "qué escribió", "contenido", "mensaje", "recibir", "lee el"
    ]
    
    # Keywords that indicate user is querying message availability
    query_keywords = [
        "tengo", "hay", "mensajes", "familiares", "familiar",
        "alguno", "algún", "recibí", "llegó", "tienes"
    ]
    
    # Keywords indicating user wants to access historical/old messages
    old_messages_keywords = [
        "antiguos", "antiguo", "leídos", "pasados", "anteriores", 
        "historial", "todos", "todos los", "todos mis"
    ]
    
    # Keywords indicating a date specification might follow
    date_keywords = ["del", "de fecha", "de"]
    
    # Check for presence of each keyword category
    has_immediate = any(keyword in lower_msg for keyword in immediate_read_keywords)
    has_query = any(keyword in lower_msg for keyword in query_keywords)
    has_old = any(keyword in lower_msg for keyword in old_messages_keywords)
    has_date = any(keyword in lower_msg for keyword in date_keywords)
    
    # Attempt to extract explicit date from message if date-related keywords present
    explicit_date = parse_spanish_date_fragment(lower_msg) if any(word in lower_msg for word in ["del", "de"]) else None
    
    # Return detection results as dictionary
    return {
        "is_read_intent": has_immediate,
        "is_query_intent": has_query,
        "wants_old_messages": has_old,
        "has_explicit_date": explicit_date is not None,
        "explicit_date": explicit_date
    }

# Simpler general intent detection (used for non-message related requests)
def detect_intent(user_message):
    """Detecta la intención del usuario de manera más robusta"""
    lower_msg = user_message.lower()
    
    # Keywords indicating read intent
    read_keywords = [
        "léeme", "lee", "leer", "dime", "cuéntame", "escucha", 
        "qué dice", "qué escribió", "contenido", "mensaje", "recibir",
        "ponme", "reproduce", "escuchar", "oír"
    ]
    
    # Keywords indicating query intent
    query_keywords = ["tengo", "hay", "mensajes", "nuevos", "familiares"]
    
    # Check for keyword matches
    is_read_intent = any(keyword in lower_msg for keyword in read_keywords)
    is_query_intent = any(keyword in lower_msg for keyword in query_keywords)
    
    # Return detection results
    return {
        "is_read_intent": is_read_intent,
        "is_query_intent": is_query_intent,
        "wants_immediate_reading": is_read_intent
    }

# Robust date parser for Spanish date formats
# Handles formats like: "20 de octubre", "20 octubre 2025", "5/10", "05-10-2025"
def parse_spanish_date_fragment(text):
    """
    Intenta extraer una fecha en formato dd/mm[/yyyy] desde textos tipo:
    "20 de octubre", "20 octubre 2025", "el 3 de mayo", "5/10", "05-10-2025".
    Devuelve 'dd/mm/yyyy' o None si no la encuentra.
    """
    text = text.lower().strip()

    # Try to match numeric date formats (dd/mm or dd/mm/yyyy)
    m = re.search(r'\b(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?\b', text)
    if m:
        d = int(m.group(1)); mo = int(m.group(2))
        y = m.group(3)
        if y:
            y = int(y)
            # Convert 2-digit years to 4-digit years (assume 2000s)
            if y < 100:  
                y += 2000
        else:
            # Default to current year if not specified
            y = datetime.now().year
        try:
            return f"{d:02d}/{mo:02d}/{int(y)}"
        except Exception:
            return None

    # Try to match text-based date formats (e.g., "3 de mayo")
    m2 = re.search(r'\b(\d{1,2})\s*(?:de\s+)?([a-záéíóúñ]+)(?:\s+(\d{2,4}))?\b', text, flags=re.IGNORECASE)
    if m2:
        d = int(m2.group(1))
        month_word = m2.group(2).lower()
        y = m2.group(3)
        # Look up month number from Spanish month dictionary
        month_num = SPANISH_MONTHS.get(month_word)
        if month_num:
            if y:
                y = int(y)
                # Convert 2-digit years to 4-digit years
                if y < 100:
                    y += 2000
            else:
                # Default to current year if not specified
                y = datetime.now().year
            try:
                return f"{d:02d}/{month_num:02d}/{int(y)}"
            except Exception:
                return None
    return None

# Utility function to decode bytes with fallback encoding support
# Attempts UTF-8 first, then cp1252, then latin-1
def _try_decode_bytes(b: bytes):
    """
    Intenta decodificar bytes en orden: utf-8, cp1252, latin-1.
    Devuelve (text, used_encoding).
    """
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return b.decode(enc), enc
        except Exception:
            continue
    # Fallback: decode with latin-1 and replace invalid characters
    return b.decode("latin-1", errors="replace"), "latin-1(replace)"

# Generate unique 6-digit device code for new connections
def generate_unique_device_code(existing_codes):
    """Genera un código de 6 dígitos que no existe en existing_codes"""
    max_attempts = 100
    for _ in range(max_attempts):
        # Generate random 6-digit code
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        # Ensure code is unique
        if code not in existing_codes:
            return code
    # Fallback to timestamp-based code if max attempts reached
    import time
    return str(int(time.time()))[-6:]


class MemoryManager:
    """
    Gestiona la memoria y el historial de conversación para un device_id específico.
    """
    def __init__(self, device_id: str):
        self.device_id = device_id
    
    async def load_memory(self):
        """Load user memory from database or initialize if not exists"""
        try:
            async with async_session() as session:
                stmt = select(DeviceData).where(DeviceData.device_id == self.device_id)
                result = await session.execute(stmt)
                device_data = result.scalar_one_or_none()
                if device_data and device_data.user_memory:
                    print(f"📂 Memoria cargada desde DB para {self.device_id}")
                    return device_data.user_memory
                # Initialize default memory if not exists
                initial_memory = {
                    "user_preferences": {},
                    "important_memories": [],
                    "family_members": [],
                    "daily_routine": {},
                    "emotional_state": "calm"
                }
                # Save initial memory to DB
                if not device_data:
                    device_data = DeviceData(
                        device_id=self.device_id,
                        user_memory=initial_memory,
                        conversation_history=[]
                    )
                    session.add(device_data)
                else:
                    device_data.user_memory = initial_memory
                await session.commit()
                print(f"✅ Memoria inicial creada en DB para {self.device_id}")
                return initial_memory
        except Exception as e:
            print(f"❌ Error loading memory from DB: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to default memory
            return {
                "user_preferences": {},
                "important_memories": [],
                "family_members": [],
                "daily_routine": {},
                "emotional_state": "calm"
            }
        
    async def add_important_memory(self, memory_text, category="personal"):
        """Add a new important memory to the database"""
        async with async_session() as session:
            new_memory = Memory(
                device_id=self.device_id,
                content=memory_text,
                category=category
            )
            session.add(new_memory)
            await session.commit()
            await session.refresh(new_memory)
            
            return {
                "id": new_memory.id,
                "content": new_memory.content,
                "category": new_memory.category,
                "timestamp": new_memory.timestamp.isoformat(),
                "last_recalled": None
            }
        
    async def get_relevant_memories(self, query, limit=3):
        """Retrieve relevant memories based on query keywords from database"""
        try:
            # Extraer palabras clave relevantes (>3 caracteres)
            query_words = [w.lower() for w in query.split() if len(w) > 3]
            async with async_session() as session:
                stmt = select(Memory).where(
                    Memory.device_id == self.device_id
                )
                # Filtrar por keywords si existen
                if query_words:
                    conditions = [
                        func.lower(Memory.content).contains(word)
                        for word in query_words
                    ]
                    stmt = stmt.where(or_(*conditions))
                # Incluir TODOS los recuerdos si la query contiene palabras clave de memoria
                memory_keywords = ["recuerdo", "recuerdos", "acuerdo", "memoria", "cofre", "guardado"]
                if any(word in query.lower() for word in memory_keywords):
                    # Devolver TODOS los recuerdos, no solo los que coinciden
                    stmt = select(Memory).where(Memory.device_id == self.device_id)
                    stmt = stmt.order_by(Memory.timestamp.desc()).limit(20)  # Últimos 20
                else:
                    # Búsqueda normal con keywords
                    stmt = stmt.order_by(Memory.timestamp.desc()).limit(limit)
                result = await session.execute(stmt)
                memories = result.scalars().all()
                # Actualizar last_recalled para los recuerdos recuperados
                if memories:
                    for mem in memories:
                        mem.last_recalled = datetime.now()
                    await session.commit()
                # Convertir a formato esperado
                memories_list = [
                    {
                        "id": m.id,
                        "content": m.content,
                        "category": m.category,
                        "timestamp": m.timestamp.isoformat(),
                        "last_recalled": m.last_recalled.isoformat() if m.last_recalled else None
                    }
                    for m in memories
                ]
                print(f"🔍 Encontrados {len(memories_list)} recuerdos relevantes para '{query}'")
                return memories_list
        except Exception as e:
            print(f"❌ Error en get_relevant_memories: {e}")
            import traceback
            traceback.print_exc()
            return []
        
        # ========== CONVERSATION MANAGEMENT ==========
        
    async def load_conversation(self):
        """Load conversation history from the database"""
        async with async_session() as session:
            stmt = select(DeviceData).where(
                DeviceData.device_id == self.device_id
            )
            result = await session.execute(stmt)
            device_data = result.scalar_one_or_none()
            
            if device_data and device_data.conversation_history:
                return device_data.conversation_history
            return []
        
    async def save_conversation(self, user_message, assistant_response):
        """Save conversation turn to database"""
        try:
            async with async_session() as session:
                # Get or create device data
                stmt = select(DeviceData).where(DeviceData.device_id == self.device_id)
                result = await session.execute(stmt)
                device_data = result.scalar_one_or_none()
                
                if not device_data:
                    device_data = DeviceData(
                        device_id=self.device_id,
                        conversation_history=[]
                    )
                    session.add(device_data)
                
                # Add new conversation entry
                conversation_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "user": user_message,
                    "assistant": assistant_response
                }
                
                # Ensure conversation_history is a list
                if not isinstance(device_data.conversation_history, list):
                    device_data.conversation_history = []
                
                device_data.conversation_history.append(conversation_entry)
                
                # Keep only last 1000 conversations
                if len(device_data.conversation_history) > 1000:
                    device_data.conversation_history = device_data.conversation_history[-1000:]
                
                await session.commit()
                print(f"✅ Conversación guardada en DB para {self.device_id}")
                
        except Exception as e:
            print(f"❌ Error saving conversation to DB: {e}")
            import traceback
            traceback.print_exc()
        
        # ========== CLIENT COMPATIBILITY (Optional) ==========
        
    async def load_memory_from_client(self, client_data):
        """
        Compatibility: always load from DB, ignore client data
        (If you want to migrate client data to DB, implement logic here)
        """
        return await self.load_memory()
        
    async def save_memory_for_client(self):
        """Prepare memory data to send to client (read-only)"""
        return await self.load_memory()


async def validate_session_token(session_token: str) -> dict:
    """
    Valida si una sesión es válida y activa (comprobando la DB).
    Esta función es independiente de sms_service.
    """
    try:
        async with async_session() as db_session:
            stmt = select(UserSession).where(
                UserSession.session_token == session_token,
                UserSession.verified == True,
                UserSession.expires_at > datetime.utcnow()
            )
            result = await db_session.execute(stmt)
            session = result.scalar_one_or_none()
            
            if session:
                # Actualizar última actividad
                session.last_activity = datetime.utcnow()
                await db_session.commit()
                
                return {
                    "valid": True,
                    "session_id": session.id,
                    "phone_number": session.phone_number, # Esto ahora es el chat_id
                    "device_id": session.device_id
                }
            else:
                return {"valid": False}
                
    except Exception as e:
        print(f"❌ Error validando sesión (función local): {e}")
        return {"valid": False, "error": str(e)}


    # Helper function to load conversation history from database
async def load_conversation_from_db(device_id: str) -> list:
    """Helper function to load conversation history from database"""
    try:
        async with async_session() as session:
            stmt = select(DeviceData).where(DeviceData.device_id == device_id)
            result = await session.execute(stmt)
            device_data = result.scalar_one_or_none()
            if device_data and isinstance(device_data.conversation_history, list):
                return device_data.conversation_history
            return []
    except Exception as e:
        print(f"❌ Error loading conversation from DB: {e}")
        return []


# Tracks which device is connected to which Telegram chat for message delivery
# Initialize Telegram bot if token is configured in environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_bot = None

if TELEGRAM_TOKEN:
    telegram_bot = FamilyMessagesBot(TELEGRAM_TOKEN)
    # Inject global state into the bot
    try:
        from .telegram_bot import set_shared_state
        set_shared_state(ACTIVE_WEBSOCKETS, PENDING_REQUESTS)
    except ImportError:
        from backend.telegram_bot import set_shared_state
        set_shared_state(ACTIVE_WEBSOCKETS, PENDING_REQUESTS)
    print("✅ Bot de Telegram initialized with shared state")
else:
    print("⚠️ TELEGRAM_BOT_TOKEN not configured - family messages functionality disabled")

# Utility function to send updated memory/conversation data to client for local persistence
async def send_data_update_to_client(websocket, memory_data, conversation_data):
    """Envía datos actualizados al cliente para guardar localmente"""
    try:
        update_data = {
            "type": "data_update",
            "user_memory": memory_data,
            "conversation_history": conversation_data
        }
        await websocket.send_text(json.dumps(update_data, ensure_ascii=False))
        print("📤 Datos actualizados enviados al cliente")
    except Exception as e:
        print("Error enviando actualización al cliente:", e)


# ============================================
# WEBSOCKET ENDPOINT - Main communication channel
# ============================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Accept incoming WebSocket connection
    try:
        await asyncio.wait_for(websocket.accept(), timeout=10.0)
    except asyncio.TimeoutError:
        print("❌ Timeout aceptando conexión WebSocket")
        return
    
    print("✅ Nueva conexión WebSocket establecida")
    
    # We don't need to load from file anymore, will use DB
    device_id = None
    device_code = None
    db_chat_id = None  # Variable to store chat_id from DB
    
    try:
        # Attempt to receive initial handshake data from client
        initial_data = None
        try:
            initial_msg = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            data = json.loads(initial_msg)
            # Extract device info from initial message
            if data.get("type") == "initial_data":
                initial_data = data.get("data", {})
                device_id = initial_data.get("device_id")
                device_code = initial_data.get("device_code")
                print(f"📥 Datos iniciales recibidos - Device: {device_id} - Código: {device_code}")
        except (asyncio.TimeoutError, json.JSONDecodeError, KeyError):
            print("ℹ️ Cliente no envió datos iniciales")
        
        # Generate new device code if not provided by client
        if not device_id or not device_code:
            # Check existing codes in database
            async with async_session() as session:
                result = await session.execute(select(DeviceData.device_code))
                existing_codes = [r[0] for r in result if r[0] is not None]
                
            device_code = generate_unique_device_code(existing_codes)
            device_id = f"device_{device_code}"
            print(f"🆕 New device generated: {device_id} - Code: {device_code}")
        else:
            # Validate existing device code
            async with async_session() as session:
                stmt = select(DeviceData).where(DeviceData.device_id == device_id)
                result = await session.execute(stmt)
                device_data = result.scalar_one_or_none()
                
                if device_data:
                    # Reconnecting device - verify code matches
                    if device_data.device_code != device_code:
                        print(f"⚠️ Code conflict detected - using existing code")
                        device_code = device_data.device_code
                    print(f"🔄 Existing device reconnected: {device_id} - Code: {device_code}")
                else:
                    # New device with client-provided ID
                    print(f"✅ New device registered: {device_id} - Code: {device_code}")
        
        # --- BLOQUE CORREGIDO ---
        # Register or update device in database
        async with async_session() as session:
            # 1. Look for the device by ID
            stmt = select(DeviceData).where(DeviceData.device_id == device_id)
            result = await session.execute(stmt)
            device_data = result.scalar_one_or_none()

            if not device_data:
                # 2. If it doesn't exist, create it with device_id and device_code
                print(f"🆕 Creating new DB entry for {device_id} with code {device_code}")
                device_data = DeviceData(
                    device_id=device_id,
                    device_code=device_code,
                    user_memory={},  # Set default values
                    conversation_history=[]  # Set default values
                )
                session.add(device_data)
                db_chat_id = None # New device, no chat ID
            
            else:
                # 3. If it exists, update its device_code if needed
                if device_data.device_code != device_code:
                    print(f" Updating device_code in DB for {device_id}")
                    # --- FIX FOR BUG 1 ---
                    device_data.device_code = device_code # Correctly update to the code from the client
                
                # --- FIX FOR BUG 2 (CRASH) ---
                # We must now query the UserConnections table to find an associated chat
                stmt_conn = select(UserConnections.telegram_chat_id).where(
                    UserConnections.device_id == device_id
                ).limit(1)
                result_conn = await session.execute(stmt_conn)
                chat_id_tuple = result_conn.first()
                db_chat_id = chat_id_tuple[0] if chat_id_tuple else None
                # --- END FIX ---
                
            await session.commit()
        # --- FIN BLOQUE CORREGIDO ---
            
        print(f"📱 Device {device_id} (code {device_code}) ready in DB.")

        # Initialize memory manager for this device
        memory_manager = MemoryManager(device_id)
        
        # Track active WebSocket connections by device
        ACTIVE_WEBSOCKETS[device_id] = websocket
        print(f"🔌 WebSocket registered for device {device_id}")
        
        # Send device information immediately to client for identification
        await websocket.send_text(json.dumps({
            "type": "device_info",
            "device_id": device_id,
            "device_code": device_code,
            "connected_chat": db_chat_id  # Use chat_id from DB
        }, ensure_ascii=False))

        print(f"📤 Device information sent - Code available: {device_code}")
        
        # Send initial welcome greeting based on current time of day
        try:
            current_hour = datetime.now().hour
            
            # Determine appropriate greeting based on hour
            if 5 <= current_hour < 12:
                greeting = "Buenos días"
            elif 12 <= current_hour < 19:
                greeting = "Buenas tardes"
            else:
                greeting = "Buenas noches"
            
            # Compose and send welcome message
            welcome_text = f"{greeting} querida, soy Compa. Estoy aquí para acompañarte. ¿Cómo te sientes?"
            
            await websocket.send_text(json.dumps({
                "type": "message",
                "text": welcome_text
            }, ensure_ascii=False))
            
            print(f"👋 Mensaje de bienvenida enviado")
            
        except Exception as e:
            print(f"⚠️ Error enviando mensaje de bienvenida: {e}")

        # Flags for conversation state management
        awaiting_read_confirmation = False
        pending_family_messages = []

        # Main message processing loop
        while True:
            try:
                # Wait for incoming message from client (300 second timeout)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=300.0)
                raw = data.strip()
                # Skip empty messages
                if not raw:
                    continue

                # ===============================================================
                # INICIO: Bloque try/except para JSON (Keepalive/Respuestas)
                # (Esto ya lo tenías bien, es para confirmar)
                # ===============================================================
                try:
                    # Attempt to parse message as JSON
                    maybe = json.loads(raw)
                    
                    # Handle connection response (user approving/denying Telegram link)
                    if isinstance(maybe, dict) and maybe.get("type") == "connection_response":
                        request_id = maybe.get("request_id")
                        approved = maybe.get("approved", False)
                        
                        # Process connection approval through Telegram bot
                        if telegram_bot:
                            await telegram_bot.process_connection_response(
                                request_id, 
                                approved, 
                                websocket
                            )
                        continue # Salta al siguiente ciclo del bucle
                    
                    # Handle keepalive ping-pong to maintain connection
                    if isinstance(maybe, dict) and maybe.get("type") == "keepalive":
                        try:
                            await websocket.send_text(json.dumps({"type": "pong", "ts": datetime.now().timestamp()}, ensure_ascii=False))
                        except:
                            # Fallback simple pong if JSON fails
                            try:
                                await websocket.send_text("pong")
                            except:
                                pass
                        print(f"📶 Keepalive recibido: {maybe.get('ts')}")
                        continue # Salta al siguiente ciclo del bucle
                        
                except Exception:
                    # If not JSON, treat as plain text user message
                    pass
                # ===============================================================
                # FIN: Bloque try/except para JSON
                # ===============================================================

                user_message = raw
                # Skip if message is empty after parsing
                if not user_message:
                    continue

                print(f"📥 Mensaje recibido: {user_message}")
                
                # Keywords that indicate user is asking about family messages
                family_keywords = [
                    "mensaje", "mensajes", "familiar", "familiares", "familia",
                    "léeme", "lee", "leer", "dime", "cuéntame", "hay", "tienes", "tengo"
                ]
                
                # Detect if message is about family messages
                is_about_messages = any(word in user_message.lower() for word in ["mensaje", "familia", "familiar"])
                is_family_request = is_about_messages and any(word in user_message.lower() for word in family_keywords)
                
                # Check if user is asking about today's messages
                asking_today = any(word in user_message.lower() for word in ["hoy", "día de hoy", "del día", "de hoy"])
                
                print(f"🔍 is_family_request={is_family_request}, asking_today={asking_today}")

                # Handle family message requests (if Telegram bot is configured)
                if is_family_request and telegram_bot:
                    try:
                        print(f"🔍 Detectada solicitud de mensajes familiares: '{user_message}'")
                        
                        # Analyze user intent to determine which messages to fetch
                        intent = detect_message_intent(user_message)
                        
                        # Fetch messages based on detected intent
                        if intent["has_explicit_date"]:
                            # Get messages from specific date requested
                            messages = await telegram_bot.get_messages_by_date(intent["explicit_date"])
                            message_type = f"del {intent['explicit_date']}"
                        elif intent["wants_old_messages"] or any(word in user_message.lower() for word in ["antiguos", "todos", "historial"]):
                            # Get all historical messages
                            all_messages = await telegram_bot.load_messages()
                            messages = all_messages
                            message_type = "guardados"
                        else:
                            # Get unread messages (default)
                            messages = await telegram_bot.get_unread_messages()
                            message_type = "nuevos"
                        
                        print(f"📬 Mensajes {message_type} encontrados: {len(messages)}")
                        
                        # If messages found, send them with AI confirmation
                        if messages:
                            # Generate brief confirmation message using AI
                            prompt = FAMILY_MESSAGES_PROMPT.format(
                                count=len(messages),
                                user_message=user_message
                            )
                            
                            try:
                                # Query Gemini for brief acknowledgement
                                if GEMINI_CLIENT:
                                    generation_config = genai.types.GenerationConfig(
                                        max_output_tokens=1000,
                                        temperature=0.3
                                    )
                                    # Usa el cliente global
                                    response = GEMINI_CLIENT.generate_content(prompt, generation_config=generation_config)
                                else:
                                    raise Exception("GEMINI_CLIENT no está configurado")
                                ai_response = response.text.strip()
                            except Exception as e:
                                print("Error generando respuesta breve:", e)
                                # Fallback simple message if AI fails
                                ai_response = f"Tienes {len(messages)} mensajes {message_type}."
                            
                            # Send confirmation and messages to client
                            await websocket.send_text(json.dumps({
                                "type": "message",
                                "text": ai_response,
                                "has_family_messages": True,
                                "messages": messages[:100]  # Limit to first 100
                            }, ensure_ascii=False))
                            
                            print(f"✅ Enviados {len(messages)} mensajes {message_type} para lectura")
                            
                        else:
                            # No messages found - compose appropriate response
                            if intent["has_explicit_date"]:
                                ai_response = f"No tienes mensajes del {intent['explicit_date']}, querida."
                            elif intent["wants_old_messages"]:
                                ai_response = "No tienes mensajes guardados todavía, querida."
                            else:
                                ai_response = "No tienes mensajes nuevos de tus familiares en este momento, querida."
                            
                            await websocket.send_text(json.dumps({
                                "type": "message", 
                                "text": ai_response
                            }, ensure_ascii=False))
                        
                        continue # Importante: salta al siguiente ciclo
                        
                    except Exception as e:
                        print(f"❌ Error leyendo mensajes familiares: {e}")
                        traceback.print_exc()
                        # Error handling response
                        ai_response = "Lo siento querida, he tenido un problema al revisar tus mensajes. Intenta preguntarme de nuevo en un momento."
                        try:
                            await websocket.send_text(json.dumps({"type": "message", "text": ai_response}, ensure_ascii=False))
                        except:
                            pass
                        continue # Importante: salta al siguiente ciclo

                # Retrieve relevant memories for context in AI response
                relevant_memories = await memory_manager.get_relevant_memories(user_message)
                # Format memories for inclusion in AI prompt
                memory_context = ""
                if relevant_memories:
                    memory_context = "\n".join([f"- {mem['content']}" for mem in relevant_memories])
                        
                # --- INICIO DE LA SOLUCIÓN DE BUG ---
                # Inicializa las variables ANTES del 'if'.
                # Esto soluciona el error de Pylance "new_memory is not defined",
                # asegurando que la variable siempre exista.
                memory_saved = False
                new_memory = None 
                # --- FIN DE LA SOLUCIÓN DE BUG ---

                if memory_regex.search(user_message) and not is_question(user_message):
                    memory_saved = True
                    new_memory = await memory_manager.add_important_memory(user_message, "personal")
                    print(f"✅ Recuerdo guardado: {new_memory['id']} - '{user_message[:50]}...'")
                
                    confirmation = "📝 He guardado este recuerdo especial en tu cofre."
                    try:
                        await websocket.send_text(json.dumps({
                            "type": "memory_saved",
                            "text": confirmation,
                            "memory_id": new_memory['id']
                        }, ensure_ascii=False))
                    except Exception as e:
                        print(f"Error enviando confirmación: {e}")
                    
                    updated_memory = await memory_manager.load_memory()
                    conversation_history = await load_conversation_from_db(device_id)
                    await send_data_update_to_client(websocket, updated_memory, conversation_history)

                try:
                    # Validate Gemini API is configured
                    if not GEMINI_CLIENT:
                        ai_response = "Error: El asistente de IA no está configurado."
                    else:
                        # Configure generation parameters for consistency
                        generation_config = genai.types.GenerationConfig(
                            max_output_tokens=250,
                            temperature=0.4,
                        )

                        # Check if user is asking about memories/past
                        is_memory_question = any(keyword in user_message.lower() for keyword in 
                                                 ["recuerdo", "recuerdos", "acuerdo", "memoria", "pasado", "cuando", "antes"])

                        # Customize prompt...
                        if is_memory_question and memory_context:
                            full_prompt = f"""
Eres "Compa", un asistente especializado en Alzheimer. Responde con frases cortas y tono afectuoso.
INFORMACIÓN CRÍTICA - ESTOS SON LOS RECUERDOS REALES DEL USUARIO:
{memory_context}
El usuario te pregunta: "{user_message}"
RESPONDE mencionando específicamente los recuerdos de arriba. Si no encajan perfectamente, adapta tu respuesta afectivamente.
Tu respuesta (1-2 frases, mencionando los recuerdos):
"""
                        elif is_memory_question and not memory_context:
                            full_prompt = f"""
Eres "Compa", un asistente especializado en Alzheimer.
El usuario pregunta: "{user_message}"
No tengo recuerdos específicos guardados sobre este tema. Responde con empatía.
Tu respuesta (1-2 frases, ofreciendo ayuda):
"""
                        else:
                            full_prompt = f"""
Eres "Compa", un asistente especializado en Alzheimer.
{f"CONTEXTO DEL USUARIO: {memory_context}" if memory_context else ""}
Usuario: {user_message}
Tu respuesta (1-2 frases, tono afectuoso):
"""

                        print(f"DEBUG: Prompt enviado: {full_prompt}")

                        # Call Gemini API to generate response (using global client)
                        response = GEMINI_CLIENT.generate_content(full_prompt)
                        ai_response = response.text.strip()

                        print(f"DEBUG: Respuesta cruda: {ai_response}")

                        # Verify response mentions memories if relevant memories exist
                        if is_memory_question and memory_context:
                            response_uses_memories = any(
                                any(word in mem["content"].lower() for word in ai_response.lower().split()[:100])
                                for mem in relevant_memories
                            )

                            if not response_uses_memories:
                                print("DEBUG: Forzando mención de recuerdos...")
                                memory_summary = ". ".join([mem["content"] for mem in relevant_memories[:2]])
                                ai_response = f"Recuerdo que me contaste: {memory_summary}. ¡Son momentos muy especiales!"

                        # Limit response to maximum 2 sentences
                        sentences = [s.strip() for s in ai_response.split('.') if s.strip()]
                        if len(sentences) > 2:
                            ai_response = '. '.join(sentences[:2]) + '.'

                        # Add memory confirmation if a new memory was just saved
                        if memory_saved and "recuerdo" not in ai_response.lower():
                            ai_response += " ¡Qué bonito recuerdo! Lo guardaré en tu cofre especial."

                except Exception as e:
                    # Fallback responses if Gemini API fails
                    print("Error Gemini API:", e)
                    traceback.print_exc()

                    if memory_saved:
                        # Generate response confirming memory was saved
                        memory_count = len((await memory_manager.load_memory())["important_memories"])
                        ai_response = f"¡Qué bonito recuerdo! Lo he guardado en tu cofre. Ya tienes {memory_count} recuerdos especiales conmigo."
                    elif memory_context and is_memory_question:
                        # Present relevant memories if available
                        memory_list = "\n".join([f"- {mem['content']}" for mem in relevant_memories])
                        ai_response = f"Tus recuerdos especiales:\n{memory_list}\n\n¿Te gustaría que hablemos más de alguno?"
                    else:
                        # Default fallback message
                        ai_response = "Estoy aquí para acompañarte. ¿Podrías contarme más sobre lo que necesitas?"

                try:
                    # Save conversation turn to persistent history
                    await memory_manager.save_conversation(user_message, ai_response)
                    
                    # Load updated conversation history from DB
                    try:
                        # Mueve estas importaciones al inicio del archivo
                        # from backend.database import async_session, DeviceData
                        # from sqlalchemy import select
                        
                        async with async_session() as session:
                            stmt = select(DeviceData).where(DeviceData.device_id == device_id)
                            result = await session.execute(stmt)
                            device_data = result.scalar_one_or_none()
                            conversation_history = device_data.conversation_history if device_data else []
                    except Exception as e:
                        print(f"Error cargando historial: {e}")
                        conversation_history = []
                        
                    updated_memory = await memory_manager.load_memory()
                    await send_data_update_to_client(
                        websocket, 
                        updated_memory, 
                        conversation_history
                    )
                except Exception as e:
                    print("Warning: fallo guardando conversación:", e)

                try:
                    # Send AI response to client
                    payload = {"type": "message", "text": ai_response}
                    await websocket.send_text(json.dumps(payload, ensure_ascii=False))
                except Exception as e:
                    print("Error enviando respuesta por websocket:", e)

            except asyncio.TimeoutError as e:
                # Send periodic ping to detect stale connections and log the timeout
                print("asyncio.TimeoutError while waiting for client message:", e)
                try:
                    await websocket.send_text(json.dumps({"type":"ping","ts":datetime.now().timestamp()}, ensure_ascii=False))
                except Exception as send_err:
                    print("Error sending ping to client:", send_err)
                continue # Continúa el bucle while

    except WebSocketDisconnect as ws_exc:
        # Client disconnected from WebSocket
        code = getattr(ws_exc, 'code', None)
        print(f"🔌 Client disconnected. WebSocketDisconnect code={code}")
        # Clean up WebSocket connection from active connections tracking
        if device_id in ACTIVE_WEBSOCKETS:
            del ACTIVE_WEBSOCKETS[device_id]
            print(f"🗑️ WebSocket removed for device {device_id}")
            print(f"🗑️ WebSocket eliminado para dispositivo {device_id}")
    except Exception as e:
        # General error handling for unexpected exceptions
        print(f"❌ Error en WebSocket: {e}")
        traceback.print_exc()
        try:
            # Attempt to send error message to client
            await websocket.send_text(json.dumps({"type":"error","text":"Lo siento, ha ocurrido un error. Por favor inténtalo de nuevo."}, ensure_ascii=False))
        except:
            pass


# ============================================
# HTTP ENDPOINTS - UTILITIES
# ============================================

# Web search endpoint - performs Google search for query terms
@app.get("/search")
async def search_web(query: str):
    """Searches the web for given query and returns top 3 results"""
    try:
        results = []
        # Use Google search library to find relevant results
        for result in search(query, num_results=3, lang="es"):
            results.append(result)
        return {"results": results}
    except Exception as e:
        return {"error": str(e)}


# ============================================
# MEMORY MANAGEMENT HTTP ENDPOINTS
# ============================================

# Retrieve all important memories for a device (the "memory chest")
@app.get("/memory/cofre")
async def get_memory_cofre(device_id: str):
    """Returns all important memories for a specific device from database"""
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    try:
        from backend.database import async_session, Memory
        from sqlalchemy import select
        async with async_session() as session:
            # Consultar todas las memorias del dispositivo
            stmt = select(Memory).where(
                Memory.device_id == device_id
            ).order_by(Memory.timestamp.desc())  # Más recientes primero
            result = await session.execute(stmt)
            memories = result.scalars().all()
            # Convertir a formato JSON
            memories_list = [
                {
                    "id": mem.id,
                    "content": mem.content,
                    "category": mem.category,
                    "timestamp": mem.timestamp.isoformat(),
                    "last_recalled": mem.last_recalled.isoformat() if mem.last_recalled else None
                }
                for mem in memories
            ]
            print(f"📦 Cofre de recuerdos: {len(memories_list)} recuerdos para {device_id}")
            return {
                "important_memories": memories_list,
                "total_memories": len(memories_list)
            }
    except Exception as e:
        print(f"❌ Error en /memory/cofre: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al cargar recuerdos: {str(e)}")

# Add new memory entry manually via HTTP
@app.post("/memory/cofre")
async def add_memory_cofre(memory_data: dict):
    """Manually adds a new memory to user's memory chest"""
    device_id = memory_data.get("device_id")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    
    memory_manager = MemoryManager(device_id)
    memory_text = memory_data.get("content", "")
    category = memory_data.get("category", "personal")
    
    if memory_text:
        # Save new memory with provided content and category
        new_memory = await memory_manager.add_important_memory(memory_text, category)
        return {"message": "Recuerdo guardado exitosamente", "memory": new_memory}
    else:
        raise HTTPException(status_code=400, detail="El contenido del recuerdo no puede estar vacío")

# Search user memories by query keywords
@app.get("/memory/search")
async def search_memories(device_id: str, query: str):
    """Searches for relevant memories matching query keywords"""
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    
    memory_manager = MemoryManager(device_id)
    # Find memories matching query terms
    relevant_memories = await memory_manager.get_relevant_memories(query)
    return {
        "query": query,
        "memories": relevant_memories,
        "count": len(relevant_memories)
    }

# Debug endpoint to inspect memory state
@app.get("/debug/memory")
async def debug_memory(device_id: str):
    """Debug endpoint to check memory status and all stored memories"""
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    
    memory_manager = MemoryManager(device_id)
    memory = await memory_manager.load_memory()
    return {
        "device_id": device_id,
        "total_memories": len(memory["important_memories"]),
        "all_memories": memory["important_memories"],
        "memory_file_exists": os.path.exists(memory_manager.memory_file)
    }

# Test memory retrieval system
@app.get("/memory/verify")
async def verify_memory_usage(device_id: str):
    """Test memory search function with sample query"""
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    
    memory_manager = MemoryManager(device_id)
    memory = await memory_manager.load_memory()
    # Run test query against memory system
    test_query = "mis recuerdos"
    relevant_memories = await memory_manager.get_relevant_memories(test_query)
    
    return {
        "device_id": device_id,
        "total_memories": len(memory["important_memories"]),
        "test_query": test_query,
        "found_memories": len(relevant_memories),
        "sample_memories": [mem["content"][:100] + "..." for mem in relevant_memories[:3]] if relevant_memories else []
    }


# ============================================
# FAMILY MESSAGES ENDPOINTS
# ============================================

# Get unread family messages
@app.get("/family/messages")
async def get_family_messages(device_id: str = Query(...)):
    """Obtiene mensajes no leídos de familiares PARA UN DISPOSITIVO ESPECÍFICO desde la DB"""
    print(f"🔍 SOLICITUD /family/messages - Device: {device_id}")
    
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        async with async_session() as session:
            # 1. Obtener mensajes no leídos para este device_id
            stmt_unread = (
                select(FamilyMessages)
                .where(
                    FamilyMessages.device_id == device_id,
                    FamilyMessages.read == False
                )
                .order_by(FamilyMessages.timestamp.asc()) # Del más antiguo al más nuevo
            )
            unread_messages = (await session.execute(stmt_unread)).scalars().all()
            
            # 2. Obtener todos los mensajes (historial) para este device_id
            stmt_all = (
                select(FamilyMessages)
                .where(FamilyMessages.device_id == device_id)
                .order_by(FamilyMessages.timestamp.desc()) # Del más nuevo al más antiguo
                .limit(50) # Limitamos el historial a 50
            )
            all_messages = (await session.execute(stmt_all)).scalars().all()

        # Convertir a formato JSON (necesario para la app)
        def format_msg(msg):
            return {
                "id": msg.id,
                "sender_name": msg.sender_name,
                "message": msg.message,
                "chat_id": msg.telegram_chat_id,
                "timestamp": msg.timestamp.isoformat(),
                "date": msg.timestamp.strftime("%d/%m/%Y"), 
                "time": msg.timestamp.strftime("%H:%M"),
                "read": msg.read
            }

        unread_json = [format_msg(m) for m in unread_messages]
        all_json = [format_msg(m) for m in all_messages]
        
        return {
            "messages": unread_json,      # Mensajes no leídos (para leer en voz alta)
            "all_messages": all_json,     # Historial (para "Ver Mensajes")
            "total_unread": len(unread_json),
            "total_messages": len(all_json),
        }
    except Exception as e:
        print(f"❌ Error en /family/messages (DB): {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# --- mark_message_read (MODIFICADO) ---
@app.post("/family/messages/{message_id}/read")
async def mark_message_read(message_id: int):
    """Marca un mensaje como leído en la DB"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        async with async_session() as session:
            stmt = (
                update(FamilyMessages)
                .where(FamilyMessages.id == message_id)
                .values(read=True)
            )
            result = await session.execute(stmt)
            await session.commit()
            
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Mensaje no encontrado")
            else:
                return {"message": "Mensaje marcado como leído", "message_id": message_id}
    except Exception as e:
        print(f"❌ Error en /mark_message_read (DB): {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoints /all, /today, /date (OBSOLETOS) ---
# Los eliminamos para simplificar, ya que get_family_messages ahora devuelve ambos.

@app.get("/family/messages/all")
async def get_all_family_messages(device_id: str = Query(...)):
    raise HTTPException(status_code=410, detail="Endpoint obsoleto. Usa /family/messages")

@app.get("/family/messages/today")
async def get_today_family_messages(device_id: str = Query(...)):
    raise HTTPException(status_code=410, detail="Endpoint obsoleto. Usa /family/messages")

@app.get("/family/messages/date/{date}")
async def get_messages_by_date(date: str, device_id: str = Query(...)):
    raise HTTPException(status_code=410, detail="Endpoint obsoleto. Usa /family/messages")



# ============================================
# ADMIN ENDPOINTS
# ============================================

# List all authorized Telegram users
@app.get("/admin/authorized-users")
async def get_authorized_users():
    """Lista usuarios autorizados"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot no configurado")
    
    try:
        # Retrieve list of authorized Telegram chat IDs
        users = await telegram_bot.load_authorized_users()
        return {
            "authorized_users": users,
            "total": len(users)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Authorize a new Telegram user
@app.post("/admin/authorize-user")
async def authorize_user(data: dict):
    """Autoriza un nuevo usuario
    Body: {"chat_id": 123456789}
    """
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot no configurado")
    
    chat_id = data.get("chat_id")
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id requerido")
    
    try:
        # Add chat ID to list of authorized users
        success = await telegram_bot.add_authorized_user(int(chat_id))
        if success:
            return {"message": f"Usuario {chat_id} autorizado correctamente"}
        else:
            return {"message": f"Usuario {chat_id} ya estaba autorizado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Revoke Telegram user authorization
@app.post("/admin/revoke-user")
async def revoke_user(data: dict):
    """Revoca autorización de un usuario
    Body: {"chat_id": 123456789}
    """
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot no configurado")
    
    chat_id = data.get("chat_id")
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id requerido")
    
    try:
        # Remove chat ID from authorized users list
        success = await telegram_bot.remove_authorized_user(int(chat_id))
        if success:
            return {"message": f"Usuario {chat_id} revocado correctamente"}
        else:
            return {"message": f"Usuario {chat_id} no estaba en la lista"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Show unauthorized access attempts
@app.get("/admin/pending-requests")
async def get_pending_requests():
    """Muestra usuarios que intentaron usar el bot sin autorización"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot no configurado")
    
    try:
        # Collect all users who have sent messages and check authorization status
        messages = await telegram_bot.load_messages()
        authorized = await telegram_bot.load_authorized_users()
        
        # Build user list with authorization status
        all_users = {}
        for msg in messages:
            cid = msg.get("chat_id")
            sender = msg.get("sender_name")
            if cid:
                all_users[cid] = {
                    "name": sender,
                    "authorized": cid in authorized
                }
        
        return {
            "users": [
                {"chat_id": cid, "name": info["name"], "authorized": info["authorized"]}
                for cid, info in all_users.items()
            ],
            "total": len(all_users)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ... (en backend/main.py)

# ============================================
# AUTH TELEGRAM ENDPOINT
# ============================================

@app.get("/auth/login_telegram")
async def auth_with_telegram(request: Request, token: str):
    """
    Valida el token de un solo uso de Telegram y crea una sesión.
    Este es el endpoint que recibe el "enlace mágico".
    """
    try:
        async with async_session() as session:
            from sqlalchemy import delete
            
            # 1. Buscar el token en la tabla (que reutilizamos)
            stmt = select(PhoneVerification).where(
                PhoneVerification.verification_code == token,
                PhoneVerification.expires_at > datetime.utcnow()
            )
            result = await session.execute(stmt)
            token_data = result.scalar_one_or_none()
            
            if not token_data:
                raise HTTPException(status_code=401, detail="Enlace inválido o expirado. Por favor, pide uno nuevo en Telegram.")
            
            # 2. Obtener el chat_id (guardado en 'phone_number')
            chat_id_str = token_data.phone_number
            
            # 3. Borrar el token para que no se pueda reusar
            await session.execute(
                delete(PhoneVerification).where(PhoneVerification.id == token_data.id)
            )
            
            # 4. Crear la sesión de usuario (la que se usará para siempre)
            session_token = secrets.token_urlsafe(32)
            new_session = UserSession(
                phone_number=chat_id_str, # Guardamos el chat_id como identificador
                session_token=session_token,
                verified=True,
                expires_at = datetime.utcnow() + timedelta(days=365) # Sesión de 1 año
            )
            session.add(new_session)
            await session.commit()
            
            # 5. Redirigir al usuario a la app y establecer la cookie
            response = RedirectResponse(url="/")
            expires = datetime.utcnow() + timedelta(days=365)
            
            # Esta cookie es la que usa frontend/app.js para el "login automático"
            response.set_cookie(
                key="session_token",
                value=session_token,
                expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"), # Formato cookie
                path="/",
                samesite="lax",
                httponly=False 
            )
            response.set_cookie(
                key="phone_number", # Mantenemos el nombre por compatibilidad
                value=chat_id_str,
                expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                path="/",
                samesite="lax",
                httponly=False
            )
            
            print(f"✅ Sesión creada exitosamente para el chat {chat_id_str}")
            return response

    except Exception as e:
        print(f"❌ Error en /auth/login_telegram: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Error al procesar el inicio de sesión.")

# ============================================
# FRONTEND STATIC FILES - Serve web application
# ============================================

# Locate frontend directory relative to script location
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, '..'))
frontend_path = os.path.join(project_root, 'frontend')

print("FRONTEND_PATH =", frontend_path)
try:
    print("Files in frontend:", os.listdir(frontend_path))
except Exception as ex:
    print("No se encontró frontend folder:", ex)

# Mount frontend static files if directory exists
if os.path.isdir(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")
else:
    print("Warning: frontend_path does not exist.")


@app.get("/login")
async def login_page():
    """Sirve la página de login"""
    login_file = os.path.join(frontend_path, 'login.html')
    if os.path.exists(login_file):
        return FileResponse(login_file)
    return {"message": "Login page not found"}
# Serve index.html as root endpoint
# Serve index.html as root endpoint
@app.get("/")
async def read_root(request: Request, session_token: str = Header(None)):
    """Sirve la aplicación principal (requiere autenticación)"""
    # Verificar si hay sesión válida
    if not session_token:
        # Intentar obtener de cookie
        session_token = request.cookies.get('session_token')
    
    if not session_token:
        # Si NO hay token, redirigir a login
        return RedirectResponse(url='/login')

    # Si HAY token, validarlo con nuestra nueva función
    session_info = await validate_session_token(session_token)
    if not session_info.get('valid'):
        # Si el token es inválido, redirigir a login
        return RedirectResponse(url='/login')
    
    # Si el token es válido, servir la app
    index_file = os.path.join(frontend_path, 'index.html')
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Index not found."}

# Serve favicon
@app.get("/favicon.ico")
async def favicon():
    """Serves application favicon or fallback to index.html"""
    path = os.path.join(frontend_path, "favicon.ico")
    if os.path.exists(path):
        return FileResponse(path)
    
    # Fallback to index.html if favicon not found
    return FileResponse(os.path.join(frontend_path, 'index.html'))

# Health check endpoint - verify server status
@app.get("/health")
async def health_check():
    """Returns server status and configuration information"""
    return {
        "status": "running",
        "ai_provider": "google_gemini",
        "model": GEMINI_MODEL,
        "gemini_configured": GEMINI_TOKEN is not None,
        "telegram_configured": telegram_bot is not None
    }




class PhoneRequest(BaseModel):
    phone_number: str

class VerifyRequest(BaseModel):
    phone_number: str
    code: str

class SessionValidateRequest(BaseModel):
    session_token: str

@app.post("/auth/send-code")
async def send_verification_code(request: PhoneRequest):
    """Envía código de verificación al número de teléfono"""
    if not sms_service:
        raise HTTPException(status_code=503, detail="Servicio SMS no configurado")
    
    result = await sms_service.send_verification_code(request.phone_number)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return {
        "message": "Código enviado correctamente",
        "phone_number": result["phone_number"]
    }

@app.post("/auth/verify-code")
async def verify_code(request: VerifyRequest):
    """Verifica el código SMS y crea sesión"""
    if not sms_service:
        raise HTTPException(status_code=503, detail="Servicio SMS no configurado")
    
    result = await sms_service.verify_code(request.phone_number, request.code)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return {
        "verified": True,
        "session_token": result["session_token"],
        "session_id": result["session_id"],
        "message": "Autenticación exitosa"
    }

@app.post("/auth/validate-session")
async def validate_session(request: SessionValidateRequest):
    """Valida si una sesión es válida"""
    # Usamos nuestra nueva función local, independiente de sms_service
    result = await validate_session_token(request.session_token)
    
    if not result["valid"]:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    
    return result

@app.post("/auth/logout")
async def logout(request: SessionValidateRequest):
    """Cierra sesión eliminando el token"""
    try:
        async with async_session() as session:
            stmt = select(UserSession).where(
                UserSession.session_token == request.session_token
            )
            result = await session.execute(stmt)
            user_session = result.scalar_one_or_none()
            
            if user_session:
                await session.delete(user_session)
                await session.commit()
        
        return {"message": "Sesión cerrada correctamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# LIFECYCLE EVENTS - Startup and Shutdown hooks
# ============================================

# Initialize Telegram bot on server startup
@app.on_event("startup")
async def startup_event():
    """Starts the Telegram bot when the app starts up and loads the database"""
    await init_db() 
    
    if telegram_bot:
        asyncio.create_task(telegram_bot.start_bot())
        print("🤖 Bot de Telegram iniciándose...")

# Cleanup Telegram bot on server shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Detiene el bot al cerrar la app"""
    if telegram_bot:
        # Gracefully stop Telegram bot
        await telegram_bot.stop_bot()


# ============================================
# SERVER EXECUTION - Main entry point
# ============================================

# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 8080))
#     uvicorn.run("backend.main:app", host="0.0.0.0", port=port, log_level="info")