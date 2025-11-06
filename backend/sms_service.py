import os
import secrets
from datetime import datetime, timedelta
from twilio.rest import Client
from sqlalchemy import select
from .database import async_session, PhoneVerification, UserSession

class SMSVerificationService:
    """Servicio para enviar y verificar códigos SMS"""
    
    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.verify_sid = os.getenv("TWILIO_VERIFY_SERVICE_SID")
        
        if not all([self.account_sid, self.auth_token, self.verify_sid]):
            raise ValueError("⚠️ Credenciales de Twilio no configuradas")
        
        self.client = Client(self.account_sid, self.auth_token)
    
    async def send_verification_code(self, phone_number: str) -> dict:
        """Envía código de verificación por SMS usando Twilio Verify"""
        try:
            # Normalizar número (debe empezar con +)
            if not phone_number.startswith('+'):
                phone_number = f'+{phone_number}'
            
            # Enviar usando Twilio Verify API
            verification = self.client.verify.v2.services(self.verify_sid) \
                .verifications \
                .create(to=phone_number, channel='sms')
            
            print(f"✅ SMS enviado a {phone_number} - Status: {verification.status}")
            
            return {
                "success": True,
                "phone_number": phone_number,
                "status": verification.status,
                "message": "Código enviado correctamente"
            }
            
        except Exception as e:
            print(f"❌ Error enviando SMS: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Error al enviar el código"
            }
    
    async def verify_code(self, phone_number: str, code: str) -> dict:
        """Verifica el código SMS ingresado por el usuario"""
        try:
            if not phone_number.startswith('+'):
                phone_number = f'+{phone_number}'
            
            # Verificar código con Twilio
            verification_check = self.client.verify.v2.services(self.verify_sid) \
                .verification_checks \
                .create(to=phone_number, code=code)
            
            if verification_check.status == 'approved':
                # Crear sesión en la base de datos
                session_token = secrets.token_urlsafe(32)
                
                async with async_session() as session:
                    new_session = UserSession(
                        phone_number=phone_number,
                        session_token=session_token,
                        verified=True
                    )
                    session.add(new_session)
                    await session.commit()
                    await session.refresh(new_session)
                
                print(f"✅ Código verificado para {phone_number}")
                
                return {
                    "success": True,
                    "verified": True,
                    "session_token": session_token,
                    "session_id": new_session.id,
                    "message": "Verificación exitosa"
                }
            else:
                return {
                    "success": False,
                    "verified": False,
                    "message": "Código incorrecto"
                }
                
        except Exception as e:
            print(f"❌ Error verificando código: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Error en la verificación"
            }
    
    async def validate_session(self, session_token: str) -> dict:
        """Valida si una sesión es válida y activa"""
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
                        "phone_number": session.phone_number,
                        "device_id": session.device_id
                    }
                else:
                    return {"valid": False}
                    
        except Exception as e:
            print(f"❌ Error validando sesión: {e}")
            return {"valid": False, "error": str(e)}
    
    async def link_session_to_device(self, session_token: str, device_id: str) -> bool:
        """Vincula una sesión verificada con un dispositivo"""
        try:
            async with async_session() as db_session:
                stmt = select(UserSession).where(
                    UserSession.session_token == session_token
                )
                result = await db_session.execute(stmt)
                session = result.scalar_one_or_none()
                
                if session:
                    session.device_id = device_id
                    await db_session.commit()
                    print(f"🔗 Sesión vinculada al dispositivo {device_id}")
                    return True
                    
                return False
                
        except Exception as e:
            print(f"❌ Error vinculando sesión: {e}")
            return False


# Instancia global del servicio
sms_service = SMSVerificationService() if all([
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN"),
    os.getenv("TWILIO_VERIFY_SERVICE_SID")
]) else None