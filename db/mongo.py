from motor.motor_asyncio import AsyncIOMotorClient
from config import settings
import logging

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGO_URI)
        self.db = self.client[settings.MONGODB_DB]

    async def get_user(self, user_id: int):
        return await self.db.users.find_one({"user_id": user_id})

    async def get_all_users(self):
        """Возвращает всех пользователей для таблицы лидеров."""
        return await self.db.users.find().to_list(length=None)

    async def create_user(self, user_id: int, username: str):
        user_data = {
            "user_id": user_id,
            "username": username,
            "name": None,
            "language_level": "A0",
            "reminder_time": None,
            "learned_words": [],
            "timezone": "Asia/Almaty",
            "perfect_streak": 0,
            "lessons_completed": 0
        }
        await self.db.users.insert_one(user_data)
        return user_data

    async def update_user_field(self, user_id: int, field: str, value):
        await self.db.users.update_one({"user_id": user_id}, {"$set": {field: value}})

    async def add_learned_words(self, user_id: int, words: list):
        if words:
            await self.db.users.update_one({"user_id": user_id}, {"$addToSet": {"learned_words": {"$each": words}}})

    async def increment_field(self, user_id: int, field: str, value: int = 1):
        await self.db.users.update_one({"user_id": user_id}, {"$inc": {field: value}})

    async def reset_field(self, user_id: int, field: str, value: int = 0):
        await self.db.users.update_one({"user_id": user_id}, {"$set": {field: value}})

    async def get_users_with_reminders(self):
        cursor = self.db.users.find({"reminder_time": {"$ne": None}})
        return await cursor.to_list(length=None)

db = Database()
