import os
import json
import asyncio
from datetime import datetime
from telegram import Update, BotCommand 
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiofiles
import traceback
import secrets
from sqlalchemy import select, delete, update as sqlalchemy_update
from .database import async_session, PhoneVerification, DeviceData, UserConnections, FamilyMessages

# --- Variables Globales ---
ACTIVE_WEBSOCKETS = {}
PENDING_REQUESTS = {}

def set_shared_state(active_ws: dict, pending_req: dict):
    global ACTIVE_WEBSOCKETS, PENDING_REQUESTS
    ACTIVE_WEBSOCKETS = active_ws
    print("✅ Global state received in telegram_bot")


class FamilyMessagesBot:
    def __init__(self, token):
        self.token = token
        self.application = None
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_name = update.effective_user.first_name
        await update.message.reply_text(
            f"👋 ¡Hola {user_name}! Soy el bot de Compa.\n\n"
            "Con este bot puedes enviar mensajes a tus familiares.\n\n"
            "Usa el menú (el botón `/`) para ver todos los comandos disponibles.",
            parse_mode="Markdown"
        )

    # --- FIXED METHOD ---
    async def get_unread_messages(self):
        """Get all unread messages sorted chronologically by timestamp from database"""
        try:
            async with async_session() as session:
                # Query unread messages from database
                stmt = select(FamilyMessages).where(
                    FamilyMessages.read == False
                ).order_by(FamilyMessages.timestamp.asc())
                
                result = await session.execute(stmt)
                db_messages = result.scalars().all()
                
                # Convert to format expected by frontend
                unread = [
                    {
                        "id": msg.id,
                        "sender_name": msg.sender_name,
                        "message": msg.message,
                        "chat_id": msg.telegram_chat_id,
                        "timestamp": msg.timestamp.isoformat(),
                        "date": msg.timestamp.strftime("%d/%m/%Y"),
                        "time": msg.timestamp.strftime("%H:%M"),
                        "read": msg.read
                    }
                    for msg in db_messages
                ]
                
                print(f"📬 get_unread_messages() devolvió {len(unread)} mensajes")
                return unread
                
        except Exception as e:
            print(f"❌ Error en get_unread_messages: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """🆘 **Ayuda - Bot Compa (Multidispositivo)**

*COMANDOS DE GESTIÓN:*
• `/connect <código>`
  Vincula tu cuenta de Telegram a un dispositivo Compa usando su código de 6 dígitos.

• `/alias <código> <nombre>`
  Asigna un nombre fácil de recordar a un dispositivo que ya hayas conectado.
  Ej: `/alias 123456 Mama`

• `/disconnect <nombre>`
  Desvincula un dispositivo usando su alias.
  Ej: `/disconnect Mama`

• `/login`
  Genera un enlace mágico para iniciar sesión en la app web.

*ENVÍO DE MENSAJES:*
• `/m <nombre> <mensaje>`
  Envía un mensaje al dispositivo que especifiques por su alias.
  Ej: `/m Mama ¿Has tomado ya la medicación?`
"""
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def connect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        user_info = {
            "chat_id": chat_id,
            "user_name": update.effective_user.name,
            "user_full_name": update.effective_user.full_name,
        }

        if not context.args or len(context.args) == 0:
            await update.message.reply_text("Uso: `/connect <código_dispositivo>`", parse_mode="Markdown")
            return
            
        device_code = context.args[0]
        
        async with async_session() as session:
            stmt_dev = select(DeviceData).where(DeviceData.device_code == device_code)
            device = (await session.execute(stmt_dev)).scalar_one_or_none()
            
            if not device:
                await update.message.reply_text(f"❌ Código de dispositivo '{device_code}' no encontrado.")
                return
            
            device_id = device.device_id
            
            stmt_conn = select(UserConnections).where(
                UserConnections.telegram_chat_id == chat_id,
                UserConnections.device_id == device_id
            )
            existing_conn = (await session.execute(stmt_conn)).scalar_one_or_none()
            
            if existing_conn:
                await update.message.reply_text(f"✅ Ya estabas conectado a este dispositivo (Alias: {existing_conn.alias or 'ninguno'}).")
                return
            
            websocket = ACTIVE_WEBSOCKETS.get(device_id)
            if not websocket:
                await update.message.reply_text("❌ Dispositivo no conectado. Asegúrate de que la app esté abierta en el dispositivo antes de conectar.")
                return
            
            request_id = secrets.token_urlsafe(16)
            PENDING_REQUESTS[request_id] = {
                "chat_id": chat_id,
                "user_info": user_info,
                "device_id": device_id,
                "device_code": device_code,
                "timestamp": datetime.utcnow()
            }
            
            try:
                await websocket.send_text(json.dumps({
                    "type": "connection_request",
                    "request_id": request_id,
                    "user_info": user_info
                }))
                await update.message.reply_text(f"⏳ Solicitud enviada al dispositivo {device_code}. Por favor, pide al usuario de la app que apruebe la conexión.")
                print(f"🔔 Solicitud de conexión {request_id} enviada a {device_id} para chat {chat_id}")
            except Exception as e:
                print(f"❌ Error enviando solicitud por WebSocket: {e}")
                await update.message.reply_text("❌ Error al contactar con el dispositivo. Inténtalo de nuevo.")
                if request_id in PENDING_REQUESTS:
                    del PENDING_REQUESTS[request_id]

    async def process_connection_response(self, request_id: str, approved: bool, websocket):
        """Procesa la respuesta (aprobación/rechazo) del frontend"""
        print(f"Processing connection response for {request_id}, approved: {approved}")
        
        request_data = PENDING_REQUESTS.get(request_id)
        if not request_data:
            print(f"⚠️ Solicitud {request_id} no encontrada o ya procesada.")
            try:
                await websocket.send_text(json.dumps({"type": "error", "text": "Solicitud no encontrada."}))
            except: pass
            return

        chat_id = request_data["chat_id"]
        user_name = request_data["user_info"]["user_full_name"]
        device_id = request_data["device_id"]
        device_code = request_data["device_code"]

        del PENDING_REQUESTS[request_id]

        try:
            if approved:
                async with async_session() as session:
                    new_connection = UserConnections(
                        telegram_chat_id=chat_id,
                        device_id=device_id,
                        alias=None 
                    )
                    session.add(new_connection)
                    await session.commit()
                
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ ¡Conexión Aprobada!\n\n"
                         f"Ahora estás conectado al dispositivo {device_code}.\n"
                         f"Usa `/alias {device_code} <nombre>` para ponerle un nombre fácil (ej: `/alias {device_code} Mama`).",
                    parse_mode="Markdown"
                )
                
                await websocket.send_text(json.dumps({
                    "type": "connection_approved",
                    "user_name": user_name,
                    "chat_id": chat_id
                }))
                
            else:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Conexión Rechazada.\n\nEl usuario del dispositivo {device_code} ha rechazado tu solicitud."
                )
                
        except Exception as e:
            print(f"❌ Error al procesar la respuesta de conexión: {e}")
            traceback.print_exc()

    async def alias_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("Uso: `/alias <código_o_alias_actual> <nuevo_alias>`\nEj: `/alias 123456 Mama`", parse_mode="Markdown")
            return

        code_or_alias = context.args[0]
        new_alias = context.args[1]
        
        async with async_session() as session:
            target_device_id = None
            
            device_by_code = (await session.execute(select(DeviceData).where(DeviceData.device_code == code_or_alias))).scalar_one_or_none()
            if device_by_code:
                target_device_id = device_by_code.device_id
            
            if not target_device_id:
                conn_by_alias = (await session.execute(
                    select(UserConnections).where(
                        UserConnections.telegram_chat_id == chat_id,
                        UserConnections.alias == code_or_alias
                    )
                )).scalar_one_or_none()
                if conn_by_alias:
                    target_device_id = conn_by_alias.device_id
            
            if not target_device_id:
                await update.message.reply_text(f"❌ No encuentro el dispositivo con código o alias '{code_or_alias}'.")
                return

            stmt_update = (
                sqlalchemy_update(UserConnections) 
                .where(
                    UserConnections.telegram_chat_id == chat_id,
                    UserConnections.device_id == target_device_id
                )
                .values(alias=new_alias)
            )
            
            try:
                result = await session.execute(stmt_update)
                if result.rowcount == 0:
                    await update.message.reply_text(f"❌ No estás conectado a ese dispositivo. Usa `/connect {code_or_alias}` primero.", parse_mode="Markdown")
                else:
                    await session.commit()
                    await update.message.reply_text(f"✅ ¡Alias actualizado! Ahora '{new_alias}' apunta al dispositivo.")
            except Exception as e:
                await session.rollback()
                print(f"❌ Error al actualizar alias: {e}")
                await update.message.reply_text(f"❌ Error: Ese alias (`{new_alias}`) ya está en uso. Elige otro.", parse_mode="Markdown")

    async def disconnect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        
        if not context.args or len(context.args) == 0:
            await update.message.reply_text("Uso: `/disconnect <alias_dispositivo>`", parse_mode="Markdown")
            return
            
        alias = context.args[0]
        
        async with async_session() as session:
            stmt_delete = (
                delete(UserConnections)
                .where(
                    UserConnections.telegram_chat_id == chat_id,
                    UserConnections.alias == alias
                )
            )
            result = await session.execute(stmt_delete)
            await session.commit()
            
            if result.rowcount == 0:
                await update.message.reply_text(f"❌ No he encontrado ningún dispositivo con el alias '{alias}'.")
            else:
                await update.message.reply_text(f"✅ Desconectado del dispositivo '{alias}'.")

    async def message_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        sender_name = update.effective_user.first_name
        
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("Uso: `/m <alias> <mensaje>`\nEj: `/m Mama ¡Hola!`", parse_mode="Markdown")
            return

        alias = context.args[0]
        message_text = " ".join(context.args[1:])
        
        async with async_session() as session:
            stmt_conn = select(UserConnections).where(
                UserConnections.telegram_chat_id == chat_id,
                UserConnections.alias == alias
            )
            connection = (await session.execute(stmt_conn)).scalar_one_or_none()
            
            if not connection:
                await update.message.reply_text(f"❌ No tienes ningún dispositivo con el alias '{alias}'.\nUsa `/connect` y `/alias` primero.", parse_mode="Markdown")
                return
            
            new_message = FamilyMessages(
                device_id=connection.device_id,
                telegram_chat_id=chat_id,
                sender_name=sender_name,
                message=message_text,
                timestamp=datetime.utcnow(),
                read=False
            )
            session.add(new_message)
            await session.commit()
            
            await update.message.reply_text(f"✅ Mensaje enviado a '{alias}'.")
            
            websocket = ACTIVE_WEBSOCKETS.get(connection.device_id)
            if websocket:
                try:
                    await websocket.send_text(json.dumps({
                        "type": "new_message_notification"
                    }))
                    print(f"📨 Notificación de mensaje nuevo enviada a {connection.device_id}")
                except Exception as e:
                    print(f"❌ Error notificando a WebSocket {connection.device_id}: {e}")

    async def login_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        user_name = update.effective_user.first_name
        token = secrets.token_urlsafe(32)
        try:
            async with async_session() as session:
                from datetime import datetime, timedelta
                await session.execute(
                    delete(PhoneVerification).where(PhoneVerification.phone_number == str(chat_id))
                )
                new_token = PhoneVerification(
                    id=secrets.token_urlsafe(16),
                    phone_number=str(chat_id),
                    verification_code=token,
                    expires_at=datetime.utcnow() + timedelta(minutes=5)
                )
                session.add(new_token)
                await session.commit()
            
            base_url = os.getenv("APP_BASE_URL", "http://localhost:8000") 
            login_link = f"{base_url}/auth/login_telegram?token={token}"
            
            await update.message.reply_text(
                f"¡Hola {user_name}! 👋\n\n"
                f"Para iniciar sesión en Compa, haz clic en este enlace. Es válido por 5 minutos:\n\n"
                f"`{login_link}`\n\n"
                f"(Si no has solicitado esto, puedes ignorar este mensaje).",
                parse_mode="Markdown"
            )
            print(f"🔑 Enlace de login generado para el chat {chat_id}")
        except Exception as e:
            print(f"❌ Error al generar token de login: {e}")
            await update.message.reply_text("Lo siento, ha ocurrido un error al intentar iniciar sesión.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "ℹ️ Para enviar un mensaje, por favor usa el formato:\n"
            "`/m <alias> <tu mensaje>`\n\n"
            "Ejemplo: `/m Mama ¡Hola!`\n\n"
            "Si no sabes qué alias tienes, usa `/connect` y `/alias` para (re)configurarlos.",
            parse_mode="Markdown"
        )

    async def start_bot(self):
        if not self.token:
            print("❌ Token de Telegram no configurado")
            return        
        
        try:
            print(f"🔄 Intentando iniciar bot de Telegram...")
            self.application = Application.builder().token(self.token).build()

            commands = [
                BotCommand("start", "👋 Bienvenida e info"),
                BotCommand("connect", "🔗 Conectar a un dispositivo (ej: /connect 123456)"),
                BotCommand("alias", "🏷️ Asignar nombre a dispositivo (ej: /alias 123456 Mama)"),
                BotCommand("m", "💬 Enviar mensaje a un dispositivo (ej: /m Mama ¡Hola!)"),
                BotCommand("disconnect", "🔌 Desconectar un dispositivo (ej: /disconnect Mama)"),
                BotCommand("login", "🔑 Iniciar sesión en la app web"),
                BotCommand("help", "🆘 Mostrar ayuda"),
            ]
            await self.application.bot.set_my_commands(commands)
            print("✅ Comandos del bot actualizados en Telegram.")
            
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("ayuda", self.help_command))
            self.application.add_handler(CommandHandler("login", self.login_command))
            self.application.add_handler(CommandHandler("connect", self.connect_command))
            self.application.add_handler(CommandHandler("alias", self.alias_command))
            self.application.add_handler(CommandHandler("disconnect", self.disconnect_command))
            self.application.add_handler(CommandHandler("m", self.message_command))
            
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))                
            
            await self.application.initialize()
            await self.application.start()
            self._polling_task = asyncio.create_task(self.application.updater.start_polling())
            
            print("✅ Bot de Telegram (Multidispositivo) iniciado correctamente")
            
        except Exception as e:
            print(f"❌ Error iniciando bot de Telegram: {e}")
            traceback.print_exc()

    async def stop_bot(self):
        print("🛑 Iniciando parada del bot de Telegram...")
        try:
            if hasattr(self, "_polling_task") and self._polling_task and not self._polling_task.done():
                self._polling_task.cancel()
            if self.application:
                await self.application.stop()
                await self.application.shutdown()
            print("✅ Bot de Telegram detenido correctamente")
        except Exception as e:
            print(f"❌ Error crítico en stop_bot: {e}")