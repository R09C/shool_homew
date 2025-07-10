import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.web_app import check_webapp_signature, safe_parse_webapp_init_data
from aiohttp import web
from sqlalchemy import (
    select,
    update,
    String,
    BigInteger,
    DateTime,
    Integer,
    JSON,
    Table,
    Column,
    ForeignKey,
    func,
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import selectinload

# --- Предполагаемая структура моделей (для контекста) ---
# Эти модели не были предоставлены, но необходимы для работы кода.
# Я добавил их сюда для полноты и ясности.

from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    username = Column(String(255), nullable=False)
    points = Column(Integer, default=0, nullable=False)
    registered_at = Column(DateTime, default=func.now())
    task_completions = relationship(
        "UserTask", back_populates="user", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "points": self.points,
            "registered_at": self.registered_at.isoformat(),
            "completed_tasks_count": len(self.task_completions),
        }


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    difficulty = Column(String, nullable=False)
    points = Column(Integer, nullable=False)
    inference = Column(String, default="")  # Поле для кода-шаблона
    created_at = Column(DateTime, default=func.now())

    @classmethod
    async def generate_task_from_topic(cls, topic: str):
        # Здесь должна быть логика генерации задачи, например, через API GPT
        # Для примера, возвращаем моковые данные
        return cls(
            title=f"Задача по теме: {topic}",
            description="Сгенерированное описание для задачи на тему " + topic,
            difficulty="Средне",
            points=10,
        )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "difficulty": self.difficulty,
            "points": self.points,
            "created_at": self.created_at.isoformat(),
        }


class UserTask(Base):
    __tablename__ = "user_tasks"
    user_id = Column(BigInteger, ForeignKey("users.id"), primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), primary_key=True)
    earned_points = Column(Integer, nullable=False)
    completed_at = Column(DateTime, default=func.now())
    user = relationship("User", back_populates="task_completions")
    task = relationship("Task")


# --- Конец предполагаемой структуры моделей ---

# Импорт функции-проверки кода (предполагается, что она существует)
from check_code import perform_comprehensive_evaluation

# --- Конфигурация ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 8080))

# --- Настройка SQLAlchemy ---
engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# --- Настройка Aiogram ---
dp = Dispatcher()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))


# --- Обработчики команд бота ---


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
    # Используем selectinload для эффективной загрузки связанных данных (решенных задач)
    # одним запросом к БД, чтобы избежать дополнительных запросов (lazy loading).
    stmt = (
        select(User)
        .options(selectinload(User.task_completions))
        .where(User.id == message.from_user.id)
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("Вы не зарегистрированы. Используйте /start")
        return

    profile_text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Имя: {user.username}\n"
        f"Баллы: {user.points}\n"
        f"Решено задач: {len(user.task_completions)}\n"
        f"Дата регистрации: {user.registered_at.strftime('%d.%m.%Y')}"
    )
    await message.answer(profile_text)


@dp.message(Command("newtask"))
async def create_new_task(message: types.Message, session: AsyncSession):
    topic = message.text.replace("/newtask", "").strip()
    if not topic:
        await message.answer(
            "Укажите тему для задания, например: /newtask алгоритмы сортировки"
        )
        return

    await message.answer("Генерирую новое задание, пожалуйста, подождите...")

    try:
        task = await Task.generate_task_from_topic(topic)
        session.add(task)
        await session.commit()

        await message.answer(
            f"✅ Создано новое задание!\n\n"
            f"<b>{task.title}</b>\n"
            f"Сложность: {task.difficulty} ({task.points} баллов)\n\n"
            f"{task.description}"
        )
    except Exception as e:
        logger.error(f"Ошибка генерации задания: {e}", exc_info=True)
        await message.answer("Не удалось сгенерировать задание. Попробуйте позже.")


# --- Веб-сервер и API ---


@web.middleware
async def db_session_middleware(request: web.Request, handler):
    """Middleware для предоставления сессии БД каждому запросу."""
    async with async_session() as session:
        request["session"] = session
        response = await handler(request)
        return response


async def webapp_handler(request: web.Request) -> web.Response:
    """Отдает главную страницу веб-приложения."""
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

        # Эффективно загружаем пользователя и связанные данные
        stmt = (
            select(User)
            .options(selectinload(User.task_completions))
            .where(User.id == webapp_data.user.id)
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            # Метод to_dict может использовать связанные данные (task_completions)
            return web.json_response({"ok": True, "user": user.to_dict()})
        else:
            return web.json_response(
                {"ok": False, "error": "User not found"}, status=404
            )
    except Exception as e:
        logger.error(f"Get user error: {e}", exc_info=True)
        return web.json_response(
            {"ok": False, "error": "Internal server error"}, status=500
        )


async def api_tasks_handler(request: web.Request) -> web.Response:
    """Возвращает список всех доступных задач."""
    session: AsyncSession = request["session"]
    result = await session.execute(select(Task))
    tasks = [task.to_dict() for task in result.scalars().all()]
    return web.json_response({"ok": True, "tasks": tasks})


async def api_generate_task(request: web.Request) -> web.Response:
    """Генерирует новую задачу по запросу из веб-приложения."""
    session: AsyncSession = request["session"]
    try:
        data = await request.json()
        topic = data.get("topic", "Программирование")

        task = await Task.generate_task_from_topic(topic)
        session.add(task)
        await session.commit()

        return web.json_response({"ok": True, "task": task.to_dict()})
    except Exception as e:
        logger.error(f"Error generating task: {e}", exc_info=True)
        return web.json_response(
            {"ok": False, "error": "Не удалось сгенерировать задание"}, status=500
        )


async def api_submit_handler(request: web.Request) -> web.Response:
    """Обрабатывает отправку решения задачи из веб-приложения."""
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

        # Проверяем, решал ли пользователь эту задачу ранее
        completion_stmt = select(UserTask).where(
            UserTask.user_id == user_id, UserTask.task_id == task_id
        )
        existing_completion = (
            await session.execute(completion_stmt)
        ).scalar_one_or_none()
        if existing_completion:
            return web.json_response(
                {"ok": True, "passed": False, "message": "Вы уже решили эту задачу!"}
            )

        # Загружаем пользователя (с его решенными задачами) и саму задачу
        user_stmt = (
            select(User)
            .options(selectinload(User.task_completions))
            .where(User.id == user_id)
        )
        user = (await session.execute(user_stmt)).scalar_one_or_none()
        task = await session.get(Task, task_id)

        if not user or not task:
            return web.json_response(
                {"ok": False, "error": "User or Task not found"}, status=404
            )

        # Проверка кода
        points, is_correct = perform_comprehensive_evaluation(
            template_code=task.inference,
            submitted_code=data.get("code"),
            algorithm_name=task.title,
        )

        if is_correct > 3:  # Условие успешного решения
            new_completion = UserTask(
                user_id=user_id, task_id=task_id, earned_points=task.points
            )
            session.add(new_completion)
            user.points += task.points

            await session.commit()

            # Так как мы заранее загрузили user.task_completions через selectinload
            # и SQLAlchemy обновил эту коллекцию в памяти после session.add(),
            # мы можем получить новую длину без дополнительного запроса к БД.
            return web.json_response(
                {
                    "ok": True,
                    "passed": True,
                    "message": f"Отлично! Задача решена. Вам начислено {task.points} баллов.",
                    "new_points": user.points,
                    "new_completed_count": len(user.task_completions),
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
    """Действия при запуске приложения."""
    logger.info("Application starting up...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        async with async_session(bind=conn) as session:
            if not (await session.execute(select(Task))).scalars().first():
                logger.info("No initial tasks found. Populating database...")
                initial_tasks = [
                    Task(
                        title="Основы Python",
                        description="Напишите функцию для сортировки массива",
                        difficulty="Легко",
                        points=5,
                    ),
                    Task(
                        title="Алгоритмы",
                        description="Реализуйте алгоритм поиска в глубину",
                        difficulty="Средне",
                        points=10,
                    ),
                    Task(
                        title="Структуры данных",
                        description="Создайте класс для работы с бинарным деревом",
                        difficulty="Сложно",
                        points=15,
                    ),
                ]
                session.add_all(initial_tasks)
                await session.commit()
                logger.info("Initial tasks have been added to the database.")

    webhook_url = f"{WEBAPP_URL}/webhook"
    await bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info(f"Webhook set to {webhook_url}")


async def on_shutdown(app: web.Application):
    """Действия при остановке приложения."""
    logger.info("Application shutting down...")
    await bot.delete_webhook()
    logger.info("Webhook deleted")


async def webhook_handler(request: web.Request):
    """Принимает обновления от Telegram и передает их в Dispatcher."""
    update_data = await request.json()
    update = types.Update.model_validate(update_data, context={"bot": bot})
    async with async_session() as session:
        await dp.feed_update(bot=bot, update=update, session=session)
    return web.Response()


def main():
    """Основная функция для запуска приложения."""
    app = web.Application(middlewares=[db_session_middleware])
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # Статика и эндпоинты API
    app.router.add_get("/app", webapp_handler)
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_post("/api/getUser", api_get_user_handler)
    app.router.add_get("/api/tasks", api_tasks_handler)
    app.router.add_post("/api/submit", api_submit_handler)
    app.router.add_post("/api/generate-task", api_generate_task)

    # Статические файлы, если они есть (например, в папке 'static')
    app.router.add_static("/", path="static", name="static")

    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    if not all([BOT_TOKEN, WEBAPP_URL, DATABASE_URL]):
        logger.critical(
            "Необходимые переменные окружения не установлены! (BOT_TOKEN, WEBAPP_URL, DATABASE_URL)"
        )
    else:
        main()
