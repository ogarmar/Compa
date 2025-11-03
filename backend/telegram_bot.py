import os
import json
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiofiles
try:
    from .main import link_chat_to_device, get_device_from_chat_db
except ImportError:
    from backend.main import link_chat_to_device, get_device_from_chat_db

# File paths for persistent data storage
FAMILY_MESSAGES_FILE = "family_messages.json"
AUTHORIZED_USERS_FILE = "authorized_users.json"

# These will act as pointers to main.py's global dictionaries
ACTIVE_WEBSOCKETS = {}
PENDING_REQUESTS = {}

def set_shared_state(active_ws: dict, pending_req: dict):
    """Receives global dictionaries from main.py"""
    global ACTIVE_WEBSOCKETS, PENDING_REQUESTS
    ACTIVE_WEBSOCKETS = active_ws
    PENDING_REQUESTS = pending_req
    print("✅ Global state received in telegram_bot")


# Main bot class handling all Telegram messaging and device connection logic
class FamilyMessagesBot:
    def __init__(self, token):
        """Initialize bot with Telegram API token"""
        self.token = token
        self.application = None
    
    async def load_authorized_users(self):
        """Load authorized users from JSON file; create file from env vars if it doesn't exist"""
        if not os.path.exists(AUTHORIZED_USERS_FILE):
            # Parse initial IDs from environment variable TELEGRAM_CHAT_IDS (comma-separated)
            ids_str = os.getenv("TELEGRAM_CHAT_IDS", "")
            initial_ids = []
            if ids_str:
                initial_ids = [int(id.strip()) for id in ids_str.split(",") if id.strip()]
            
            await self.save_authorized_users(initial_ids)
            return initial_ids
        
        try:
            async with aiofiles.open(AUTHORIZED_USERS_FILE, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                return data.get("authorized_chat_ids", [])
        except Exception as e:
            print(f"Error cargando usuarios autorizados: {e}")
            return []
    
    async def save_authorized_users(self, chat_ids):
        """Save authorized chat IDs to JSON file with timestamp"""
        try:
            async with aiofiles.open(AUTHORIZED_USERS_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps({
                    "authorized_chat_ids": chat_ids,
                    "last_updated": datetime.now().isoformat()
                }, indent=2, ensure_ascii=False))
            return True
        except Exception as e:
            print(f"Error guardando usuarios autorizados: {e}")
            return False
    
    async def add_authorized_user(self, chat_id):
        """Add a new authorized user and load active device connections"""
        users = await self.load_authorized_users()

        # Note: We no longer need to display device information here since it's in the DB
        print("✅ Bot de Telegram iniciado correctamente")
        print("🔗 Sistema de conexión por código activado")

        print("✅ Bot de Telegram iniciado correctamente")

        # Append new chat_id if not already authorized
        if chat_id not in users:
            users.append(chat_id)
            await self.save_authorized_users(users)
            print(f"✅ Usuario {chat_id} autorizado correctamente")
            return True
        print(f"ℹ️ Usuario {chat_id} ya estaba autorizado")
        return False
    
    async def remove_authorized_user(self, chat_id):
        """Remove an authorized user from the whitelist"""
        users = await self.load_authorized_users()
        if chat_id in users:
            users.remove(chat_id)
            await self.save_authorized_users(users)
            print(f"🚫 Usuario {chat_id} revocado correctamente")
            return True
        return False
    
    async def is_authorized(self, chat_id):
        """Check if a chat_id has permission to use the bot"""
        users = await self.load_authorized_users()
        if not users:
            print(f"⚠️ Lista de autorizados vacía - acceso denegado por defecto")
            return False
        return chat_id in users
    
    async def load_messages(self):
        """Load all stored family messages from JSON file"""
        if not os.path.exists(FAMILY_MESSAGES_FILE):
            return []
        
        try:
            async with aiofiles.open(FAMILY_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            print(f"Error cargando mensajes familiares: {e}")
            return []
    
    async def save_message(self, sender_name, message_text, chat_id):
        """Save a new family message with full timestamp and metadata"""
        messages = await self.load_messages()
        
        now = datetime.now()
        
        # Create message object with ID, sender, content, and timestamp information
        new_message = {
            "id": len(messages) + 1,
            "sender_name": sender_name,
            "message": message_text,
            "chat_id": chat_id,
            "timestamp": now.isoformat(),
            "date": now.strftime("%d/%m/%Y"), 
            "time": now.strftime("%H:%M"),
            "day_name": now.strftime("%A"),  
            "read": False
        }
        
        messages.append(new_message)
        
        try:
            async with aiofiles.open(FAMILY_MESSAGES_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(messages, indent=2, ensure_ascii=False))
            return new_message
        except Exception as e:
            print(f"Error guardando mensaje familiar: {e}")
            return None
    
    async def get_messages_by_date(self, date_str):
        """Retrieve all messages from a specific date (format: dd/mm/yyyy)"""
        messages = await self.load_messages()
        filtered = [msg for msg in messages if msg.get("date") == date_str]
        return filtered
    
    async def get_messages_today(self):
        """Retrieve all messages from the current day"""
        today = datetime.now().strftime("%d/%m/%Y")
        return await self.get_messages_by_date(today)
    
    async def get_unread_messages(self):
        """Get all unread messages sorted chronologically by timestamp"""
        messages = await self.load_messages()
        unread = [msg for msg in messages if not msg.get("read", False)]
        unread.sort(key=lambda x: x.get("timestamp", ""), reverse=False)
        print(f"📬 get_unread_messages() devolvió {len(unread)} mensajes")
        return unread
    
    async def mark_as_read(self, message_id):
        """Mark a specific message as read and update the JSON file"""
        messages = await self.load_messages()
        
        # Find and update the message's read status
        for msg in messages:
            if msg["id"] == message_id:
                msg["read"] = True
                break
        
        try:
            async with aiofiles.open(FAMILY_MESSAGES_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(messages, indent=2, ensure_ascii=False))
            return True
        except Exception as e:
            print(f"Error marcando mensaje como leído: {e}")
            return False


    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - show welcome message and available commands"""
        user_name = update.effective_user.first_name
        await update.message.reply_text(
            f"👋 ¡Hola {user_name}!\n\n"
            "Soy el bot de la aplicación *Compa*.\n\n"
            "📋 *Comandos disponibles:*\n"
            "• `/connect <código>` - Conectarte a un dispositivo\n"
            "• `/disconnect` - Desconectarte\n"
            "• `/status` - Ver estado de conexión\n"
            "• `/mismensajes` - Ver tus mensajes enviados\n"
            "• `/ayuda` - Mostrar ayuda\n\n"
            "Para enviar mensajes, primero conéctate a un dispositivo usando el código de 6 dígitos que aparece en la aplicación.",
            parse_mode="Markdown"
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ayuda command - display detailed help information"""
        help_text = """🆘 **Ayuda - Bot de Mensajes Compa**

📋 *Comandos disponibles:*
• `/start` - Iniciar el bot
• `/connect <código>` - Conectarte a un dispositivo específico
• `/disconnect` - Desconectarte del dispositivo actual  
• `/status` - Ver tu estado de conexión
• `/mismensajes` - Ver tus mensajes enviados
• `/ayuda` - Esta ayuda

💡 *Para enviar mensajes:*
1. Pide el código de 6 dígitos de la aplicación Compa
2. Usa `/connect CODIGO` para conectarte
3. Envía tu mensaje normalmente
4. Usa `/disconnect` cuando termines

El mensaje llegará directamente al dispositivo conectado."""
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def my_messages_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mismensajes command - display user's sent messages (last 10)"""
        chat_id = update.effective_chat.id
        
        # Verify user is authorized before showing their messages
        if not await self.is_authorized(chat_id):
            await update.message.reply_text("⚠️ Necesitas estar autorizado para ver tus mensajes.")
            return
        
        messages = await self.load_messages()
        # Filter messages sent by this specific user
        user_messages = [msg for msg in messages if msg.get("chat_id") == chat_id]
        
        if not user_messages:
            await update.message.reply_text("No has enviado ningún mensaje todavía.")
            return
        
        # Build response showing last 10 messages with read status and preview
        response = "📬 **Tus mensajes enviados:**\n\n"
        for msg in user_messages[-10:]: 
            status = "✅ Leído" if msg.get("read") else "📨 Pendiente"
            date = datetime.fromisoformat(msg["timestamp"]).strftime("%d/%m/%Y %H:%M")
            preview = msg['message'][:50] + "..." if len(msg['message']) > 50 else msg['message']
            response += f"{status} - {date}\n_{preview}_\n\n"
        
        # Note: We no longer need to print device information since it's in the DB

        await update.message.reply_text(response, parse_mode="Markdown")
    
    async def handle_connect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /connect command - initiate device connection request requiring device approval"""
        try:
            chat_id = update.effective_chat.id
            user_name = update.effective_user.first_name
            user_full_name = update.effective_user.full_name
            username = update.effective_user.username or "sin_usuario"
            
            # Validate that a device code was provided
            if len(context.args) == 0:
                await update.message.reply_text(
                    "🔗 *Conectar a Dispositivo*\n\n"
                    "Uso: `/connect <código>`\n\n"
                    "Pide el código de 6 dígitos que aparece en la aplicación Compa del dispositivo al que quieres conectarte.",
                    parse_mode="Markdown"
                )
                return
            
            device_code = context.args[0]
            
            # First try to link the chat to the device
            success = await link_chat_to_device(device_code, str(chat_id))
            
            # Handle case where device code is not found or device is offline
            if not success:
                await update.message.reply_text(
                    "❌ *Código no encontrado*\n\n"
                    "Verifica que el código sea correcto y que la aplicación esté abierta en el dispositivo.",
                    parse_mode="Markdown"
                )
                return
            
            # Get device ID after successful link
            target_device_id = await get_device_from_chat_db(str(chat_id))
            
            # Create pending connection request object with unique request ID
            request_id = f"req_{chat_id}_{int(datetime.now().timestamp())}"
            
            # Store connection request with user and device information
            PENDING_REQUESTS[request_id] = {
                "chat_id": chat_id,
                "user_name": user_name,
                "user_full_name": user_full_name,
                "username": username,
                "device_id": target_device_id,
                "device_code": device_code,
                "timestamp": datetime.now().isoformat(),
                "status": "pending"
            }
            
            print(f"📨 Solicitud de conexión creada: {request_id}")
            print(f"   Usuario: {user_full_name} (@{username}) - Chat: {chat_id}")
            print(f"   Dispositivo: {target_device_id}")
            
            # Send connection request notification to device via WebSocket
            notification_sent = await self.notify_device_connection_request(
                target_device_id,
                request_id,
                {
                    "chat_id": chat_id,
                    "user_name": user_name,
                    "user_full_name": user_full_name,
                    "username": username
                }
            )
            
            if notification_sent:
                # Notify user that request was sent and is awaiting approval
                await update.message.reply_text(
                    f"⏳ *Solicitud enviada*\n\n"
                    f"Hola {user_name}, tu solicitud de conexión ha sido enviada al dispositivo.\n\n"
                    f"Esperando aprobación del usuario...",
                    parse_mode="Markdown"
                )
            else:
                # Device is offline or unreachable
                await update.message.reply_text(
                    "⚠️ *Dispositivo no disponible*\n\n"
                    "El dispositivo está desconectado. Pide al usuario que abra la aplicación e intenta de nuevo.",
                    parse_mode="Markdown"
                )
                # Clean up failed request from pending list
                PENDING_REQUESTS.pop(request_id,  None)
            
        except Exception as e:
            print(f"Error en comando connect: {e}")
            import traceback
            traceback.print_exc()
            await update.message.reply_text("❌ Error en la conexión.")

    async def notify_device_connection_request(self, device_id, request_id, user_info):
        """Send connection request notification to device via WebSocket"""
        # Retrieve WebSocket connection for the target device
        websocket = ACTIVE_WEBSOCKETS.get(device_id)
        
        if websocket:
            try:
                # Send JSON message with connection request details
                await websocket.send_text(json.dumps({
                    "type": "connection_request",
                    "request_id": request_id,
                    "user_info": user_info
                }, ensure_ascii=False))
                print(f"✅ Notificación enviada al dispositivo {device_id}")
                return True
            except Exception as e:
                print(f"❌ Error enviando notificación al dispositivo: {e}")
                return False
        else:
            print(f"❌ WebSocket no encontrado para dispositivo {device_id}")
            return False

    async def process_connection_response(self, request_id, approved, websocket):
        """Process device's approval or rejection of connection request"""
        # Retrieve the pending request
        request = PENDING_REQUESTS.get(request_id)
        
        if not request:
            print(f"⚠️ Solicitud {request_id} no encontrada")
            return False
        
        # Extract request details
        chat_id = request['chat_id']
        user_name = request['user_name']
        device_id = request['device_id']
        device_code = request['device_code']
        
        if approved:
            # Establish new device connection using database
            success = await link_chat_to_device(device_code, str(chat_id))
            
            if not success:
                print(f"❌ Error linking chat {chat_id} to device with code {device_code}")
                return False
            
            # Send approval confirmation to Telegram user
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ *¡Conexión aprobada!*\n\n"
                        f"Hola {user_name}, ya puedes enviar mensajes al dispositivo.\n"
                        f"Código: `{device_code}`",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Error enviando mensaje de aprobación: {e}")
            
            # Send approval confirmation back to device via WebSocket
            try:
                await websocket.send_text(json.dumps({
                    "type": "connection_approved",
                    "user_name": user_name,
                    "chat_id": chat_id
                }, ensure_ascii=False))
            except:
                pass
            
            print(f"✅ Conexión aprobada: Chat {chat_id} → Dispositivo {device_id}")
            
        else:
            # Send rejection notification to Telegram user
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ *Conexión rechazada*\n\n"
                        f"El usuario del dispositivo ha rechazado tu solicitud de conexión.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Error enviando mensaje de rechazo: {e}")
            
            print(f"❌ Conexión rechazada: Chat {chat_id} → Dispositivo {device_id}")
        
        # Update and remove request from pending list
        del PENDING_REQUESTS[request_id]
        request['status'] = 'approved' if approved else 'rejected'
        
        return True

    async def handle_disconnect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /disconnect command - terminate device connection for this chat"""
        try:
            chat_id = update.effective_chat.id
            # Retrieve device currently connected to this chat from database
            device_id = await get_device_from_chat_db(str(chat_id))
            
            if device_id:
                # We don't need to explicitly disconnect since we'll just 
                # overwrite the chat_id when connecting to a new device
                await update.message.reply_text(
                    "✅ *Desconectado correctamente*\n\n"
                    "Ya no enviarás mensajes a ningún dispositivo.",
                    parse_mode="Markdown"
                )
                print(f"🔗 Chat {chat_id} desconectado del dispositivo {device_id}")
            else:
                # User was not connected to any device
                await update.message.reply_text(
                    "ℹ️ No estabas conectado a ningún dispositivo.",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            print(f"Error en comando disconnect: {e}")
            await update.message.reply_text("❌ Error en la desconexión.")

    async def handle_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - show current connection status and details"""
        try:
            chat_id = update.effective_chat.id
            # Retrieve connected device for this chat from database
            device_id = await get_device_from_chat_db(str(chat_id))
            
            if device_id:
                # Show simplified status since we don't store connection time in DB
                await update.message.reply_text(
                    f"📱 *Estado de Conexión*\n\n"
                    f"• Dispositivo ID: `{device_id}`\n\n"
                    f"Usa `/disconnect` para desconectarte.",
                    parse_mode="Markdown"
                )
            else:
                # User has no active device connection
                await update.message.reply_text(
                    "🔌 *Estado de Conexión*\n\n"
                    "No estás conectado a ningún dispositivo.\n"
                    "Usa `/connect <código>` para conectarte.",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            print(f"Error en comando status: {e}")
            await update.message.reply_text("❌ Error obteniendo estado.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages - save and forward to connected device"""
        chat_id = update.effective_chat.id
        user_name = update.effective_user.first_name
        message_text = update.message.text
        
        # Verify user has an active device connection using database
        device_id = await get_device_from_chat_db(str(chat_id))
        if not device_id:
            await update.message.reply_text(
                "❌ *No estás conectado a ningún dispositivo*\n\n"
                "Para enviar mensajes, primero conéctate a un dispositivo usando:\n"
                "`/connect <código>`\n\n"
                "Pide el código de 6 dígitos que aparece en la aplicación Compa.",
                parse_mode="Markdown"
            )
            print(f"🚫 Usuario {user_name} (ID: {chat_id}) intentó enviar mensaje sin conexión")
            return
        
        # Save message to persistent storage
        saved = await self.save_message(user_name, message_text, chat_id)
        
        if saved:
            date_formatted = saved['date']
            tifme_formatted = saved['time']
            # Send confirmation to user with message details
            await update.message.reply_text(
                f"✅ *Mensaje enviado correctamente*\n\n"
                f"👤 De: {user_name}\n"
                f"📱 A: Dispositivo `{device_id}`\n"
                f"📅 Fecha: {date_formatted}\n"
                f"🕐 Hora: {tifme_formatted}\n\n"
                f"💬 *Vista previa:*\n{message_text[:100]}{'...' if len(message_text) > 100 else ''}",
                parse_mode="Markdown"
            )
            print(f"📨 Mensaje de {user_name} (ID: {chat_id}) enviado al dispositivo {device_id}: {message_text[:50]}...")
        else:
            # Message save failed
            await update.message.reply_text(
                "❌ Error al enviar el mensaje. Inténtalo de nuevo."
            )

    async def start_bot(self):  # ✅ CORRECTO: FUERA de handle_message
        """Initialize and start the Telegram bot with all command and message handlers"""
        if not self.token:
            print("❌ Token de Telegram no configurado")
            return        
        
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                print(f"🔄 Intentando iniciar bot de Telegram (intento {attempt + 1}/{max_retries})")
                
                # Create bot application with provided token
                self.application = Application.builder().token(self.token).build()
                
                # Register command handlers for all bot commands
                self.application.add_handler(CommandHandler("start", self.start_command))
                self.application.add_handler(CommandHandler("ayuda", self.help_command))
                self.application.add_handler(CommandHandler("mismensajes", self.my_messages_command))
                self.application.add_handler(CommandHandler("connect", self.handle_connect_command))
                self.application.add_handler(CommandHandler("disconnect", self.handle_disconnect_command))
                self.application.add_handler(CommandHandler("status", self.handle_status_command))
                # Register handler for all non-command text messages
                self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
                
                # Initialize and start the bot application
                await self.application.initialize()
                await self.application.start()

                try:
                    # Start polling for incoming messages with connection timeout
                    self._polling_task = asyncio.create_task(self.application.updater.start_polling())
                except Exception as e:
                    print("⚠️ start_polling() falló, intentando fallback run_polling():", e)
                    # Fallback to alternative polling method if start_polling fails
                    self._polling_task = asyncio.create_task(self.application.run_polling(
                        close_loop=False, 
                        stop_signals=None,
                        poll_interval=2.0,
                        timeout=10
                    ))

                users = await self.load_authorized_users()
                print("✅ Bot de Telegram iniciado correctamente")
                print(f"🔗 Sistema de conexión por código activado")
                if users:
                    print(f"🔐 {len(users)} usuarios autorizados históricamente")
                else:
                    print("🔐 Sin usuarios autorizados históricamente")
                
                break

            except Exception as e:
                print(f"❌ Error iniciando bot de Telegram (intento {attempt + 1}): {e}")
                
                try:
                    if self.application:
                        await self.application.stop()
                        await self.application.shutdown()
                        self.application = None
                except Exception as e2:
                    print("⚠️ Error limpiando aplicación:", e2)
                
                if attempt < max_retries - 1:
                    print(f"⏳ Reintentando en {retry_delay} segundos...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print("❌ Todos los intentos fallaron. Bot de Telegram no iniciado.")
                    print("ℹ️ La aplicación continuará sin funcionalidad de Telegram")

    async def stop_bot(self):  # ✅ CORRECTO: FUERA de handle_message
        """Gracefully stop the bot and clean up resources"""
        print("🛑 Iniciando parada del bot de Telegram...")
        
        try:
            # 1. First stop the updater/polling
            if hasattr(self, "_polling_task") and self._polling_task:
                try:
                    print("⏹️ Deteniendo polling...")
                    # Stop the updater properly
                    if self.application and hasattr(self.application, 'updater') and self.application.updater:
                        try:
                            self.application.updater.running = False
                            if hasattr(self.application.updater, 'stop_polling'):
                                await self.application.updater.stop_polling()
                            elif hasattr(self.application.updater, 'stop'):
                                await self.application.updater.stop()
                        except Exception as e:
                            print("⚠️ Error deteniendo updater:", e)
                    
                    # Cancel the polling task
                    if not self._polling_task.done():
                        self._polling_task.cancel()
                        try:
                            await asyncio.wait_for(self._polling_task, timeout=5.0)
                        except (asyncio.CancelledError, asyncio.TimeoutError):
                            pass
                except Exception as e:
                    print("⚠️ Error en proceso de detención de polling:", e)
            
            # 2. Stop the application
            if self.application:
                try:
                    print("⏹️ Deteniendo aplicación...")
                    await self.application.stop()
                except Exception as e:
                    print("⚠️ Error en application.stop():", e)
                
                try:
                    print("⏹️ Cerrando aplicación...")
                    await self.application.shutdown()
                except Exception as e:
                    print("⚠️ Error en application.shutdown():", e)
            
            # 3. Additional cleanup
            if hasattr(self, "_polling_task") and self._polling_task:
                try:
                    if not self._polling_task.done():
                        self._polling_task.cancel()
                except:
                    pass
            
            print("✅ Bot de Telegram detenido correctamente")
            
        except Exception as e:
            print("❌ Error crítico en stop_bot:", e)