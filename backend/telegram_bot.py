import os
import json
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiofiles

FAMILY_MESSAGES_FILE = "family_messages.json"
AUTHORIZED_USERS_FILE = "authorized_users.json"

device_manager = None

def set_device_manager(manager):
    """Configura el device_manager desde main.py"""
    global device_manager
    device_manager = manager
    print(f"✅ device_manager configurado en telegram_bot")





class FamilyMessagesBot:
    def __init__(self, token):
        self.token = token
        self.application = None
    
    async def load_authorized_users(self):
        """Carga usuarios autorizados desde archivo JSON"""
        if not os.path.exists(AUTHORIZED_USERS_FILE):
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
        """Guarda usuarios autorizados"""
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
        """Agrega un usuario autorizado"""
        users = await self.load_authorized_users()

        if device_manager:
            await device_manager.load_connections()
            print(f"📱 {len(device_manager.connections)} dispositivos registrados")
        else:
            print("⚠️ device_manager no configurado correctamente")

        print("✅ Bot de Telegram iniciado correctamente")

        if chat_id not in users:
            users.append(chat_id)
            await self.save_authorized_users(users)
            print(f"✅ Usuario {chat_id} autorizado correctamente")
            return True
        print(f"ℹ️ Usuario {chat_id} ya estaba autorizado")
        return False
    
    async def remove_authorized_user(self, chat_id):
        """Elimina un usuario autorizado"""
        users = await self.load_authorized_users()
        if chat_id in users:
            users.remove(chat_id)
            await self.save_authorized_users(users)
            print(f"🚫 Usuario {chat_id} revocado correctamente")
            return True
        return False
    
    async def is_authorized(self, chat_id):
        """Verifica si un usuario está autorizado"""
        users = await self.load_authorized_users()
        if not users:
            print(f"⚠️ Lista de autorizados vacía - acceso denegado por defecto")
            return False
        return chat_id in users
    
    async def load_messages(self):
        """Carga mensajes existentes"""
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
        """Guarda un nuevo mensaje familiar con fecha completa"""
        messages = await self.load_messages()
        
        now = datetime.now()
        
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
        """Obtiene mensajes de una fecha específica (formato: dd/mm/yyyy)"""
        messages = await self.load_messages()
        filtered = [msg for msg in messages if msg.get("date") == date_str]
        return filtered
    
    async def get_messages_today(self):
        """Obtiene mensajes del día de hoy"""
        today = datetime.now().strftime("%d/%m/%Y")
        return await self.get_messages_by_date(today)
    
    async def get_unread_messages(self):
        """Obtiene mensajes no leídos ordenados por fecha"""
        messages = await self.load_messages()
        unread = [msg for msg in messages if not msg.get("read", False)]
        unread.sort(key=lambda x: x.get("timestamp", ""), reverse=False)
        print(f"📬 get_unread_messages() devolvió {len(unread)} mensajes")
        return unread
    
    async def mark_as_read(self, message_id):
        """Marca un mensaje como leído"""
        messages = await self.load_messages()
        
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
        """Comando /start del bot"""
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
        """Comando /ayuda"""
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
        """Comando /mismensajes - ver mensajes del usuario"""
        chat_id = update.effective_chat.id
        
        if not await self.is_authorized(chat_id):
            await update.message.reply_text("⚠️ Necesitas estar autorizado para ver tus mensajes.")
            return
        
        messages = await self.load_messages()
        user_messages = [msg for msg in messages if msg.get("chat_id") == chat_id]
        
        if not user_messages:
            await update.message.reply_text("No has enviado ningún mensaje todavía.")
            return
        
        response = "📬 **Tus mensajes enviados:**\n\n"
        for msg in user_messages[-10:]: 
            status = "✅ Leído" if msg.get("read") else "📨 Pendiente"
            date = datetime.fromisoformat(msg["timestamp"]).strftime("%d/%m/%Y %H:%M")
            preview = msg['message'][:50] + "..." if len(msg['message']) > 50 else msg['message']
            response += f"{status} - {date}\n_{preview}_\n\n"
        
        device_code = context.args[0]
        print(f"🔍 Buscando código: {device_code}")
        print(f"🔍 Dispositivos disponibles: {list(device_manager.connections.keys())}")
        print(f"🔍 Códigos disponibles: {[info.get('device_code') for info in device_manager.connections.values()]}")

        target_device_id = None

        await update.message.reply_text(response, parse_mode="Markdown")
    
    async def handle_connect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Conectar un chat de Telegram a un dispositivo específico - CON APROBACIÓN"""
        try:
            chat_id = update.effective_chat.id
            user_name = update.effective_user.first_name
            user_full_name = update.effective_user.full_name
            username = update.effective_user.username or "sin_usuario"
            
            if len(context.args) == 0:
                await update.message.reply_text(
                    "🔗 *Conectar a Dispositivo*\n\n"
                    "Uso: `/connect <código>`\n\n"
                    "Pide el código de 6 dígitos que aparece en la aplicación Compa del dispositivo al que quieres conectarte.",
                    parse_mode="Markdown"
                )
                return
            
            device_code = context.args[0]
            
            # Buscar dispositivo con ese código
            target_device_id = None
            for device_id, info in device_manager.connections.items():
                if info.get("device_code") == device_code:
                    target_device_id = device_id
                    break
            
            if not target_device_id:
                await update.message.reply_text(
                    "❌ *Código no encontrado*\n\n"
                    "Verifica que el código sea correcto y que la aplicación esté abierta en el dispositivo.",
                    parse_mode="Markdown"
                )
                return
            
            # Crear solicitud de conexión pendiente
            request_id = f"req_{chat_id}_{int(datetime.now().timestamp())}"
            
            if not hasattr(device_manager, 'pending_requests'):
                device_manager.pending_requests = {}
            
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
            
            # Enviar notificación al dispositivo via WebSocket
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
                await update.message.reply_text(
                    f"⏳ *Solicitud enviada*\n\n"
                    f"Hola {user_name}, tu solicitud de conexión ha sido enviada al dispositivo.\n\n"
                    f"Esperando aprobación del usuario...",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "⚠️ *Dispositivo no disponible*\n\n"
                    "El dispositivo está desconectado. Pide al usuario que abra la aplicación e intenta de nuevo.",
                    parse_mode="Markdown"
                )
                # Limpiar solicitud pendiente
                del device_manager.pending_requests[request_id]
            
        except Exception as e:
            print(f"Error en comando connect: {e}")
            import traceback
            traceback.print_exc()
            await update.message.reply_text("❌ Error en la conexión.")

    async def notify_device_connection_request(self, device_id, request_id, user_info):
        """Notifica al dispositivo sobre una solicitud de conexión"""
        if not hasattr(device_manager, 'active_websockets'):
            device_manager.active_websockets = {}
        
        websocket = device_manager.active_websockets.get(device_id)
        
        if websocket:
            try:
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
        """Procesa la respuesta de aprobación/rechazo del dispositivo"""
        if not hasattr(device_manager, 'pending_requests'):
            return False
        
        request = device_manager.pending_requests.get(request_id)
        
        if not request:
            print(f"⚠️ Solicitud {request_id} no encontrada")
            return False
        
        chat_id = request['chat_id']
        user_name = request['user_name']
        device_id = request['device_id']
        device_code = request['device_code']
        
        if approved:
            # Desconectar dispositivo anterior si existe
            current_device = await device_manager.get_device_for_chat(chat_id)
            if current_device:
                await device_manager.disconnect_device(current_device)
            
            # Conectar
            await device_manager.connect_device(device_id, device_code, chat_id)
            
            # Notificar a Telegram
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
            
            # Notificar al websocket
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
            # Rechazar
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
        
        # Limpiar solicitud pendiente
        del device_manager.pending_requests[request_id]
        request['status'] = 'approved' if approved else 'rejected'
        
        return True

    async def handle_disconnect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Desconectar un chat de Telegram"""
        try:
            chat_id = update.effective_chat.id
            device_id = await device_manager.get_device_for_chat(chat_id)
            
            if device_id:
                await device_manager.disconnect_device(device_id)
                await update.message.reply_text(
                    "✅ *Desconectado correctamente*\n\n"
                    "Ya no enviarás mensajes a ningún dispositivo.",
                    parse_mode="Markdown"
                )
                print(f"🔗 Chat {chat_id} desconectado del dispositivo {device_id}")
            else:
                await update.message.reply_text(
                    "ℹ️ No estabas conectado a ningún dispositivo.",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            print(f"Error en comando disconnect: {e}")
            await update.message.reply_text("❌ Error en la desconexión.")

    async def handle_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mostrar estado de conexión actual"""
        try:
            chat_id = update.effective_chat.id
            device_id = await device_manager.get_device_for_chat(chat_id)
            
            if device_id:
                device_info = device_manager.connections.get(device_id, {})
                connected_time = datetime.fromisoformat(device_info.get('connected_at', datetime.now().isoformat()))
                time_ago = datetime.now() - connected_time
                hours = int(time_ago.total_seconds() // 3600)
                minutes = int((time_ago.total_seconds() % 3600) // 60)
                
                await update.message.reply_text(
                    f"📱 *Estado de Conexión*\n\n"
                    f"• Conectado al dispositivo: `{device_info.get('device_code', 'N/A')}`\n"
                    f"• Conectado desde: {connected_time.strftime('%d/%m/%Y %H:%M')}\n"
                    f"• Tiempo conectado: {hours}h {minutes}m\n\n"
                    f"Usa `/disconnect` para desconectarte.",
                    parse_mode="Markdown"
                )
            else:
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
        """Maneja mensajes de texto normales"""
        chat_id = update.effective_chat.id
        user_name = update.effective_user.first_name
        message_text = update.message.text
        
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
        
        saved = await self.save_message(user_name, message_text, chat_id)
        
        if saved:
            date_formatted = saved['date']
            tifme_formatted = saved['time']
            await update.message.reply_text(
                f"✅ *Mensaje enviado correctamente*\n\n"
                f"👤 De: {user_name}\n"
                f"📱 A: Dispositivo `{device_manager.connections[device_id].get('device_code', 'N/A')}`\n"
                f"📅 Fecha: {date_formatted}\n"
                f"🕐 Hora: {time_formatted}\n\n"
                f"💬 *Vista previa:*\n{message_text[:100]}{'...' if len(message_text) > 100 else ''}",
                parse_mode="Markdown"
            )
            print(f"📨 Mensaje de {user_name} (ID: {chat_id}) enviado al dispositivo {device_id}: {message_text[:50]}...")
        else:
            await update.message.reply_text(
                "❌ Error al enviar el mensaje. Inténtalo de nuevo."
            )

    async def start_bot(self):
        """Inicia el bot."""
        if not self.token:
            print("❌ Token de Telegram no configurado")
            return        
        
        try:
            self.application = Application.builder().token(self.token).build()
            
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("ayuda", self.help_command))
            self.application.add_handler(CommandHandler("mismensajes", self.my_messages_command))
            self.application.add_handler(CommandHandler("connect", self.handle_connect_command))
            self.application.add_handler(CommandHandler("disconnect", self.handle_disconnect_command))
            self.application.add_handler(CommandHandler("status", self.handle_status_command))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            await self.application.initialize()
            await self.application.start()

            try:
                self._polling_task = asyncio.create_task(self.application.updater.start_polling())
            except Exception as e:
                print("⚠️ start_polling() falló, intentando fallback run_polling():", e)
                self._polling_task = asyncio.create_task(self.application.run_polling(close_loop=False, stop_signals=None))

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
                if self.application:
                    await self.application.stop()
                    await self.application.shutdown()
            except Exception as e2:
                print("⚠️ Error intentando limpiar la aplicación tras fallo:", e2)

    async def stop_bot(self):
        """Detiene el bot limpiamente sin cerrar el event loop global."""
        try:
            if hasattr(self, "_polling_task") and self._polling_task:
                try:
                    if self.application and getattr(self.application, "updater", None):
                        try:
                            await self.application.updater.stop_polling()
                        except Exception:
                            pass

                    if not self._polling_task.done():
                        self._polling_task.cancel()
                        try:
                            await self._polling_task
                        except asyncio.CancelledError:
                            pass
                except Exception as e:
                    print("⚠️ Error deteniendo tarea de polling:", e)

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