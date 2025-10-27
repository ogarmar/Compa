from random import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
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

try:
    from .telegram_bot import FamilyMessagesBot
except ImportError:
    from telegram_bot import FamilyMessagesBot

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


load_dotenv()

app = FastAPI(title="Asistente Alzheimer", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup Google Gemini API Client
GEMINI_TOKEN = os.getenv("GEMINI_TOKEN")
if not GEMINI_TOKEN:
    print("ERROR: GEMINI_TOKEN not found in environment variables.")
else:
    genai.configure(api_key=GEMINI_TOKEN)

GEMINI_MODEL = "gemini-2.5-flash-lite"  # DO NOT CHANGE THIS MODEL

# Constants for memory and conversation files
MEMORY_FILE = "user_memory.json"
CONVERSATION_FILE = "conversation_history.json"

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

def detect_message_intent(user_message):
    """Detección más inteligente de intenciones sobre mensajes"""
    lower_msg = user_message.lower()
    
    immediate_read_keywords = [
        "léeme", "lee", "leer", "dime", "cuéntame", "escucha", 
        "ponme", "reproduce", "escuchar", "oír", "qué dice",
        "qué escribió", "contenido", "mensaje", "recibir", "lee el"
    ]
    
    query_keywords = [
        "tengo", "hay", "mensajes", "familiares", "familiar",
        "alguno", "algún", "recibí", "llegó", "tienes"
    ]
    
    old_messages_keywords = [
        "antiguos", "antiguo", "leídos", "pasados", "anteriores", 
        "historial", "todos", "todos los", "todos mis"
    ]
    
    date_keywords = ["del", "de fecha", "de"]
    
    has_immediate = any(keyword in lower_msg for keyword in immediate_read_keywords)
    has_query = any(keyword in lower_msg for keyword in query_keywords)
    has_old = any(keyword in lower_msg for keyword in old_messages_keywords)
    has_date = any(keyword in lower_msg for keyword in date_keywords)
    
    explicit_date = parse_spanish_date_fragment(lower_msg) if any(word in lower_msg for word in ["del", "de"]) else None
    
    return {
        "is_read_intent": has_immediate,
        "is_query_intent": has_query,
        "wants_old_messages": has_old,
        "has_explicit_date": explicit_date is not None,
        "explicit_date": explicit_date
    }

def detect_intent(user_message):
    """Detecta la intención del usuario de manera más robusta"""
    lower_msg = user_message.lower()
    
    read_keywords = [
        "léeme", "lee", "leer", "dime", "cuéntame", "escucha", 
        "qué dice", "qué escribió", "contenido", "mensaje", "recibir",
        "ponme", "reproduce", "escuchar", "oír"
    ]
    
    query_keywords = ["tengo", "hay", "mensajes", "nuevos", "familiares"]
    
    is_read_intent = any(keyword in lower_msg for keyword in read_keywords)
    is_query_intent = any(keyword in lower_msg for keyword in query_keywords)
    
    return {
        "is_read_intent": is_read_intent,
        "is_query_intent": is_query_intent,
        "wants_immediate_reading": is_read_intent
    }

def parse_spanish_date_fragment(text):
    """
    Intenta extraer una fecha en formato dd/mm[/yyyy] desde textos tipo:
    "20 de octubre", "20 octubre 2025", "el 3 de mayo", "5/10", "05-10-2025".
    Devuelve 'dd/mm/yyyy' o None si no la encuentra.
    """
    text = text.lower().strip()

    m = re.search(r'\b(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?\b', text)
    if m:
        d = int(m.group(1)); mo = int(m.group(2))
        y = m.group(3)
        if y:
            y = int(y)
            if y < 100:  
                y += 2000
        else:
            y = datetime.now().year
        try:
            return f"{d:02d}/{mo:02d}/{int(y)}"
        except Exception:
            return None

    m2 = re.search(r'\b(\d{1,2})\s*(?:de\s+)?([a-záéíóúñ]+)(?:\s+(\d{2,4}))?\b', text, flags=re.IGNORECASE)
    if m2:
        d = int(m2.group(1))
        month_word = m2.group(2).lower()
        y = m2.group(3)
        month_num = SPANISH_MONTHS.get(month_word)
        if month_num:
            if y:
                y = int(y)
                if y < 100:
                    y += 2000
            else:
                y = datetime.now().year
            try:
                return f"{d:02d}/{month_num:02d}/{int(y)}"
            except Exception:
                return None
    return None

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
    return b.decode("latin-1", errors="replace"), "latin-1(replace)"

def generate_unique_device_code(existing_codes):
    """Genera un código de 6 dígitos que no existe en existing_codes"""
    max_attempts = 100
    for _ in range(max_attempts):
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        if code not in existing_codes:
            return code
    # Si llegamos aquí, usar timestamp como fallback
    import time
    return str(int(time.time()))[-6:]

class MemoryManager:
    def __init__(self, device_id):
        self.device_id = device_id
        self.memory_file = MEMORY_FILE
        self.conversation_file = CONVERSATION_FILE
        
    async def load_memory_from_client(self, client_data):
        """Carga memoria desde datos enviados por el cliente"""
        if client_data:
            print("✅ Cargando memoria desde datos del cliente")
            return client_data
        else:
            return await self.load_memory() 
    
    async def save_memory_for_client(self, memory_data):
        """Prepara datos para que el cliente los guarde localmente"""
        return memory_data
    
    async def load_conversation_from_client(self, client_data):
        """Carga conversación desde datos del cliente"""
        if client_data:
            print("✅ Cargando conversación desde datos del cliente")
            return client_data
        else:
            return await self.load_conversation_from_file()
    
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
        
    async def load_memory(self):
        if not os.path.exists(self.memory_file):
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
            async with aiofiles.open(self.memory_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except UnicodeDecodeError as ude:
            print("Error leyendo memoria (utf-8):", ude)
            try:
                async with aiofiles.open(self.memory_file, 'rb') as f:
                    raw_bytes = await f.read()
                text, used_enc = _try_decode_bytes(raw_bytes)
                print(f"Decoded memory file with fallback encoding: {used_enc}. Normalizing to utf-8...")
                data = json.loads(text)
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
        
    async def save_memory(self, memory_data):
        try:
            async with aiofiles.open(self.memory_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(memory_data, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Error guardando memoria:", e)
        
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
        
    async def get_relevant_memories(self, query, limit=3):
        memory = await self.load_memory()
        relevant = []
        query_words = query.lower().split()
        
        for mem in memory["important_memories"]:
            memory_text = mem["content"].lower()
            direct_match = any(word in memory_text for word in query_words if len(word) > 3)
            
            if any(word in query.lower() for word in ["recuerdo", "recuerdos", "acuerdo", "memoria"]):
                relevant.append(mem)
            elif direct_match:
                relevant.append(mem)
        
        relevant.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return relevant[:limit]
        
    async def save_conversation(self, user_message, assistant_response):
        try:
            conversations = []
            if os.path.exists(self.conversation_file):
                try:
                    async with aiofiles.open(self.conversation_file, 'r', encoding='utf-8') as f:
                        conversations = json.loads(await f.read())
                except UnicodeDecodeError:
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
            
            conversation_entry = {
                "timestamp": datetime.now().isoformat(),
                "user": user_message,
                "assistant": assistant_response
            }
            conversations.append(conversation_entry)
            if len(conversations) > 1000:
                conversations = conversations[-1000:]
            async with aiofiles.open(self.conversation_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(conversations, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Error guardando conversación:", e)


class DeviceConnectionManager:
    def __init__(self):
        self.connections_file = "device_connections.json"
        self.connections = {}
    
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
    
    async def save_connections(self):
        """Guardar conexiones en archivo"""
        try:
            async with aiofiles.open(self.connections_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.connections, indent=2))
        except Exception as e:
            print(f"Error guardando conexiones: {e}")
    
    async def connect_device(self, device_id, device_code, chat_id):
        """Conectar un dispositivo a un chat de Telegram"""
        self.connections[device_id] = {
            "chat_id": chat_id,
            "device_code": device_code,
            "connected_at": datetime.now().isoformat()
        }
        await self.save_connections()
        print(f"🔗 Dispositivo {device_id} conectado a chat {chat_id}")
    
    async def disconnect_device(self, device_id):
        """Desconectar un dispositivo"""
        if device_id in self.connections:
            del self.connections[device_id]
            await self.save_connections()
            print(f"🔗 Dispositivo {device_id} desconectado")
    
    async def get_chat_id_for_device(self, device_id):
        """Obtener chat_id para un dispositivo"""
        return self.connections.get(device_id, {}).get("chat_id")
    
    async def get_device_for_chat(self, chat_id):
        """Obtener dispositivo para un chat"""
        for device_id, info in self.connections.items():
            if info.get("chat_id") == chat_id:
                return device_id
        return None


device_manager = DeviceConnectionManager()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_bot = None

if TELEGRAM_TOKEN:
    telegram_bot = FamilyMessagesBot(TELEGRAM_TOKEN)
    from telegram_bot import set_device_manager
    set_device_manager(device_manager)
    print("✅ device_manager inyectado en telegram_bot")
else:
    print("⚠️ TELEGRAM_BOT_TOKEN no configurado - funcionalidad de mensajes familiares deshabilitada")

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
# WEBSOCKET ENDPOINT
# ============================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ Nueva conexión WebSocket establecida")
    
    await device_manager.load_connections()
    
    device_id = None
    device_code = None
    
    try:
        initial_data = None
        try:
            initial_msg = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            data = json.loads(initial_msg)
            if data.get("type") == "initial_data":
                initial_data = data.get("data", {})
                device_id = initial_data.get("device_id")
                device_code = initial_data.get("device_code")
                print(f"📥 Datos iniciales recibidos - Device: {device_id} - Código: {device_code}")
        except (asyncio.TimeoutError, json.JSONDecodeError, KeyError):
            print("ℹ️ Cliente no envió datos iniciales")
        
        # Validar y generar device_id si es necesario
        if not device_id or not device_code:
            # Generar nuevo código de 6 dígitos
            existing_codes = [info.get("device_code") for info in device_manager.connections.values()]
            device_code = generate_unique_device_code(existing_codes)
            device_id = f"device_{device_code}"
            print(f"🆕 Nuevo dispositivo generado: {device_id} - Código: {device_code}")
        else:
            # Verificar si el device_id ya existe en las conexiones
            if device_id in device_manager.connections:
                # Dispositivo existente reconectándose
                existing_code = device_manager.connections[device_id].get("device_code")
                if existing_code != device_code:
                    print(f"⚠️ Conflicto de código detectado - usando código existente")
                    device_code = existing_code
                print(f"🔄 Dispositivo existente reconectado: {device_id} - Código: {device_code}")
            else:
                # Nuevo dispositivo con ID del cliente
                print(f"✅ Nuevo dispositivo registrado: {device_id} - Código: {device_code}")
        
        # Registrar dispositivo en device_manager
        if device_id not in device_manager.connections:
            device_manager.connections[device_id] = {
                "device_code": device_code,
                "connected_at": datetime.now().isoformat(),
                "chat_id": None
            }
            await device_manager.save_connections()
            print(f"📱 Dispositivo {device_id} registrado con código {device_code}")
        else:
            # Actualizar timestamp de última conexión
            device_manager.connections[device_id]["last_connected"] = datetime.now().isoformat()
            await device_manager.save_connections()
        
        # Crear memory manager
        memory_manager = MemoryManager(device_id)
        if not hasattr(device_manager, 'active_websockets'):
            device_manager.active_websockets = {}
        device_manager.active_websockets[device_id] = websocket
        print(f"🔌 WebSocket registrado para dispositivo {device_id}")
        # Enviar información del dispositivo INMEDIATAMENTE
        await websocket.send_text(json.dumps({
            "type": "device_info",
            "device_id": device_id,
            "device_code": device_code,
            "connected_chat": await device_manager.get_chat_id_for_device(device_id)
        }, ensure_ascii=False))

        print(f"📤 Información del dispositivo enviada - Código disponible: {device_code}")
        
       
        
        # Mensaje de bienvenida inicial
        try:
            current_hour = datetime.now().hour
            
            if 5 <= current_hour < 12:
                greeting = "Buenos días"
            elif 12 <= current_hour < 19:
                greeting = "Buenas tardes"
            else:
                greeting = "Buenas noches"
            
            welcome_text = f"{greeting} querida, soy Compa. Estoy aquí para acompañarte. ¿Cómo te sientes?"
            
            await websocket.send_text(json.dumps({
                "type": "message",
                "text": welcome_text
            }, ensure_ascii=False))
            
            print(f"👋 Mensaje de bienvenida enviado")
            
        except Exception as e:
            print(f"⚠️ Error enviando mensaje de bienvenida: {e}")

        awaiting_read_confirmation = False
        pending_family_messages = []

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=300.0)
                raw = data.strip()
                if not raw:
                    continue

                try:
                    maybe = json.loads(raw)
                    
                    # ⬇️ NUEVO: Manejar respuesta de conexión
                    if isinstance(maybe, dict) and maybe.get("type") == "connection_response":
                        request_id = maybe.get("request_id")
                        approved = maybe.get("approved", False)
                        
                        if telegram_bot:
                            await telegram_bot.process_connection_response(
                                request_id, 
                                approved, 
                                websocket
                            )
                        continue
                    
                    if isinstance(maybe, dict) and maybe.get("type") == "keepalive":
                        try:
                            await websocket.send_text(json.dumps({"type": "pong", "ts": datetime.now().timestamp()}, ensure_ascii=False))
                        except:
                            try:
                                await websocket.send_text("pong")
                            except:
                                pass
                        print(f"📶 Keepalive recibido: {maybe.get('ts')}")
                        continue
                except Exception:
                    pass

                user_message = raw
                if not user_message:
                    continue

                print(f"📥 Mensaje recibido: {user_message}")
                
                family_keywords = [
                    "mensaje", "mensajes", "familiar", "familiares", "familia",
                    "léeme", "lee", "leer", "dime", "cuéntame", "hay", "tienes", "tengo"
                ]
                
                is_about_messages = any(word in user_message.lower() for word in ["mensaje", "familia", "familiar"])
                is_family_request = is_about_messages and any(word in user_message.lower() for word in family_keywords)
                
                asking_today = any(word in user_message.lower() for word in ["hoy", "día de hoy", "del día", "de hoy"])
                
                print(f"🔍 is_family_request={is_family_request}, asking_today={asking_today}")

                if is_family_request and telegram_bot:
                    try:
                        print(f"🔍 Detectada solicitud de mensajes familiares: '{user_message}'")
                        
                        intent = detect_message_intent(user_message)
                        
                        if intent["has_explicit_date"]:
                            messages = await telegram_bot.get_messages_by_date(intent["explicit_date"])
                            message_type = f"del {intent['explicit_date']}"
                        elif intent["wants_old_messages"] or any(word in user_message.lower() for word in ["antiguos", "todos", "historial"]):
                            all_messages = await telegram_bot.load_messages()
                            messages = all_messages
                            message_type = "guardados"
                        else:
                            messages = await telegram_bot.get_unread_messages()
                            message_type = "nuevos"
                        
                        print(f"📬 Mensajes {message_type} encontrados: {len(messages)}")
                        
                        if messages:
                            prompt = FAMILY_MESSAGES_PROMPT.format(
                                count=len(messages),
                                user_message=user_message
                            )
                            
                            try:
                                model = genai.GenerativeModel(GEMINI_MODEL)
                                generation_config = genai.types.GenerationConfig(
                                    max_output_tokens=1000,
                                    temperature=0.3
                                )
                                response = model.generate_content(prompt, generation_config=generation_config)
                                ai_response = response.text.strip()
                            except Exception as e:
                                print("Error generando respuesta breve:", e)
                                ai_response = f"Tienes {len(messages)} mensajes {message_type}."
                            
                            await websocket.send_text(json.dumps({
                                "type": "message",
                                "text": ai_response,
                                "has_family_messages": True,
                                "messages": messages[:100]
                            }, ensure_ascii=False))
                            
                            print(f"✅ Enviados {len(messages)} mensajes {message_type} para lectura")
                            
                        else:
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
                        ai_response = "Lo siento querida, he tenido un problema al revisar tus mensajes. Intenta preguntarme de nuevo en un momento."
                        try:
                            await websocket.send_text(json.dumps({"type": "message", "text": ai_response}, ensure_ascii=False))
                        except:
                            pass
                        continue

                relevant_memories = await memory_manager.get_relevant_memories(user_message)
                memory_context = ""
                if relevant_memories:
                    memory_context = "\n".join([f"- {mem['content']}" for mem in relevant_memories])
                        
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

                important_keywords = [
                    "recuerdo cuando", "me acuerdo de", "mi hijo", "mi hija", "mi esposo", "mi esposa", 
                    "cuando era joven", "mi nieto", "mi nieta", "qué ilusión", "me encantaba",
                    "mi mamá", "mi papá", "mi familia", "cuando era niño", "cuando era niña", 
                    "en mi juventud", "aquellos tiempos", "me gustaba", "disfrutaba",
                    "extraño", "extrañar", "nostalgia", "añoro", "añorar", "tiempo pasado",
                    "cuando vivía", "cuando trabajaba", "mi infancia", "mi juventud"
                ]
                memory_saved = False

                if any(keyword in user_message.lower() for keyword in important_keywords):
                    memory_saved = True
                    new_memory = await memory_manager.add_important_memory(user_message, "personal")
                    print(f"DEBUG: Recuerdo guardado: {new_memory['id']}")
                                    
                    updated_memory = await memory_manager.load_memory()
                    conversation_history = await memory_manager.load_conversation_from_file()
                    await send_data_update_to_client(
                        websocket, 
                        updated_memory, 
                        conversation_history
                    )

                try:
                    if not GEMINI_TOKEN:
                        ai_response = "Error: GEMINI_TOKEN no configurado."
                    else:
                        model = genai.GenerativeModel(GEMINI_MODEL)

                        generation_config = genai.types.GenerationConfig(
                            max_output_tokens=250,
                            temperature=0.4,
                        )

                        is_memory_question = any(keyword in user_message.lower() for keyword in 
                                                 ["recuerdo", "recuerdos", "acuerdo", "memoria", "pasado", "cuando", "antes"])

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

                        response = model.generate_content(full_prompt)
                        ai_response = response.text.strip()

                        print(f"DEBUG: Respuesta cruda: {ai_response}")

                        if is_memory_question and memory_context:
                            response_uses_memories = any(
                                any(word in mem["content"].lower() for word in ai_response.lower().split()[:100])
                                for mem in relevant_memories
                            )

                            if not response_uses_memories:
                                print("DEBUG: Forzando mención de recuerdos...")
                                memory_summary = ". ".join([mem["content"] for mem in relevant_memories[:2]])
                                ai_response = f"Recuerdo que me contaste: {memory_summary}. ¡Son momentos muy especiales!"

                        sentences = [s.strip() for s in ai_response.split('.') if s.strip()]
                        if len(sentences) > 2:
                            ai_response = '. '.join(sentences[:2]) + '.'

                        if memory_saved and "recuerdo" not in ai_response.lower():
                            ai_response += " ¡Qué bonito recuerdo! Lo guardaré en tu cofre especial."

                except Exception as e:
                    print("Error Gemini API:", e)
                    traceback.print_exc()

                    if memory_saved:
                        memory_count = len((await memory_manager.load_memory())["important_memories"])
                        ai_response = f"¡Qué bonito recuerdo! Lo he guardado en tu cofre. Ya tienes {memory_count} recuerdos especiales conmigo."
                    elif memory_context and is_memory_question:
                        memory_list = "\n".join([f"- {mem['content']}" for mem in relevant_memories])
                        ai_response = f"Tus recuerdos especiales:\n{memory_list}\n\n¿Te gustaría que hablemos más de alguno?"
                    else:
                        ai_response = "Estoy aquí para acompañarte. ¿Podrías contarme más sobre lo que necesitas?"

                try:
                    await memory_manager.save_conversation(user_message, ai_response)
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
                    payload = {"type": "message", "text": ai_response}
                    await websocket.send_text(json.dumps(payload, ensure_ascii=False))
                except Exception as e:
                    print("Error enviando respuesta por websocket:", e)

            except asyncio.TimeoutError:
                try:
                    await websocket.send_text(json.dumps({"type":"ping","ts":datetime.now().timestamp()}, ensure_ascii=False))
                except:
                    pass
                continue

    except WebSocketDisconnect as ws_exc:
        code = getattr(ws_exc, 'code', None)
        print(f"🔌 Cliente desconectado. WebSocketDisconnect code={code}")
        if hasattr(device_manager, 'active_websockets') and device_id:
            if device_id in device_manager.active_websockets:
                del device_manager.active_websockets[device_id]
                print(f"🗑️ WebSocket eliminado para dispositivo {device_id}")
    except Exception as e:
        print(f"❌ Error en WebSocket: {e}")
        traceback.print_exc()
        try:
            await websocket.send_text(json.dumps({"type":"error","text":"Lo siento, ha ocurrido un error. Por favor inténtalo de nuevo."}, ensure_ascii=False))
        except:
            pass


# ============================================
# HTTP ENDPOINTS - UTILITIES
# ============================================

@app.get("/search")
async def search_web(query: str):
    try:
        results = []
        for result in search(query, num_results=3, lang="es"):
            results.append(result)
        return {"results": results}
    except Exception as e:
        return {"error": str(e)}


# ============================================
# MEMORY MANAGEMENT HTTP ENDPOINTS
# ============================================

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

@app.post("/memory/cofre")
async def add_memory_cofre(memory_data: dict):
    """Manually adds a new memory"""
    device_id = memory_data.get("device_id")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    
    memory_manager = MemoryManager(device_id)
    memory_text = memory_data.get("content", "")
    category = memory_data.get("category", "personal")
    
    if memory_text:
        new_memory = await memory_manager.add_important_memory(memory_text, category)
        return {"message": "Recuerdo guardado exitosamente", "memory": new_memory}
    else:
        raise HTTPException(status_code=400, detail="El contenido del recuerdo no puede estar vacío")

@app.get("/memory/search")
async def search_memories(device_id: str, query: str):
    """Searches for relevant memories"""
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    
    memory_manager = MemoryManager(device_id)
    relevant_memories = await memory_manager.get_relevant_memories(query)
    return {
        "query": query,
        "memories": relevant_memories,
        "count": len(relevant_memories)
    }

@app.get("/debug/memory")
async def debug_memory(device_id: str):
    """Debug endpoint to check memory status"""
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

@app.get("/memory/verify")
async def verify_memory_usage(device_id: str):
    """Test memory search function"""
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    
    memory_manager = MemoryManager(device_id)
    memory = await memory_manager.load_memory()
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

@app.get("/family/messages")
async def get_family_messages():
    """Obtiene mensajes no leídos de familiares"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        all_messages = await telegram_bot.load_messages()
        unread_messages = [msg for msg in all_messages if not msg.get("read", False)]
        
        all_messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        unread_messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {
            "messages": unread_messages,
            "all_messages": all_messages,
            "total_unread": len(unread_messages),
            "total_messages": len(all_messages)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/family/messages/all")
async def get_all_family_messages():
    """Obtiene todos los mensajes familiares"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        messages = await telegram_bot.load_messages()
        return {
            "messages": messages,
            "total": len(messages)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/family/messages/today")
async def get_today_family_messages():
    """Obtiene mensajes del día de hoy"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        messages = await telegram_bot.get_messages_today()
        return {
            "messages": messages,
            "total": len(messages),
            "date": datetime.now().strftime("%d/%m/%Y")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/family/messages/date/{date}")
async def get_messages_by_date(date: str):
    """Obtiene mensajes de una fecha específica (formato: dd-mm-yyyy)"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
        date_formatted = date.replace("-", "/")
        messages = await telegram_bot.get_messages_by_date(date_formatted)
        return {
            "messages": messages,
            "total": len(messages),
            "date": date_formatted
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/family/messages/{message_id}/read")
async def mark_message_read(message_id: int):
    """Marca un mensaje como leído"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot de Telegram no configurado")
    
    try:
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

@app.get("/admin/authorized-users")
async def get_authorized_users():
    """Lista usuarios autorizados"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot no configurado")
    
    try:
        users = await telegram_bot.load_authorized_users()
        return {
            "authorized_users": users,
            "total": len(users)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        success = await telegram_bot.add_authorized_user(int(chat_id))
        if success:
            return {"message": f"Usuario {chat_id} autorizado correctamente"}
        else:
            return {"message": f"Usuario {chat_id} ya estaba autorizado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        success = await telegram_bot.remove_authorized_user(int(chat_id))
        if success:
            return {"message": f"Usuario {chat_id} revocado correctamente"}
        else:
            return {"message": f"Usuario {chat_id} no estaba en la lista"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/pending-requests")
async def get_pending_requests():
    """Muestra usuarios que intentaron usar el bot sin autorización"""
    if not telegram_bot:
        raise HTTPException(status_code=503, detail="Bot no configurado")
    
    try:
        messages = await telegram_bot.load_messages()
        authorized = await telegram_bot.load_authorized_users()
        
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
# FRONTEND STATIC FILES
# ============================================

script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, '..'))
frontend_path = os.path.join(project_root, 'frontend')

print("FRONTEND_PATH =", frontend_path)
try:
    print("Files in frontend:", os.listdir(frontend_path))
except Exception as ex:
    print("No se encontró frontend folder:", ex)

if os.path.isdir(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")
else:
    print("Warning: frontend_path does not exist.")

@app.get("/")
async def read_root():
    index_file = os.path.join(frontend_path, 'index.html')
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Index not found."}

@app.get("/favicon.ico")
async def favicon():
    path = os.path.join(frontend_path, "favicon.ico")
    if os.path.exists(path):
        return FileResponse(path)
    
    return FileResponse(os.path.join(frontend_path, 'index.html'))

@app.get("/health")
async def health_check():
    return {
        "status": "running",
        "ai_provider": "google_gemini",
        "model": GEMINI_MODEL,
        "gemini_configured": GEMINI_TOKEN is not None,
        "telegram_configured": telegram_bot is not None
    }


# ============================================
# EVENTS
# ============================================

@app.on_event("startup")
async def startup_event():
    """Inicia el bot de Telegram al arrancar la app"""
    if telegram_bot:
        asyncio.create_task(telegram_bot.start_bot())
        print("🤖 Bot de Telegram iniciándose...")

@app.on_event("shutdown")
async def shutdown_event():
    """Detiene el bot al cerrar la app"""
    if telegram_bot:
        await telegram_bot.stop_bot()


# ============================================
# SERVER EXECUTION
# ============================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting server on port {port}")
    print(f"📊 Model: {GEMINI_MODEL}")
    
    host = "0.0.0.0" if os.environ.get("RENDER") else "localhost"
    reload = not os.environ.get("RENDER") 
    
    uvicorn.run(
        "main:app", 
        host=host, 
        port=port, 
        reload=reload,
        log_level="info"
    )