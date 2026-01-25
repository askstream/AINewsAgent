"""Модели базы данных для новостей и RSS каналов"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import Config
import os

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


class SearchHistory(Base):
    """Модель истории запросов поиска"""
    __tablename__ = 'search_history'
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Параметры запроса
    rss_feeds = Column(Text, nullable=False)  # RSS каналы (каждый с новой строки)
    selection_criteria = Column(Text, nullable=False)  # Критерий отбора
    
    # Дополнительные настройки
    llm_model = Column(String(100))
    llm_temperature = Column(Float)
    similarity_threshold = Column(Float)
    openai_api_base = Column(String(500))
    
    # Результаты и статистика в JSON
    results_data = Column(JSON)  # Статистика и другие данные
    
    # Связь с статьями
    articles = relationship("NewsArticle", back_populates="search_history", cascade="all, delete-orphan")


class NewsArticle(Base):
    """Модель новостной статьи"""
    __tablename__ = 'news_articles'
    __table_args__ = (
        UniqueConstraint('link', 'search_history_id', name='uq_article_link_history'),
    )
    
    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    content = Column(Text)
    link = Column(String(1000), nullable=False, index=True)
    source = Column(String(200))
    published_at = Column(DateTime)
    collected_at = Column(DateTime, default=datetime.utcnow)
    
    # Связь с историей запросов
    search_history_id = Column(Integer, ForeignKey('search_history.id'), nullable=True, index=True)
    search_history = relationship("SearchHistory", back_populates="articles")
    
    # Результаты обработки
    is_duplicate = Column(Boolean, default=False)
    duplicate_of = Column(Integer, nullable=True)  # ID оригинальной статьи
    relevance_score = Column(Float, nullable=True)  # Оценка релевантности (0-1)
    is_relevant = Column(Boolean, default=False)
    classification_reason = Column(Text)  # Причина классификации
    
    # Хеш для быстрой проверки дубликатов
    content_hash = Column(String(64), index=True)


# Создание движка БД и сессии
# Убеждаемся, что директория data существует
db_url = Config.DATABASE_URL
if db_url.startswith('sqlite:///'):
    db_path = db_url.replace('sqlite:///', '')
    if '/' in db_path or '\\' in db_path:
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

engine = create_engine(Config.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Инициализация базы данных"""
    # Убеждаемся, что директория существует
    if Config.DATABASE_URL.startswith('sqlite:///'):
        db_path = Config.DATABASE_URL.replace('sqlite:///', '')
        if '/' in db_path or '\\' in db_path:
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
    
    Base.metadata.create_all(engine)


def get_db_session():
    """Получение сессии БД"""
    return SessionLocal()

