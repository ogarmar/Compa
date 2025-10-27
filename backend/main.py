from random import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import os
import json
import aiofiles
import re
from datetime import datetime
from dotenv import load_dotenv
import asyncio
from googlesearch import search
import traceback
import google.generativeai as genai
import re
from datetime import datetime
import uuid
from collections import defaultdict

# Import custom Telegram bot handler (fallback to local import if package not found)
try:
    from .telegram_bot import FamilyMessagesBot
except ImportError:
    from telegram_bot import FamilyMessagesBot

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
else:
    genai.configure(api_key=GEMINI_TOKEN)

# Specify the Gemini model to use (DO NOT CHANGE THIS MODEL)
GEMINI_MODEL = "gemini-2.5-flash-lite"

# File paths for persistent data storage
MEMORY_FILE = "user_memory.json"
CONVERSATION_FILE = "conversation_history.json"

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
   "Veo que esto te emociona mucho…" / "Me encanta escucharte hablar de esto"

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

# Manager class for user memory operations (emotion tracking, important memories, preferences)
class MemoryManager:
    def __init__(self, device_id):
        self.device_id = device_id
        # Unique file names per device
        self.memory_file = f"user_memory_{device_id}.json"
        self.conversation_file = f"conversation_history_{device_id}.json"
    
    # Load user memory from client-side provided data
    async def load_memory_from_client(self, client_data):
        """Carga memoria desde datos enviados por el cliente"""
        if client_data:
            print("✅ Cargando memoria desde datos del cliente")
            return client_data
        else:
            return await self.load_memory() 
    
    # Prepare memory data for client-side storage
    async def save_memory_for_client(self, memory_data):
        """Prepara datos para que el cliente los guarde localmente"""
        return memory_data
    
    # Load conversation history from client-provided data
    async def load_conversation_from_client(self, client_data):
        """Carga conversación desde datos del cliente"""
        if client_data:
            print("✅ Cargando conversación desde datos del cliente")
            return client_data
        else:
            return await self.load_conversation_from_file()
    
    # Load conversation history from local file (fallback mechanism)
    async def load_conversation_from_file(self):
        """Carga conversación desde archivo (fallback)"""
        try:
            if os.path.exists(self.conversation_file):
                async with aiofiles.open(self.conversation_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            return []
        except Exception as e:
            print("Error cargando conversación:", e)
            return []
    
    # Load or initialize user memory structure
    async def load_memory(self):
        if not os.path.exists(self.memory_file):
            # Initialize default memory structure if file doesn't exist
            initial_memory = {
                "user_preferences": {},
                "important_memories": [],
                "family_members": [],
                "daily_routine": {},
                "emotional_state": "calm"
            }
            await self.save_memory(initial_memory)
            return initial_memory

        try:
            # Attempt to read file with UTF-8 encoding
            async with aiofiles.open(self.memory_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except UnicodeDecodeError as ude:
            # Handle encoding issues with fallback decoding
            print("Error leyendo memoria (utf-8):", ude)
            try:
                async with aiofiles.open(self.memory_file, 'rb') as f:
                    raw_bytes = await f.read()
                text, used_enc = _try_decode_bytes(raw_bytes)
                print(f"Decoded memory file with fallback encoding: {used_enc}. Normalizing to utf-8...")
                data = json.loads(text)
                # Rewrite file in UTF-8 for future consistency
                try:
                    async with aiofiles.open(self.memory_file, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(data, indent=2, ensure_ascii=False))
                    print("Memoria reescrita en UTF-8 correctamente.")
                except Exception as e:
                    print("Error reescribiendo memoria en UTF-8:", e)
                return data
            except Exception as e:
                print("Error leyendo/decodificando memoria con fallback:", e)
                return {
                    "user_preferences": {},
                    "important_memories": [],
                    "family_members": [],
                    "daily_routine": {},
                    "emotional_state": "calm"
                }
        except FileNotFoundError:
            # Initialize new memory if file not found
            initial_memory = {
                "user_preferences": {},
                "important_memories": [],
                "family_members": [],
                "daily_routine": {},
                "emotional_state": "calm"
            }
            await self.save_memory(initial_memory)
            return initial_memory
        except json.JSONDecodeError as jde:
            # Handle corrupted JSON with recovery attempt
            print("JSON corrupto en memory file:", jde)
            try:
                async with aiofiles.open(self.memory_file, 'rb') as f:
                    raw_bytes = await f.read()
                text, used_enc = _try_decode_bytes(raw_bytes)
                data = json.loads(text)
                async with aiofiles.open(self.memory_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(data, indent=2, ensure_ascii=False))
                return data
            except Exception as e:
                print("No se pudo reparar memory file:", e)
                return {
                    "user_preferences": {},
                    "important_memories": [],
                    "family_members": [],
                    "daily_routine": {},
                    "emotional_state": "calm"
                }
        except Exception as e:
            print("Error leyendo memoria (general):", e)
            return {
                "user_preferences": {},
                "important_memories": [],
                "family_members": [],
                "daily_routine": {},
                "emotional_state": "calm"
            }
    
    # Save memory to file asynchronously
    async def save_memory(self, memory_data):
        try:
            async with aiofiles.open(self.memory_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(memory_data, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Error guardando memoria:", e)
    
    # Add new important memory entry with timestamp
    async def add_important_memory(self, memory_text, category="personal"):
        memory = await self.load_memory()
        new_memory = {
            "id": len(memory["important_memories"]) + 1,
            "content": memory_text,
            "category": category,
            "timestamp": datetime.now().isoformat(),
            "last_recalled": None
        }
        memory["important_memories"].append(new_memory)
        await self.save_memory(memory)
        return new_memory
    
    # Retrieve relevant memories based on query keywords (semantic search-lite)
    async def get_relevant_memories(self, query, limit=3):
        memory = await self.load_memory()
        relevant = []
        query_words = query.lower().split()
        
        # Search through memories for matching keywords
        for mem in memory["important_memories"]:
            memory_text = mem["content"].lower()
            # Check for direct keyword matches (exclude short words)
            direct_match = any(word in memory_text for word in query_words if len(word) > 3)
            
            # Include all memories if query contains memory-related keywords
            if any(word in query.lower() for word in ["recuerdo", "recuerdos", "acuerdo", "memoria"]):
                relevant.append(mem)
            elif direct_match:
                relevant.append(mem)
        
        # Sort by recency and return top results
        relevant.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return relevant[:limit]
    
    # Save conversation turn (user message + AI response) to file
    async def save_conversation(self, user_message, assistant_response):
        try:
            conversations = []
            # Load existing conversations
            if os.path.exists(self.conversation_file):
                try:
                    async with aiofiles.open(self.conversation_file, 'r', encoding='utf-8') as f:
                        conversations = json.loads(await f.read())
                except UnicodeDecodeError:
                    # Handle encoding issues
                    print("Error leyendo conversation_history.json con utf-8; aplicando fallback.")
                    try:
                        async with aiofiles.open(self.conversation_file, 'rb') as f:
                            raw_bytes = await f.read()
                        text, used_enc = _try_decode_bytes(raw_bytes)
                        conversations = json.loads(text)
                        
                        async with aiofiles.open(self.conversation_file, 'w', encoding='utf-8') as f:
                            await f.write(json.dumps(conversations, indent=2, ensure_ascii=False))
                        print("conversation_history.json reescrito en UTF-8.")
                    except Exception as e:
                        print("No se pudo reparar conversation_history.json:", e)
                        conversations = []
                except json.JSONDecodeError:
                    print("JSON corrupto en conversation_history.json; se reiniciará.")
                    conversations = []
                except Exception as e:
                    print("Error leyendo conversation file:", e)
                    conversations = []
            else:
                conversations = []
            
            # Append new conversation turn
            conversation_entry = {
                "timestamp": datetime.now().isoformat(),
                "user": user_message,
                "assistant": assistant_response
            }
            conversations.append(conversation_entry)
            
            # Maintain rolling window of last 1000 conversations (prevent unbounded growth)
            if len(conversations) > 1000:
                conversations = conversations[-1000:]
            
            # Write updated conversations to file
            async with aiofiles.open(self.conversation_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(conversations, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Error guardando conversación:", e)


# Manager class for device-to-Telegram chat connections
# Tracks which device is connected to which Telegram chat for message delivery
class DeviceConnectionManager:
    def __init__(self):
        self.connections_file = "device_connections.json"
        self.connections = {}
    
    # Load device connections from persistent storage
    async def load_connections(self):
        """Cargar conexiones desde archivo"""
        try:
            if os.path.exists(self.connections_file):
                async with aiofiles.open(self.connections_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    self.connections = json.loads(content)
                    print(f"📂 Cargadas {len(self.connections)} conexiones de dispositivos")
            else:
                self.connections = {}
                print("📂 No hay conexiones previas de dispositivos")
        except Exception as e:
            print(f"Error cargando conexiones: {e}")
            self.connections = {}
    
    # Save device connections to persistent storage
    async def save_connections(self):
        """Guardar conexiones en archivo"""
        try:
            async with aiofiles.open(self.connections_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.connections, indent=2))
        except Exception as e:
            print(f"Error guardando conexiones: {e}")
    
    # Register device connection to specific Telegram chat
    async def connect_device(self, device_id, device_code, chat_id):
        """Conectar un dispositivo a un chat de Telegram"""
        self.connections[device_id] = {
            "chat_id": chat_id,
            "device_code": device_code,
            "connected_at": datetime.now().isoformat()
        }
        await self.save_connections()
        print(f"🔗 Dispositivo {device_id} conectado a chat {chat_id}")
    
    # Remove device connection record
    async def disconnect_device(self, device_id):
        """Desconectar un dispositivo"""
        if device_id in self.connections:
            del self.connections[device_id]
            await self.save_connections()
            print(f"🔗 Dispositivo {device_id} desconectado")
    
    # Retrieve Telegram chat ID for a given device
    async def get_chat_id_for_device(self, device_id):
        """Obtener chat_id para un dispositivo"""
        return self.connections.get(device_id, {}).get("chat_id")
    
    # Retrieve device ID for a given Telegram chat
    async def get_device_for_chat(self, chat_id):
        """Obtener dispositivo para un chat"""
        for device_id, info in self.connections.items():
            if info.get("chat_id") == chat_id:
                return device_id
        return None


# Initialize global device manager instance
device_manager = DeviceConnectionManager()

# Initialize Telegram bot if token is configured in environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_bot = None

if TELEGRAM_TOKEN:
    telegram_bot = FamilyMessagesBot(TELEGRAM_TOKEN)
    from telegram_bot import set_device_manager
    # Inject device manager into telegram bot for cross-module communication
    set_device_manager(device_manager)
    print("✅ device_manager inyectado en telegram_bot")
else:
    print("⚠️ TELEGRAM_BOT_TOKEN no configurado - funcionalidad de mensajes familiares deshabilitada")

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
    
    # Load previously saved device connections from file
    await device_manager.load_connections()
    
    device_id = None
    device_code = None
    
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
            # Generate unique 6-digit code
            existing_codes = [info.get("device_code") for info in device_manager.connections.values()]
            device_code = generate_unique_device_code(existing_codes)
            device_id = f"device_{device_code}"
            print(f"🆕 Nuevo dispositivo generado: {device_id} - Código: {device_code}")
        else:
            # Validate existing device code
            if device_id in device_manager.connections:
                # Reconnecting device - verify code matches
                existing_code = device_manager.connections[device_id].get("device_code")
                if existing_code != device_code:
                    print(f"⚠️ Conflicto de código detectado - usando código existente")
                    device_code = existing_code
                print(f"🔄 Dispositivo existente reconectado: {device_id} - Código: {device_code}")
            else:
                # New device with client-provided ID
                print(f"✅ Nuevo dispositivo registrado: {device_id} - Código: {device_code}")
        
        # Register or update device in connection manager
        if device_id not in device_manager.connections:
            device_manager.connections[device_id] = {
                "device_code": device_code,
                "connected_at": datetime.now().isoformat(),
                "chat_id": None
            }
            await device_manager.save_connections()
            print(f"📱 Dispositivo {device_id} registrado con código {device_code}")
        else:
            # Update last connection timestamp for existing device
            device_manager.connections[device_id]["last_connected"] = datetime.now().isoformat()
            await device_manager.save_connections()
        
        # Initialize memory manager for this device
        memory_manager = MemoryManager(device_id)
        
        # Track active WebSocket connections by device (initialize if needed)
        if not hasattr(device_manager, 'active_websockets'):
            device_manager.active_websockets = {}
        device_manager.active_websockets[device_id] = websocket
        print(f"🔌 WebSocket registrado para dispositivo {device_id}")
        
        # Send device information immediately to client for identification
        await websocket.send_text(json.dumps({
            "type": "device_info",
            "device_id": device_id,
            "device_code": device_code,
            "connected_chat": await device_manager.get_chat_id_for_device(device_id)
        }, ensure_ascii=False))

        print(f"📤 Información del dispositivo enviada - Código disponible: {device_code}")
        
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
                        continue
                    
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
                        continue
                except Exception:
                    # If not JSON, treat as plain text user message
                    pass

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
                                model = genai.GenerativeModel(GEMINI_MODEL)
                                generation_config = genai.types.GenerationConfig(
                                    max_output_tokens=1000,
                                    temperature=0.3
                                )
                                response = model.generate_content(prompt, generation_config=generation_config)
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
                                "messages": messages[:100]  # Limit to first 100 to prevent oversized payload
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
                        
                        continue
                        
                    except Exception as e:
                        print(f"❌ Error leyendo mensajes familiares: {e}")
                        traceback.print_exc()
                        # Error handling response
                        ai_response = "Lo siento querida, he tenido un problema al revisar tus mensajes. Intenta preguntarme de nuevo en un momento."
                        try:
                            await websocket.send_text(json.dumps({"type": "message", "text": ai_response}, ensure_ascii=False))
                        except:
                            pass
                        continue

                # Retrieve relevant memories for context in AI response
                relevant_memories = await memory_manager.get_relevant_memories(user_message)
                # Format memories for inclusion in AI prompt
                memory_context = ""
                if relevant_memories:
                    memory_context = "\n".join([f"- {mem['content']}" for mem in relevant_memories])
                        
                # Build main AI prompt with user message and context
                full_prompt = f"""
Eres "Compa", un compañero conversacional afectuoso.

{f"RECUERDOS PREVIOS DEL USUARIO (usa estos en tu respuesta):\n{memory_context}" if memory_context else "No tengo recuerdos específicos sobre este tema."}

Usuario: "{user_message}"

Instrucciones:
- Responde de manera natural y afectuosa
- Si hay recuerdos previos, menciónalos sutilmente
- 1-2 frases máximo, tono cálido
- Haz preguntas abiertas cuando sea apropiado

Respuesta:
"""

                # Keywords that trigger automatic memory saving
                important_keywords = [
                    "recuerdo cuando", "me acuerdo de", "mi hijo", "mi hija", "mi esposo", "mi esposa", 
                    "cuando era joven", "mi nieto", "mi nieta", "qué ilusión", "me encantaba",
                    "mi mamá", "mi papá", "mi familia", "cuando era niño", "cuando era niña", 
                    "en mi juventud", "aquellos tiempos", "me gustaba", "disfrutaba",
                    "extraño", "extrañar", "nostalgia", "añoro", "añorar", "tiempo pasado",
                    "cuando vivía", "cuando trabajaba", "mi infancia", "mi juventud"
                ]
                
                # Check if message contains memory-worthy content
                memory_saved = False

                if any(keyword in user_message.lower() for keyword in important_keywords):
                    # Automatically save user's memory to persistent storage
                    memory_saved = True
                    new_memory = await memory_manager.add_important_memory(user_message, "personal")
                    print(f"DEBUG: Recuerdo guardado: {new_memory['id']}")
                                    
                    # Send updated memory data to client for local sync
                    updated_memory = await memory_manager.load_memory()
                    conversation_history = await memory_manager.load_conversation_from_file()
                    await send_data_update_to_client(
                        websocket, 
                        updated_memory, 
                        conversation_history
                    )

                try:
                    # Validate Gemini API is configured
                    if not GEMINI_TOKEN:
                        ai_response = "Error: GEMINI_TOKEN no configurado."
                    else:
                        # Initialize Gemini model
                        model = genai.GenerativeModel(GEMINI_MODEL)

                        # Configure generation parameters for consistency
                        generation_config = genai.types.GenerationConfig(
                            max_output_tokens=250,
                            temperature=0.4,
                        )

                        # Check if user is asking about memories/past
                        is_memory_question = any(keyword in user_message.lower() for keyword in 
                                                 ["recuerdo", "recuerdos", "acuerdo", "memoria", "pasado", "cuando", "antes"])

                        # Customize prompt based on whether this is a memory-related question
                        if is_memory_question and memory_context:
                            # Specific prompt for memory recall questions with relevant context
                            full_prompt = f"""
Eres "Compa", un asistente especializado en Alzheimer. Responde con frases cortas y tono afectuoso.

INFORMACIÓN CRÍTICA - ESTOS SON LOS RECUERDOS REALES DEL USUARIO:
{memory_context}

El usuario te pregunta: "{user_message}"

RESPONDE mencionando específicamente los recuerdos de arriba. Si no encajan perfectamente, adapta tu respuesta afectivamente.

Tu respuesta (1-2 frases, mencionando los recuerdos):
"""
                        elif is_memory_question and not memory_context:
                            # Empathetic prompt for memory questions without context
                            full_prompt = f"""
Eres "Compa", un asistente especializado en Alzheimer.

El usuario pregunta: "{user_message}"

No tengo recuerdos específicos guardados sobre este tema. Responde con empatía.

Tu respuesta (1-2 frases, ofreciendo ayuda):
"""
                        else:
                            # General conversation prompt
                            full_prompt = f"""
Eres "Compa", un asistente especializado en Alzheimer.

{f"CONTEXTO DEL USUARIO: {memory_context}" if memory_context else ""}

Usuario: {user_message}

Tu respuesta (1-2 frases, tono afectuoso):
"""

                        print(f"DEBUG: Prompt enviado: {full_prompt}")

                        # Call Gemini API to generate response
                        response = model.generate_content(full_prompt)
                        ai_response = response.text.strip()

                        print(f"DEBUG: Respuesta cruda: {ai_response}")

                        # Verify response mentions memories if relevant memories exist
                        if is_memory_question and memory_context:
                            # Check if response actually uses the memories provided
                            response_uses_memories = any(
                                any(word in mem["content"].lower() for word in ai_response.lower().split()[:100])
                                for mem in relevant_memories
                            )

                            # Force memory mention if AI didn't naturally include them
                            if not response_uses_memories:
                                print("DEBUG: Forzando mención de recuerdos...")
                                memory_summary = ". ".join([mem["content"] for mem in relevant_memories[:2]])
                                ai_response = f"Recuerdo que me contaste: {memory_summary}. ¡Son momentos muy especiales!"

                        # Limit response to maximum 2 sentences to maintain brevity
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
                    # Sync updated conversation history to client
                    conversation_history = await memory_manager.load_conversation_from_file()
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

            except asyncio.TimeoutError:
                # Send periodic ping to detect stale connections
                try:
                    await websocket.send_text(json.dumps({"type":"ping","ts":datetime.now().timestamp()}, ensure_ascii=False))
                except:
                    pass
                continue

    except WebSocketDisconnect as ws_exc:
        # Client disconnected from WebSocket
        code = getattr(ws_exc, 'code', None)
        print(f"🔌 Cliente desconectado. WebSocketDisconnect code={code}")
        # Clean up WebSocket connection from active connections tracking
        if hasattr(device_manager, 'active_websockets') and device_id:
            if device_id in device_manager.active_websockets:
                del device_manager.active_websockets[device_id]
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
    """Returns all important memories for a specific device"""
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    
    memory_manager = MemoryManager(device_id)
    memory = await memory_manager.load_memory()
    return {
        "important_memories": memory["important_memories"],
        "total_memories": len(memory["important_memories"])
    }

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
    """Obtiene mensajes no leídos de familiares PARA UN DISPOSITIVO ESPECÍFICO"""
    print(f"🔍 SOLICITUD /family/messages - Device: {device_id}")
    
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        chat_id = await device_manager.get_chat_id_for_device(device_id)
        
        all_messages = await telegram_bot.load_messages()
        
       
        if chat_id:
            device_messages = [msg for msg in all_messages if msg.get("chat_id") == chat_id]
        else:
            device_messages = []  
        
        
        unread_messages = [msg for msg in device_messages if not msg.get("read", False)]
        
        
        device_messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        unread_messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {
            "messages": unread_messages,
            "all_messages": device_messages,
            "total_unread": len(unread_messages),
            "total_messages": len(device_messages),
            "connected_chat": chat_id  # Para debug
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get all family messages (including read ones)
@app.get("/family/messages/all")
async def get_all_family_messages(device_id: str = Query(...)):
    """Obtiene todos los mensajes familiares PARA UN DISPOSITIVO ESPECÍFICO"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        chat_id = await device_manager.get_chat_id_for_device(device_id)
        all_messages = await telegram_bot.load_messages()
        if chat_id:
            device_messages = [msg for msg in all_messages if msg.get("chat_id") == chat_id]
        else:
            device_messages = []
            
        return {
            "messages": device_messages,
            "total": len(device_messages),
            "connected_chat": chat_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get today's family messages
@app.get("/family/messages/today")
async def get_today_family_messages(device_id: str = Query(...)):
    """Obtiene mensajes del día de hoy PARA UN DISPOSITIVO ESPECÍFICO"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        chat_id = await device_manager.get_chat_id_for_device(device_id)
        today_messages = await telegram_bot.get_messages_today()
        if chat_id:
            device_messages = [msg for msg in today_messages if msg.get("chat_id") == chat_id]
        else:
            device_messages = []
            
        return {
            "messages": device_messages,
            "total": len(device_messages),
            "date": datetime.now().strftime("%d/%m/%Y"),
            "connected_chat": chat_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get messages from a specific date
@app.get("/family/messages/date/{date}")
async def get_messages_by_date(date: str, device_id: str = Query(...)):
    """Obtiene mensajes de una fecha específica PARA UN DISPOSITIVO ESPECÍFICO"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        # Obtain chat_id associated with this device
        chat_id = await device_manager.get_chat_id_for_device(device_id)
        date_formatted = date.replace("-", "/")
        all_date_messages = await telegram_bot.get_messages_by_date(date_formatted)
        
        if chat_id:
            device_messages = [msg for msg in all_date_messages if msg.get("chat_id") == chat_id]
        else:
            device_messages = []
            
        return {
            "messages": device_messages,
            "total": len(device_messages),
            "date": date_formatted,
            "connected_chat": chat_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mark a specific message as read
@app.post("/family/messages/{message_id}/read")
async def mark_message_read(message_id: int):
    """Marca un mensaje como leído"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        # Update message read status in Telegram bot
        success = await telegram_bot.mark_as_read(message_id)
        if success:
            return {"message": "Mensaje marcado como leído", "message_id": message_id}
        else:
            raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

# Serve index.html as root endpoint
@app.get("/")
async def read_root():
    """Serves the main frontend HTML file"""
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


# ============================================
# LIFECYCLE EVENTS - Startup and Shutdown hooks
# ============================================

# Initialize Telegram bot on server startup
@app.on_event("startup")
async def startup_event():
    """Inicia el bot de Telegram al arrancar la app"""
    if telegram_bot:
        # Schedule Telegram bot to start asynchronously
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