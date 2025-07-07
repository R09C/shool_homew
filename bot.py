# bot.py

import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.web_app import check_webapp_signature, safe_parse_webapp_init_data
from aiogram.client.default import DefaultBotProperties
from aiohttp import web

# --- SQLAlchemy Imports ---
from sqlalchemy import select, update, String, BigInteger, DateTime, Integer, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# --- НАСТРОЙКА ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- КОНФИГУРАЦИЯ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
# Render предоставит эти переменные в вашем окружении
BOT_TOKEN = os.getenv("BOT_TOKEN")
# URL, который предоставит Render (e.g., https://your-app-name.onrender.com)
WEBAPP_URL = os.getenv("WEBAPP_URL")
# Render предоставит внутренний URL для базы данных
DATABASE_URL = os.getenv("DATABASE_URL")
# Render сам подставит порт. Для локального запуска можно оставить 8080
PORT = int(os.getenv("PORT", 8080))


# --- НАСТРОЙКА БАЗЫ ДАННЫХ (SQLAlchemy 2.0) ---
engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# Базовый класс для наших моделей
class Base(DeclarativeBase):
    pass


# Модель пользователя
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    points: Mapped[int] = mapped_column(Integer, default=0)
    completed_tasks: Mapped[list] = mapped_column(JSON, default=list)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "registered_at": self.registered_at.isoformat(),
            "points": self.points,
            "completed_tasks": self.completed_tasks,
        }


# Модель задания
class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    difficulty: Mapped[str] = mapped_column(String(20))
    points: Mapped[int] = mapped_column(Integer)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# --- ХЭНДЛЕРЫ БОТА (ЛОГИКА) ---
dp = Dispatcher()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))


@dp.message(Command("start"))
async def start_command(message: types.Message, session: AsyncSession):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    user = await session.get(User, user_id)
    if not user:
        user = User(id=user_id, username=username)
        session.add(user)
        await session.commit()
        logger.info(f"New user registered: {username} ({user_id})")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть мини-приложение",
                    web_app=WebAppInfo(url=f"{WEBAPP_URL}/app"),
                )
            ]
        ]
    )
    await message.answer(
        f"Привет, {username}! 👋\nДобро пожаловать в кодинг-платформу!",
        reply_markup=keyboard,
    )


@dp.message(Command("profile"))
async def profile_command(message: types.Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    profile_text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Имя: {user.username}\n"
        f"Баллы: {user.points}\n"
        f"Решено задач: {len(user.completed_tasks)}\n"
        f"Дата регистрации: {user.registered_at.strftime('%d.%m.%Y')}"
    )
    await message.answer(profile_text)


# --- WEB-СЕРВЕР (AIOHTTP) ---


@web.middleware
async def db_session_middleware(request: web.Request, handler):
    async with async_session() as session:
        request["session"] = session
        response = await handler(request)
        return response


async def webapp_handler(request: web.Request) -> web.Response:
    return web.FileResponse("static/index.html")


async def api_get_user_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        init_data = data.get("initData")

        if not check_webapp_signature(BOT_TOKEN, init_data):
            return web.json_response(
                {"ok": False, "error": "Invalid signature"}, status=401
            )

        webapp_data = safe_parse_webapp_init_data(BOT_TOKEN, init_data=init_data)

        session: AsyncSession = request["session"]
        user = await session.get(User, webapp_data.user.id)
        if user:
            return web.json_response({"ok": True, "user": user.to_dict()})
        else:
            return web.json_response(
                {"ok": False, "error": "User not found"}, status=404
            )
    except Exception as e:
        logger.error(f"Get user error: {e}")
        return web.json_response(
            {"ok": False, "error": "Internal server error"}, status=500
        )


async def api_tasks_handler(request: web.Request) -> web.Response:
    session: AsyncSession = request["session"]
    result = await session.execute(select(Task))
    tasks = [task.to_dict() for task in result.scalars().all()]
    return web.json_response({"ok": True, "tasks": tasks})


async def api_submit_handler(request: web.Request) -> web.Response:
    session: AsyncSession = request["session"]
    try:
        data = await request.json()
        init_data = data.get("initData")

        if not check_webapp_signature(BOT_TOKEN, init_data):
            return web.json_response(
                {"ok": False, "error": "Invalid signature"}, status=401
            )

        webapp_data = safe_parse_webapp_init_data(BOT_TOKEN, init_data=init_data)
        user_id = webapp_data.user.id
        task_id = int(data.get("taskId"))

        user = await session.get(User, user_id)
        if task_id in user.completed_tasks:
            return web.json_response(
                {"ok": True, "passed": False, "message": "Вы уже решили эту задачу!"}
            )

        is_correct = True  # Заглушка для проверки кода

        if is_correct:
            task = await session.get(Task, task_id)
            user.points += task.points
            user.completed_tasks = user.completed_tasks + [task_id]
            await session.commit()

            return web.json_response(
                {
                    "ok": True,
                    "passed": True,
                    "message": f"Отлично! Задача решена. Вам начислено {task.points} баллов.",
                    "new_points": user.points,
                    "new_completed_count": len(user.completed_tasks),
                }
            )
        else:
            return web.json_response(
                {
                    "ok": True,
                    "passed": False,
                    "message": "Решение неверное. Попробуйте еще раз.",
                }
            )

    except Exception as e:
        logger.error(f"Submit error: {e}", exc_info=True)
        return web.json_response(
            {"ok": False, "error": "Submission failed"}, status=500
        )


async def on_startup(app: web.Application):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        async with async_session(bind=conn) as session:
            if not (await session.execute(select(Task))).scalars().first():
                initial_tasks = [
                    Task(
                        title="Основы Python",
                        description="Напишите функцию для сортировки массива",
                        difficulty="Легко",
                        points=10,
                    ),
                    Task(
                        title="Алгоритмы",
                        description="Реализуйте алгоритм поиска в глубину",
                        difficulty="Средне",
                        points=20,
                    ),
                    Task(
                        title="Структуры данных",
                        description="Создайте класс для работы с бинарным деревом",
                        difficulty="Сложно",
                        points=30,
                    ),
                ]
                session.add_all(initial_tasks)
                await session.commit()
                logger.info("Initial tasks have been added to the database.")

    webhook_url = f"{WEBAPP_URL}/webhook"
    await bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info(f"Webhook set to {webhook_url}")


async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    logger.info("Webhook deleted")


async def webhook_handler(request: web.Request):
    update_data = await request.json()
    update = types.Update.model_validate(update_data, context={"bot": bot})
    async with async_session() as session:
        await dp.feed_update(bot=bot, update=update, session=session)
    return web.Response()


def main():
    app = web.Application(middlewares=[db_session_middleware])
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    app.router.add_get("/app", webapp_handler)
    app.router.add_post("/webhook", webhook_handler)

    app.router.add_post("/api/getUser", api_get_user_handler)
    app.router.add_get("/api/tasks", api_tasks_handler)
    app.router.add_post("/api/submit", api_submit_handler)

    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    if not all([BOT_TOKEN, WEBAPP_URL, DATABASE_URL]):
        logger.critical(
            "Необходимые переменные окружения не установлены! (BOT_TOKEN, WEBAPP_URL, DATABASE_URL)"
        )
    else:
        main()
