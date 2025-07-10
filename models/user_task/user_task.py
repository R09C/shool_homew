from sqlalchemy import BigInteger, ForeignKey, DateTime, Integer, Column
from sqlalchemy.orm import relationship, mapped_column
from ..base_model import Base
from datetime import datetime


class UserTask(Base):
    __tablename__ = "user_tasks"

    user_id = Column(BigInteger, ForeignKey("users.id"), primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), primary_key=True)
    earned_points = Column(Integer, nullable=False)  
    completed_at = Column(DateTime, default=datetime.utcnow)  

    
    user = relationship("User", back_populates="task_completions")
    task = relationship("Task", back_populates="user_completions")

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "task_id": self.task_id,
            "earned_points": self.earned_points,
            "completed_at": self.completed_at.isoformat(),
        }
