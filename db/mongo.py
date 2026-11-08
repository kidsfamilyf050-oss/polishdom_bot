from motor.motor_asyncio import AsyncIOMotorClient
from config import settings
from datetime import datetime
import logging

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGO_URI)
        self.db = self.client[settings.MONGODB_DB]

    async def get_user(self, user_id: int):
        return await self.db.users.find_one({"user_id": user_id})

    async def create_user(self, user_id: int, username: str):
        user_data = {
            "user_id": user_id,
            "username": username,
            "name": None,
            "language_level": "A0",
            "reminder_time": None,
            "learned_words": [],
            "timezone": "Asia/Almaty"
        }
        await self.db.users.insert_one(user_data)
        return user_data

    async def update_user_field(self, user_id: int, field: str, value):
        await self.db.users.update_one({"user_id": user_id}, {"$set": {field: value}})

    async def add_learned_word(self, user_id: int, word: str):
        await self.db.users.update_one({"user_id": user_id}, {"$addToSet": {"learned_words": word}})

    async def get_users_with_reminders(self):
        # Вот здесь был баг, добавлен await
        cursor = self.db.users.find({"reminder_time": {"$ne": None}})
        return await cursor.to_list(length=None)

db = Database()
