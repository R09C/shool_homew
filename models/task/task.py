
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base_model import Base
import logging
import json
import re 

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    difficulty: Mapped[str] = mapped_column(String(20))
    points: Mapped[int] = mapped_column(Integer)
    inference: Mapped[str] = mapped_column(
        String(5000), nullable=True
    )  

    
    user_completions = relationship("UserTask", back_populates="task")

    def to_dict(self):
        base_dict = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "difficulty": self.difficulty,
            "points": self.points,
            
            "created_at": self.created_at.isoformat() if hasattr(self, 'created_at') and self.created_at else None,
            
            "completion_count": len(self.user_completions) if hasattr(self, 'user_completions') and self.user_completions is not None else 0
        }
        return base_dict

    @staticmethod
    def create_task(title, description, difficulty, points, inference=None):
        """Метод для создания нового задания"""
        return Task(
            title=title,
            description=description,
            difficulty=difficulty,
            points=points,
            inference=inference,
        )

    @staticmethod
    async def generate_task_from_topic(topic):
        """Генерирует задание на основе темы"""
        try:
            from g4f.client import Client
            from g4f.models import DeepInfraChat

            client = Client()
            prompt = f"""
            Сгенерируй учебное задание по программированию на тему: "{topic}"
            
            Твой ответ ДОЛЖЕН БЫТЬ СТРОГО в формате JSON без каких-либо пояснений, вступлений или markdown-оберток.
            Никогда не используй одинарные кавычки для ключей или строк. Всегда используй двойные кавычки.
            Экранируй все двойные кавычки внутри строковых значений с помощью \\".

            Пример правильного формата:
            {{
                "title": "Краткое название задания",
                "description": "Подробное описание задания. Пример с \\"экранированием\\" кавычек.",
                "difficulty": "Средне",
                "points": 5, # Количество баллов за выполнение задания всегда 5
                "inference": "def solution():\\n    
            }}

            Вот твой запрос:
            {{
                "title": "Краткое название задания (не более 100 символов)",
                "description": "Подробное описание задания (не более 500 символов)",
                "difficulty": "Один из вариантов: 'Легко', 'Средне', 'Сложно'",
                "points": 5,  
                "inference": "Полное решение задачи на Python с комментариями"
            }}
            """

            response = client.chat.completions.create(
                model="deepseek-prover-v2-671b",
                messages=[{"role": "user", "content": prompt}],
                provider=DeepInfraChat,
            )
            
            content = response.choices[0].message.content
            logging.info(f"Получен ответ от LLM: {content}") 

            
            
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if not match:
                raise json.JSONDecodeError("Не найден JSON объект в ответе LLM", content, 0)
            
            json_str = match.group(0)

            
            task_data = json.loads(json_str)

            
            return Task.create_task(
                title=task_data.get("title"),
                description=task_data.get("description"),
                difficulty=task_data.get("difficulty"),
                points=task_data.get("points"),
                inference=task_data.get("inference"),
            )
        except Exception as e:
            logging.error(f"Ошибка при генерации задания: {e}", exc_info=True)
            raise