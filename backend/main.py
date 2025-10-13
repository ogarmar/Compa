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

# Load environment variables
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

# Configure the Gemini model
GEMINI_MODEL = "gemini-2.5-flash-lite"  # DO NOT CHANGE THIS MODEL

# Constants for memory and conversation files
MEMORY_FILE = "user_memory.json"
CONVERSATION_FILE = "conversation_history.json"

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

class MemoryManager:
    def __init__(self):
        self.memory_file = MEMORY_FILE
        self.conversation_file = CONVERSATION_FILE
        
    async def load_memory(self):
        # Tries to load existing user memory or creates a new one
        try:
            async with aiofiles.open(self.memory_file, 'r') as f:
                content = await f.read()
                return json.loads(content)
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
        
    async def save_memory(self, memory_data):
        # Writes the memory data to the JSON file
        async with aiofiles.open(self.memory_file, 'w') as f:
            await f.write(json.dumps(memory_data, indent=2, ensure_ascii=False))
        
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
        # Saves the user message and assistant's response to history
        try:
            async with aiofiles.open(self.conversation_file, 'r') as f:
                conversations = json.loads(await f.read())
        except FileNotFoundError:
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
        async with aiofiles.open(self.conversation_file, 'w') as f:
            await f.write(json.dumps(conversations, indent=2, ensure_ascii=False))

memory_manager = MemoryManager()

# WebSocket endpoint for real-time conversation
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        user_memory = await memory_manager.load_memory()
        await websocket.send_text("Bienvenido querido usuario. Soy Acompaña, tu asistente personal. ¿En qué puedo ayudarte hoy?")
        
        while True:
            data = await websocket.receive_text()
            user_message = data.strip()
            if not user_message:
                continue
            
            # Check for relevant memories
            relevant_memories = await memory_manager.get_relevant_memories(user_message)
            memory_context = ""
            if relevant_memories:
                memory_context = " | ".join([mem["content"] for mem in relevant_memories])
                print(f"DEBUG: Found memories: {len(relevant_memories)}")
                print(f"DEBUG: Memory context: {memory_context}")
            
            # Detect and save new important memories
            important_keywords = ["recuerdo cuando", "me acuerdo de", "mi hijo", "mi hija", "mi esposo", "mi esposa", "cuando era joven", "mi nieto", "mi nieta", "qué ilusión", "me encantaba"]
            memory_saved = False
            
            if any(keyword in user_message.lower() for keyword in important_keywords):
                memory_saved = True
                new_memory = await memory_manager.add_important_memory(user_message, "personal")
                print(f"DEBUG: Memory saved: {new_memory['id']}")
            
            # Call Gemini API
            try:
                if not GEMINI_TOKEN:
                    ai_response = "Error: GEMINI_TOKEN is not configured."
                else:
                    model = genai.GenerativeModel(GEMINI_MODEL)
                    
                    generation_config = genai.types.GenerationConfig(
                        max_output_tokens=250,
                        temperature=0.4,
                    )
                    
                    # Determine if it's a memory-related question
                    is_memory_question = any(keyword in user_message.lower() for keyword in 
                                             ["recuerdo", "recuerdos", "acuerdo", "memoria", "pasado", "cuando", "antes"])
                    
                    # Build the prompt based on context and question type
                    if is_memory_question and memory_context:
                        # For memory questions with context
                        full_prompt = f"""
Eres "Acompaña", un asistente especializado en Alzheimer. Responde con frases cortas y tono afectuoso.

CRITICAL INFORMATION - THESE ARE THE USER'S REAL MEMORIES:
{memory_context}

The user asks: "{user_message}"

RESPOND by specifically mentioning the memories above. If they don't fit perfectly, adapt your response kindly.

Your response (1-2 sentences, mentioning the memories):
"""
                    elif is_memory_question and not memory_context:
                        # For memory questions without context
                        full_prompt = f"""
Eres "Acompaña", un asistente especializado en Alzheimer.

El usuario pregunta: "{user_message}"

No tengo recuerdos específicos guardados sobre este tema. Responde con empatía.

Tu respuesta (1-2 frases, ofreciendo ayuda):
"""
                    else:
                        # For normal conversation
                        full_prompt = f"""
Eres "Acompaña", un asistente especializado en Alzheimer.

{f"USER CONTEXT: {memory_context}" if memory_context else ""}

Usuario: {user_message}

Tu respuesta (1-2 frases, tono afectuoso):
"""
                    
                    print(f"DEBUG: Prompt sent: {full_prompt}")
                    
                    # Send prompt to Gemini
                    response = model.generate_content(full_prompt)
                    ai_response = response.text.strip()
                    
                    print(f"DEBUG: Raw response: {ai_response}")
                    
                    # Logic to ensure memory mention (if relevant)
                    if is_memory_question and memory_context:
                        response_uses_memories = any(
                            any(word in mem["content"].lower() for word in ai_response.lower().split()[:10])
                            for mem in relevant_memories
                        )
                        
                        if not response_uses_memories:
                            print("DEBUG: Forcing memory mention...")
                            # Create a response that DOES mention the memories
                            memory_summary = ". ".join([mem["content"] for mem in relevant_memories[:2]])
                            ai_response = f"Recuerdo que me contaste: {memory_summary}. ¡Son momentos muy especiales!"
                        
                    # Truncate response to 1-2 sentences
                    sentences = [s.strip() for s in ai_response.split('.') if s.strip()]
                    if len(sentences) > 2:
                        ai_response = '. '.join(sentences[:2]) + '.'
                    
                    # Add confirmation message if a memory was saved
                    if memory_saved and "recuerdo" not in ai_response.lower():
                        ai_response += " ¡Qué bonito recuerdo! Lo guardaré en tu cofre especial."
                        
            except Exception as e:
                print("Error Gemini API:", e)
                traceback.print_exc()
                
                # Intelligent fallback response
                if memory_saved:
                    memory_count = len((await memory_manager.load_memory())["important_memories"])
                    ai_response = f"¡Qué bonito recuerdo! Lo he guardado en tu cofre. Ya tienes {memory_count} recuerdos especiales conmigo."
                elif memory_context and is_memory_question:
                    # Manual response with found memories
                    memory_list = "\n".join([f"- {mem['content']}" for mem in relevant_memories])
                    ai_response = f"Tus recuerdos especiales:\n{memory_list}\n\n¿Te gustaría que hablemos más de alguno?"
                else:
                    ai_response = "Estoy aquí para acompañarte. ¿Podrías contarme más sobre lo que necesitas?"

            # Save and send the final response
            await memory_manager.save_conversation(user_message, ai_response)
            await websocket.send_text(ai_response)
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print("Error in WebSocket:", e)
        traceback.print_exc()
        try:
            await websocket.send_text("Lo siento, ha ocurrido un error. Por favor inténtalo de nuevo.")
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
    # Serves the main index.html file
    index_file = os.path.join(frontend_path, 'index.html')
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Index not found."}

@app.get("/health")
async def health_check():
    # Simple health check endpoint
    return {
        "status": "running",
        "ai_provider": "google_gemini",
        "model": GEMINI_MODEL,
        "gemini_configured": GEMINI_TOKEN is not None
    }

# Server execution
if __name__ == "__main__":
    print("Starting server with Google Gemini API")
    print(f"Model: {GEMINI_MODEL}")
    uvicorn.run("main:app", host="localhost", port=8000, reload=True)