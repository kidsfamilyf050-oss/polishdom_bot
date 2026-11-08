import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from config import settings
from handlers import interview, test, common, lesson
from aiogram.types import BotCommand
from db.mongo import db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=settings.TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()

dp.include_router(common.router)
dp.include_router(test.router)
dp.include_router(lesson.router)
dp.include_router(interview.router)

async def send_reminders():
    now = datetime.now().strftime("%H:%M")
    users = await db.get_users_with_reminders()
    for user in users:
        if user.get("reminder_time") == now:
            try:
                await bot.send_message(user["user_id"], f"👋 {user.get('name', 'Друг')}, время учить польский! Напиши /lesson 🇵🇱")
            except Exception as e:
                logger.error(f"Reminder error: {e}")

async def on_startup(bot: Bot):
    scheduler.add_job(send_reminders, 'cron', minute='*')
    scheduler.start()
    
    await bot.set_webhook(url=settings.WEBHOOK_URL)
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="test", description="Тест уровня"),
        BotCommand(command="lesson", description="Новый урок"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="remind", description="Напоминание (напр. /remind 21:00)"),
    ])

async def health_check(request):
    return web.json_response({"status": "ok"})

async def main():
    app = web.Application()
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=settings.WEBHOOK_PATH)
    app.on_startup.append(lambda app: on_startup(bot))
    app.router.add_get('/', health_check)
    app.router.add_get('/ping', lambda r: web.Response(text='pong'))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=settings.WEBHOOK_PORT)
    await site.start()
    logger.info("Bot started")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
