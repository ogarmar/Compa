
from sqlalchemy import select
from .database import async_session, DeviceData


async def link_chat_to_device(device_code: str, chat_id: str) -> bool:
    """
    Search a device by its 'device_code' and assings a 'telegram_chat_id'.
    """
    async with async_session() as session:
        stmt = select(DeviceData).where(DeviceData.device_code == device_code)
        result = await session.execute(stmt)
        device_data = result.scalar_one_or_none()

        if device_data:
            device_data.telegram_chat_id = int(chat_id)
            await session.commit()
            print(f"🔗 Dispositivo {device_data.device_id} vinculado a chat {chat_id}")
            return True
        
        print(f"⚠️ No se encontró dispositivo con código {device_code} para vincular.")
        return False


async def get_chat_id_from_device_db(device_id: str) -> str | None:
    """
    Get the telegram_chat_id for a device_id.
    """
    async with async_session() as session:
        stmt = select(DeviceData.telegram_chat_id).where(DeviceData.device_id == device_id)
        result = await session.execute(stmt)
        chat_id = result.scalar_one_or_none()
        return chat_id


async def get_device_from_chat_db(chat_id: str) -> str | None:
    """
    Get the device code from the database
    """
    async with async_session() as session:
        stmt = select(DeviceData.device_id).where(DeviceData.telegram_chat_id == int(chat_id))
        result = await session.execute(stmt)
        device_id = result.scalar_one_or_none()
        return device_id