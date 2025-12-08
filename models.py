"""Модели базы данных для новостей и RSS каналов"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import Config

Base = declarative_base()


class RSSFeed(Base):
    """Модель RSS канала"""
    __tablename__ = 'rss_feeds'
    
    id = Column(Integer, primary_key=True)
    url = Column(String(500), unique=True, nullable=False)
    name = Column(String(200))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NewsArticle(Base):
    """Модель новостной статьи"""
    __tablename__ = 'news_articles'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    content = Column(Text)
    link = Column(String(1000), unique=True, nullable=False)
    source = Column(String(200))
    published_at = Column(DateTime)
    collected_at = Column(DateTime, default=datetime.utcnow)
    
    # Результаты обработки
    is_duplicate = Column(Boolean, default=False)
    duplicate_of = Column(Integer, nullable=True)  # ID оригинальной статьи
    relevance_score = Column(Float, nullable=True)  # Оценка релевантности (0-1)
    is_relevant = Column(Boolean, default=False)
    classification_reason = Column(Text)  # Причина классификации
    
    # Хеш для быстрой проверки дубликатов
    content_hash = Column(String(64), index=True)


# Создание движка БД и сессии
engine = create_engine(Config.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Инициализация базы данных"""
    Base.metadata.create_all(engine)


def get_db_session():
    """Получение сессии БД"""
    return SessionLocal()

