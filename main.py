import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from commands import router

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)

async def main():
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        from functions.charge_functions import _session
        if _session and not _session.closed:
            await _session.close()

if __name__ == "__main__":
    asyncio.run(main())
