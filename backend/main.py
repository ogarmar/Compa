from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import os
import json
import aiofiles
from datetime import datetime
from dotenv import load_dotenv
import asyncio
from googlesearch import search
import traceback
import google.generativeai as genai
from telegram_bot import FamilyMessagesBot

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

# Telegram Bot Setup
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_bot = None

if TELEGRAM_TOKEN:
    telegram_bot = FamilyMessagesBot(TELEGRAM_TOKEN)
else:
    print("⚠️ TELEGRAM_BOT_TOKEN no configurado - funcionalidad de mensajes familiares deshabilitada")

ALZHEIMER_PROMPT = """
Eres "Acompaña", un asistente de voz compasivo especializado en ayudar a personas con Alzheimer.

DIRECTIVAS ESTRICTAS:
1. Paciencia infinita: Repite las respuestas con la misma calma las veces necesarias
2. Lenguaje simple: Frases cortas, vocabulario básico, tono afectuoso
3. No contradigas: Si menciona recuerdos inexactos, acompáñalos afectivamente
4. Refuerzo positivo: Usa palabras como "querido/a", "valiente", "importante"
5. Reorientación suave: Si está confundido, ofrece ayuda práctica sin correcciones
6. Estímulos positivos: Sugiere actividades sencillas y placenteras
7. Seguridad emocional: Transmite calma y estabilidad en cada respuesta

Mantén las respuestas en 1-2 frases máximo.
"""

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
    # fallback for safety
    return b.decode("latin-1", errors="replace"), "latin-1(replace)"


class MemoryManager:
    def __init__(self):
        self.memory_file = MEMORY_FILE
        self.conversation_file = CONVERSATION_FILE
        
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
        # Adds a new memory to the list and saves the file
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
        # Finds memories related to the user's query
        memory = await self.load_memory()
        relevant = []
        query_words = query.lower().split()
        
        # Simple relevance check based on keywords
        for mem in memory["important_memories"]:
            memory_text = mem["content"].lower()
            direct_match = any(word in memory_text for word in query_words if len(word) > 3)
            
            # If it's a general question about memories, return recent ones
            if any(word in query.lower() for word in ["recuerdo", "recuerdos", "acuerdo", "memoria"]):
                relevant.append(mem)
            elif direct_match:
                relevant.append(mem)
        
        # Sort by most recent first
        relevant.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return relevant[:limit]
        
    async def save_conversation(self, user_message, assistant_response):
        # Saves the user message and assistant's response to history with utf-8 safe I/O
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
            # Keep only the last 100 entries
            if len(conversations) > 100:
                conversations = conversations[-100:]
            async with aiofiles.open(self.conversation_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(conversations, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Error guardando conversación:", e)

memory_manager = MemoryManager()


# WEBSOCKET

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ Nueva conexión WebSocket establecida")
    
    try:
        user_memory = await memory_manager.load_memory()
        try:
            await websocket.send_text(json.dumps({"type":"message","text":"Hola querido usuario. Soy Acompaña, tu asistente personal. Estoy aquí para ayudarte."}, ensure_ascii=False))
        except Exception as e:
            print("No se pudo enviar saludo inicial por WS:", e)
        
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=300.0)
                raw = data.strip()
                if not raw:
                    continue

                try:
                    maybe = json.loads(raw)
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
                        
                        if asking_today:
                            today_messages = await telegram_bot.get_messages_today()
                            print(f"📅 Mensajes de hoy encontrados: {len(today_messages)}")
                            
                            if today_messages:
                                messages_text = []
                                for msg in today_messages:
                                    msg_str = f"{msg['sender_name']} te escribió a las {msg['time']}: {msg['message']}"
                                    messages_text.append(msg_str)
                                    if not msg.get('read'):
                                        await telegram_bot.mark_as_read(msg['id'])
                                
                                ai_response = f"Tienes {len(today_messages)} mensaje{'s' if len(today_messages) > 1 else ''} de hoy. " + messages_text[0]
                            else:
                                ai_response = "No tienes mensajes nuevos de hoy, querida."
                        else:
                            unread = await telegram_bot.get_unread_messages()
                            print(f"📬 Mensajes no leídos encontrados: {len(unread)}")
                            
                            if unread:
                                first_msg = unread[0]
                                date_str = first_msg.get('date', 'recientemente')
                                time_str = first_msg.get('time', '')
                                sender = first_msg.get('sender_name', 'un familiar')
                                message_content = first_msg.get('message', '')
                                
                                if date_str != 'recientemente' and time_str:
                                    ai_response = f"Sí, querida. Tienes {len(unread)} mensaje{'s' if len(unread) > 1 else ''} nuevo{'s' if len(unread) > 1 else ''}. El primero es de {sender} del día {date_str} a las {time_str}: {message_content}"
                                else:
                                    ai_response = f"Sí, querida. Tienes {len(unread)} mensaje{'s' if len(unread) > 1 else ''} nuevo{'s' if len(unread) > 1 else ''}. El primero es de {sender}: {message_content}"
                                
                                print(f"✅ Mensaje a narrar: {ai_response[:100]}")
                                
                                await telegram_bot.mark_as_read(first_msg['id'])
                            else:
                                ai_response = "No tienes mensajes nuevos de tus familiares en este momento, querida."
                                print("ℹ️ No hay mensajes no leídos")
                        
                        try:
                            await memory_manager.save_conversation(user_message, ai_response)
                        except Exception as e:
                            print("Warning: fallo guardando conversación:", e)
                        
                        try:
                            payload = {"type": "message", "text": ai_response}
                            await websocket.send_text(json.dumps(payload, ensure_ascii=False))
                        except Exception as e:
                            print("Error enviando respuesta por websocket:", e)
                        
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

                # search relevant memories
                relevant_memories = await memory_manager.get_relevant_memories(user_message)
                memory_context = ""
                if relevant_memories:
                    memory_context = " | ".join([mem["content"] for mem in relevant_memories])
                    print(f"DEBUG: Recuerdos encontrados: {len(relevant_memories)}")
                    print(f"DEBUG: Contexto de memoria: {memory_context}")

                important_keywords = ["recuerdo cuando", "me acuerdo de", "mi hijo", "mi hija", "mi esposo", "mi esposa", "cuando era joven", "mi nieto", "mi nieta", "qué ilusión", "me encantaba"]
                memory_saved = False

                if any(keyword in user_message.lower() for keyword in important_keywords):
                    memory_saved = True
                    new_memory = await memory_manager.add_important_memory(user_message, "personal")
                    print(f"DEBUG: Recuerdo guardado: {new_memory['id']}")

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
Eres "Acompaña", un asistente especializado en Alzheimer. Responde con frases cortas y tono afectuoso.

INFORMACIÓN CRÍTICA - ESTOS SON LOS RECUERDOS REALES DEL USUARIO:
{memory_context}

El usuario te pregunta: "{user_message}"

RESPONDE mencionando específicamente los recuerdos de arriba. Si no encajan perfectamente, adapta tu respuesta afectivamente.

Tu respuesta (1-2 frases, mencionando los recuerdos):
"""
                        elif is_memory_question and not memory_context:
                            full_prompt = f"""
Eres "Acompaña", un asistente especializado en Alzheimer.

El usuario pregunta: "{user_message}"

No tengo recuerdos específicos guardados sobre este tema. Responde con empatía.

Tu respuesta (1-2 frases, ofreciendo ayuda):
"""
                        else:
                            full_prompt = f"""
Eres "Acompaña", un asistente especializado en Alzheimer.

{f"CONTEXTO DEL USUARIO: {memory_context}" if memory_context else ""}

Usuario: {user_message}

Tu respuesta (1-2 frases, tono afectuoso):
"""

                        print(f"DEBUG: Prompt enviado: {full_prompt}")

                        # Gemini call
                        response = model.generate_content(full_prompt)
                        ai_response = response.text.strip()

                        print(f"DEBUG: Respuesta cruda: {ai_response}")

                        if is_memory_question and memory_context:
                            response_uses_memories = any(
                                any(word in mem["content"].lower() for word in ai_response.lower().split()[:10])
                                for mem in relevant_memories
                            )

                            if not response_uses_memories:
                                print("DEBUG: Forzando mención de recuerdos...")
                                memory_summary = ". ".join([mem["content"] for mem in relevant_memories[:2]])
                                ai_response = f"Recuerdo que me contaste: {memory_summary}. ¡Son momentos muy especiales!"

                        # TODOOOOOOOO CHAGNE
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
    except Exception as e:
        print(f"❌ Error en WebSocket: {e}")
        traceback.print_exc()
        try:
            await websocket.send_text(json.dumps({"type":"error","text":"Lo siento, ha ocurrido un error. Por favor inténtalo de nuevo."}, ensure_ascii=False))
        except:
            pass

# HTTP endpoints for utilities and memory management
@app.get("/search")
async def search_web(query: str):
    # Searches the web using googlesearch library
    try:
        results = []
        for result in search(query, num_results=3, lang="es"):
            results.append(result)
        return {"results": results}
    except Exception as e:
        return {"error": str(e)}

@app.get("/memory/cofre")
async def get_memory_cofre():
    # Returns all important memories
    memory = await memory_manager.load_memory()
    return {
        "important_memories": memory["important_memories"],
        "total_memories": len(memory["important_memories"])
    }

@app.post("/memory/cofre")
async def add_memory_cofre(memory_data: dict):
    # Manually adds a new memory
    memory_text = memory_data.get("content", "")
    category = memory_data.get("category", "personal")
    if memory_text:
        new_memory = await memory_manager.add_important_memory(memory_text, category)
        return {"message": "Recuerdo guardado exitosamente", "memory": new_memory}
    else:
        raise HTTPException(status_code=400, detail="El contenido del recuerdo no puede estar vacío")

@app.get("/memory/search")
async def search_memories(query: str):
    # Searches for relevant memories
    relevant_memories = await memory_manager.get_relevant_memories(query)
    return {
        "query": query,
        "memories": relevant_memories,
        "count": len(relevant_memories)
    }

@app.get("/debug/memory")
async def debug_memory():
    # Debug endpoint to check memory status
    memory = await memory_manager.load_memory()
    return {
        "total_memories": len(memory["important_memories"]),
        "all_memories": memory["important_memories"],
        "memory_file_exists": os.path.exists(MEMORY_FILE)
    }

@app.get("/memory/verify")
async def verify_memory_usage():
    # Test memory search function
    memory = await memory_manager.load_memory()
    test_query = "mis recuerdos"
    relevant_memories = await memory_manager.get_relevant_memories(test_query)
    
    return {
        "total_memories": len(memory["important_memories"]),
        "test_query": test_query,
        "found_memories": len(relevant_memories),
        "sample_memories": [mem["content"][:100] + "..." for mem in relevant_memories[:3]] if relevant_memories else []
    }


# FAMILY MESSAGES ENDPOINTS

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
        # Change format from URL (dd-mm-yyyy) to internal format (dd/mm/yyyy)
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


# ADMIN ENDPOINTS - auth users

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

# Frontend static file serving
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, '..'))
frontend_path = os.path.join(project_root, 'frontend')

print("FRONTEND_PATH =", frontend_path)
try:
    print("Files in frontend:", os.listdir(frontend_path))
except Exception as ex:
    print("No se encontró frontend folder:", ex)

if os.path.isdir(frontend_path):
    # Mount static files for the frontend
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
    # Simple health check endpoint
    return {
        "status": "running",
        "ai_provider": "google_gemini",
        "model": GEMINI_MODEL,
        "gemini_configured": GEMINI_TOKEN is not None,
        "telegram_configured": telegram_bot is not None
    }

# Events
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

# Server execution
if __name__ == "__main__":
    print("Starting server with Google Gemini API")
    print(f"Model: {GEMINI_MODEL}")
    uvicorn.run("main:app", host="localhost", port=8000, reload=True)