import os
import json
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiofiles

# File paths for persistent data storage
FAMILY_MESSAGES_FILE = "family_messages.json"
AUTHORIZED_USERS_FILE = "authorized_users.json"

# Global variable to manage device connections
device_manager = None

def set_device_manager(manager):
    """Configure the device_manager from main.py to enable device connectivity"""
    global device_manager
    device_manager = manager
    print(f"✅ device_manager configured in telegram_bot")


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

        # Load and display registered devices when authorizing new users
        if device_manager:
            await device_manager.load_connections()
            print(f"📱 {len(device_manager.connections)} dispositivos registrados")
        else:
            print("⚠️ device_manager no configurado correctamente")

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
        
        # Debug: Print available device codes for troubleshooting
        device_code = context.args[0]
        print(f"🔍 Buscando código: {device_code}")
        print(f"🔍 Dispositivos disponibles: {list(device_manager.connections.keys())}")
        print(f"🔍 Códigos disponibles: {[info.get('device_code') for info in device_manager.connections.values()]}")

        target_device_id = None

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
            
            # Search for device matching the provided code
            target_device_id = None
            for device_id, info in device_manager.connections.items():
                if info.get("device_code") == device_code:
                    target_device_id = device_id
                    break
            
            # Handle case where device code is not found or device is offline
            if not target_device_id:
                await update.message.reply_text(
                    "❌ *Código no encontrado*\n\n"
                    "Verifica que el código sea correcto y que la aplicación esté abierta en el dispositivo.",
                    parse_mode="Markdown"
                )
                return
            
            # Create pending connection request object with unique request ID
            request_id = f"req_{chat_id}_{int(datetime.now().timestamp())}"
            
            # Initialize pending_requests dict if it doesn't exist
            if not hasattr(device_manager, 'pending_requests'):
                device_manager.pending_requests = {}
            
            # Store connection request with user and device information
            device_manager.pending_requests[request_id] = {
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
                del device_manager.pending_requests[request_id]
            
        except Exception as e:
            print(f"Error en comando connect: {e}")
            import traceback
            traceback.print_exc()
            await update.message.reply_text("❌ Error en la conexión.")

    async def notify_device_connection_request(self, device_id, request_id, user_info):
        """Send connection request notification to device via WebSocket"""
        # Initialize active_websockets dict if it doesn't exist
        if not hasattr(device_manager, 'active_websockets'):
            device_manager.active_websockets = {}
        
        # Retrieve WebSocket connection for the target device
        websocket = device_manager.active_websockets.get(device_id)
        
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
        # Validate that pending_requests dict exists
        if not hasattr(device_manager, 'pending_requests'):
            return False
        
        # Retrieve the pending request
        request = device_manager.pending_requests.get(request_id)
        
        if not request:
            print(f"⚠️ Solicitud {request_id} no encontrada")
            return False
        
        # Extract request details
        chat_id = request['chat_id']
        user_name = request['user_name']
        device_id = request['device_id']
        device_code = request['device_code']
        
        if approved:
            # Disconnect existing device connection for this chat if one exists
            current_device = await device_manager.get_device_for_chat(chat_id)
            if current_device:
                await device_manager.disconnect_device(current_device)
            
            # Establish new device connection
            await device_manager.connect_device(device_id, device_code, chat_id)
            
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
        del device_manager.pending_requests[request_id]
        request['status'] = 'approved' if approved else 'rejected'
        
        return True

    async def handle_disconnect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /disconnect command - terminate device connection for this chat"""
        try:
            chat_id = update.effective_chat.id
            # Retrieve device currently connected to this chat
            device_id = await device_manager.get_device_for_chat(chat_id)
            
            if device_id:
                # Disconnect the device
                await device_manager.disconnect_device(device_id)
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
            # Retrieve connected device for this chat
            device_id = await device_manager.get_device_for_chat(chat_id)
            
            if device_id:
                # Get device information and calculate connection duration
                device_info = device_manager.connections.get(device_id, {})
                connected_time = datetime.fromisoformat(device_info.get('connected_at', datetime.now().isoformat()))
                time_ago = datetime.now() - connected_time
                hours = int(time_ago.total_seconds() // 3600)
                minutes = int((time_ago.total_seconds() % 3600) // 60)
                
                # Display connection status with details
                await update.message.reply_text(
                    f"📱 *Estado de Conexión*\n\n"
                    f"• Conectado al dispositivo: `{device_info.get('device_code', 'N/A')}`\n"
                    f"• Conectado desde: {connected_time.strftime('%d/%m/%Y %H:%M')}\n"
                    f"• Tiempo conectado: {hours}h {minutes}m\n\n"
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
        
        # Verify user has an active device connection
        device_id = await device_manager.get_device_for_chat(chat_id)
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
                f"📱 A: Dispositivo `{device_manager.connections[device_id].get('device_code', 'N/A')}`\n"
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

    async def start_bot(self):
        """Initialize and start the Telegram bot with all command and message handlers"""
        if not self.token:
            print("❌ Token de Telegram no configurado")
            return        
        
        try:
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
                # Start polling for incoming messages (preferred method)
                self._polling_task = asyncio.create_task(self.application.updater.start_polling())
            except Exception as e:
                print("⚠️ start_polling() falló, intentando fallback run_polling():", e)
                # Fallback to alternative polling method if start_polling fails
                self._polling_task = asyncio.create_task(self.application.run_polling(close_loop=False, stop_signals=None))

            # Display startup information
            users = await self.load_authorized_users()
            print("✅ Bot de Telegram iniciado correctamente")
            print(f"🔗 Sistema de conexión por código activado")
            if users:
                print(f"🔐 {len(users)} usuarios autorizados históricamente")
            else:
                print("🔐 Sin usuarios autorizados históricamente")

        except Exception as e:
            print(f"❌ Error iniciando bot de Telegram: {e}")
            try:
                # Attempt cleanup if initialization fails
                if self.application:
                    await self.application.stop()
                    await self.application.shutdown()
            except Exception as e2:
                print("⚠️ Error intentando limpiar la aplicación tras fallo:", e2)

    async def stop_bot(self):
        """Gracefully stop the bot and clean up resources without closing global event loop"""
        try:
            # Stop polling task if it exists
            if hasattr(self, "_polling_task") and self._polling_task:
                try:
                    # Stop the updater from polling Telegram servers
                    if self.application and getattr(self.application, "updater", None):
                        try:
                            await self.application.updater.stop_polling()
                        except Exception:
                            pass

                    # Cancel the polling task if it's still running
                    if not self._polling_task.done():
                        self._polling_task.cancel()
                        try:
                            await self._polling_task
                        except asyncio.CancelledError:
                            pass
                except Exception as e:
                    print("⚠️ Error deteniendo tarea de polling:", e)

            # Shutdown the application gracefully
            if self.application:
                try:
                    await self.application.stop()
                except Exception as e:
                    print("⚠️ Error en application.stop():", e)
                try:
                    await self.application.shutdown()
                except Exception as e:
                    print("⚠️ Error en application.shutdown():", e)

            print("Bot de Telegram detenido")
        except Exception as e:
            print("Error en stop_bot:", e)