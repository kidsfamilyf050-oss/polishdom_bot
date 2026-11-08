import asyncio
import logging
import os
import time
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiogram.exceptions import TelegramAPIError
from config import settings
from handlers import interview, test, common, word
from aiogram.types import BotCommand

from utils.subscription import SubscriptionCheckMiddleware
from db.mongo import db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
START_TIME = time.time()

required_env_vars = {'TOKEN': settings.TOKEN, 'MONGO_URI': settings.MONGO_URI, 'CHANNEL_ID': settings.CHANNEL_ID}
for var_name, var_value in required_env_vars.items():
    if not var_value:
        logger.error(f"Missing required environment variable: {var_name}")
        raise ValueError(f"Missing required environment variable: {var_name}")

if os.getenv('RENDER_EXTERNAL_URL'):
    WEBHOOK_HOST = os.getenv('RENDER_EXTERNAL_URL').rstrip('/')
    WEBHOOK_PORT = 10000
    settings.IS_PRODUCTION = True
    WEBHOOK_URL = f"{WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
else:
    WEBHOOK_HOST = settings.WEBHOOK_HOST.rstrip('/')
    WEBHOOK_PORT = settings.WEBHOOK_PORT
    WEBHOOK_URL = f"{WEBHOOK_HOST}{settings.WEBHOOK_PATH}"

bot = Bot(token=settings.TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

dp.message.middleware(SubscriptionCheckMiddleware())
dp.callback_query.middleware(SubscriptionCheckMiddleware())

# Регистрация роутеров
dp.include_router(common.router)
dp.include_router(interview.router)
dp.include_router(test.router)
dp.include_router(word.router) # <-- ДОБАВЛЕН НОВЫЙ РОУТЕР

commands = [
    BotCommand(command="start", description="Начать работу с ботом"),
    BotCommand(command="test", description="Узнать свой уровень"),
    BotCommand(command="interview", description="Тренажер интервью"),
    BotCommand(command="word", description="Учить новое слово с озвучкой"),
]

async def check_telegram_token():
    try:
        bot_info = await bot.me()
        logger.info(f"Bot authorized as @{bot_info.username}")
        return True
    except TelegramAPIError as e:
        logger.error(f"Failed to authorize bot: {e}")
        return False

async def check_mongo_connection():
    try:
        await db.db.command('ping')
        logger.info("Successfully connected to MongoDB")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return False

async def on_startup(bot: Bot):
    try:
        if not await check_telegram_token(): raise ValueError("Invalid Telegram token")
        if not await check_mongo_connection(): raise ValueError("Failed to connect to MongoDB")
        await bot.set_webhook(url=WEBHOOK_URL)
        await bot.set_my_commands(commands)
        logger.info("Bot commands registered")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

async def on_shutdown(bot: Bot):
    try:
        await bot.delete_webhook()
        await bot.session.close()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

async def health_check(request):
    try:
        mongo_status = await get_mongo_status()
        bot_status = await get_bot_status()
        uptime = int(time.time() - START_TIME)
        health_data = {
            "status": "ok" if mongo_status["ok"] and bot_status["ok"] else "error",
            "timestamp": time.time(),
            "uptime_seconds": uptime,
            "environment": "production" if settings.IS_PRODUCTION else "development",
            "services": {"mongodb": mongo_status, "telegram_bot": bot_status},
            "version": "1.0.0"
        }
        return web.json_response(health_data, status=200 if health_data["status"] == "ok" else 500)
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)

async def main():
    try:
        app = web.Application()
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path=settings.WEBHOOK_PATH)
        
        app.on_startup.append(lambda app: on_startup(bot))
        app.on_shutdown.append(lambda app: on_shutdown(bot))
        
        app.router.add_get('/', health_check)
        app.router.add_get('/ping', lambda r: web.Response(text='pong'))

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host='0.0.0.0', port=WEBHOOK_PORT)
        await site.start()
        
        logger.info(f"Bot started on port {WEBHOOK_PORT}")
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Error during bot startup: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
