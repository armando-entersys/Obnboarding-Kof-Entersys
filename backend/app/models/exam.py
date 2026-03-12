# app/models/exam.py
from sqlalchemy import (
    Boolean, Column, Integer, String, Text, ForeignKey,
    TIMESTAMP, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.base import Base


class ExamCategory(Base):
    __tablename__ = 'exam_categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(20), nullable=False, default='gray')
    display_order = Column(Integer, nullable=False, default=0)
    questions_to_show = Column(Integer, nullable=False, default=10)
    min_score_percent = Column(Integer, nullable=False, default=80)
    is_active = Column(Boolean, server_default='true', nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    questions = relationship("ExamQuestion", back_populates="category")


class ExamQuestion(Base):
    __tablename__ = 'exam_questions'

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("exam_categories.id"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    options = Column(JSONB, nullable=False)       # ["opA", "opB", "opC", "opD"]
    correct_answer = Column(Text, nullable=False)
    is_active = Column(Boolean, server_default='true', nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    category = relationship("ExamCategory", back_populates="questions")
