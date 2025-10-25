import os
import json
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiofiles

FAMILY_MESSAGES_FILE = "family_messages.json"
AUTHORIZED_USERS_FILE = "authorized_users.json"


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
        chat_id = update.effective_chat.id
        user_name = update.effective_user.first_name
        
        is_auth = await self.is_authorized(chat_id)
        
        if is_auth:
            welcome_msg = f"""¡Hola {user_name}! 👋

Soy el bot de mensajes (Compa).

✅ **Tu acceso está autorizado**

📝 **Cómo enviar un mensaje:**
Simplemente escribe tu mensaje y lo guardaré para que se escuche.

⚙️ **Comandos disponibles:**
/start - Ver este mensaje
/mismensajes - Ver tus mensajes enviados
/ayuda - Obtener ayuda"""
        else:
            welcome_msg = f"""¡Hola {user_name}! 👋

Soy el bot de mensajes (Compa).

⚠️ **Tu acceso aún no está autorizado**

📋 Tu Chat ID es: `{chat_id}`

Por favor, envía este ID al administrador para que te autorice y puedas enviar mensajes al usuario.

Una vez autorizado, podrás enviar mensajes que el usuario escuchará a través de su asistente de voz."""

        await update.message.reply_text(welcome_msg)
        print(f"🔍 Usuario {user_name} (ID: {chat_id}) solicitó /start - Autorizado: {is_auth}")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /ayuda"""
        help_text = """🆘 **Ayuda - Bot de Mensajes**

Para enviar un mensaje al usuario, simplemente escríbelo.

Ejemplo:
"Hola mamá, espero que estés bien. Te queremos mucho."

El mensaje se guardará y se podrá escucharlo cuando active el asistente.

Comandos:
/start - Inicio
/mismensajes - Ver mensajes enviados
/ayuda - Esta ayuda"""
        
        await update.message.reply_text(help_text)
    
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
        
        await update.message.reply_text(response)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja mensajes de texto normales - FORMATO RECOMENDADO"""
        chat_id = update.effective_chat.id
        user_name = update.effective_user.first_name
        message_text = update.message.text
        
        if not await self.is_authorized(chat_id):
            await update.message.reply_text(
                f"⚠️ Hola {user_name}, aún no tienes acceso autorizado.\n\n"
                f"📋 Tu Chat ID es: `{chat_id}`\n\n"
                f"Por favor, envía este ID al administrador para que te autorice.\n\n"
                f"Puedes usar /start para más información."
            )
            print(f"🚫 Usuario no autorizado intentó enviar mensaje: {user_name} (ID: {chat_id})")
            return
        
        saved = await self.save_message(user_name, message_text, chat_id)
        
        if saved:
            date_formatted = saved['date']
            time_formatted = saved['time']
            await update.message.reply_text(
                f"✅ Mensaje guardado correctamente.\n\n"
                f"👤 De: {user_name}\n"
                f"📅 Fecha: {date_formatted}\n"
                f"🕐 Hora: {time_formatted}\n\n"
                f"El usuario podrá escucharlo cuando consulte sus mensajes.\n\n"
                f"💬 Vista previa:\n{message_text[:100]}{'...' if len(message_text) > 100 else ''}\n\n"
                            )
            print(f"📨 Nuevo mensaje de {user_name} (ID: {chat_id}) el {date_formatted}: {message_text[:50]}...")
        else:
            await update.message.reply_text(
                "❌ Error al guardar el mensaje. Inténtalo de nuevo."
            )
    
    async def start_bot(self):
        """Inicia el bot de Telegram sin cerrar el event loop (compatible con FastAPI)."""
        try:
            self.application = Application.builder().token(self.token).build()

            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("ayuda", self.help_command))
            self.application.add_handler(CommandHandler("mismensajes", self.my_messages_command))
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
            if users:
                print(f"🔐 Modo PRIVADO - {len(users)} usuarios autorizados")
            else:
                print("🔐 Modo PRIVADO - Sin usuarios autorizados (nadie puede enviar mensajes)")
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