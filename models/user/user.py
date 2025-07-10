from ..base_model import Base
from sqlalchemy import BigInteger, String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    points: Mapped[int] = mapped_column(Integer, default=0)

    task_completions = relationship("UserTask", back_populates="user")

    @property
    def completed_tasks(self):
        return [completion.task for completion in self.task_completions]

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "registered_at": self.registered_at.isoformat(),
            "points": self.points,
            "completed_tasks": [
                {
                    "id": completion.task.id,
                    "title": completion.task.title,
                    "earned_points": completion.earned_points,
                    "completed_at": completion.completed_at.isoformat(),
                }
                for completion in self.task_completions
            ],
        }
