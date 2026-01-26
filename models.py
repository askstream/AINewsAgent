"""Модели базы данных для новостей и RSS каналов"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, JSON, UniqueConstraint, LargeBinary
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


class SystemSettings(Base):
    """Модель системных настроек"""
    __tablename__ = 'system_settings'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)  # Ключ настройки
    value = Column(Text, nullable=False)  # Значение настройки (JSON или строка)
    description = Column(Text)  # Описание настройки
    category = Column(String(50), nullable=False, default='general')  # Категория настройки
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
    
    # Саммари статьи
    summary = Column(Text, nullable=True)  # Краткое содержание статьи
    
    # Векторное представление для семантического поиска (JSON массив чисел)
    embedding = Column(JSON, nullable=True)  # Embedding вектор статьи


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
    
    # Создаем все таблицы
    Base.metadata.create_all(engine)
    
    # Инициализируем настройки по умолчанию (после создания таблиц)
    # Используем небольшую задержку, чтобы убедиться, что таблицы созданы
    try:
        init_default_settings()
    except Exception as e:
        print(f"Предупреждение: не удалось инициализировать настройки при старте: {e}")
        print("Настройки можно инициализировать вручную через UI")
    
    # Для SQLite: добавляем недостающие колонки, если таблица уже существует
    if Config.DATABASE_URL.startswith('sqlite:///'):
        from sqlalchemy import text
        try:
            with engine.begin() as conn:
                # Проверяем, существует ли таблица news_articles
                result = conn.execute(text("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='news_articles'
                """))
                if result.fetchone():
                    # Таблица существует, проверяем колонки
                    # Проверяем summary
                    result = conn.execute(text("""
                        SELECT COUNT(*) as cnt 
                        FROM pragma_table_info('news_articles') 
                        WHERE name = 'summary'
                    """))
                    has_summary = result.fetchone()[0] > 0
                    
                    # Проверяем embedding
                    result = conn.execute(text("""
                        SELECT COUNT(*) as cnt 
                        FROM pragma_table_info('news_articles') 
                        WHERE name = 'embedding'
                    """))
                    has_embedding = result.fetchone()[0] > 0
                    
                    # Добавляем недостающие колонки
                    if not has_summary:
                        try:
                            conn.execute(text("ALTER TABLE news_articles ADD COLUMN summary TEXT"))
                            print("Добавлена колонка summary в таблицу news_articles")
                        except Exception as e:
                            print(f"Ошибка при добавлении колонки summary: {e}")
                    
                    if not has_embedding:
                        try:
                            conn.execute(text("ALTER TABLE news_articles ADD COLUMN embedding JSON"))
                            print("Добавлена колонка embedding в таблицу news_articles")
                        except Exception as e:
                            print(f"Ошибка при добавлении колонки embedding: {e}")
        except Exception as e:
            print(f"Ошибка при проверке/обновлении схемы БД: {e}")


def init_default_settings():
    """Инициализация настроек по умолчанию (только если таблица пустая)"""
    session = get_db_session()
    try:
        # Проверяем, существует ли таблица
        from sqlalchemy import inspect
        try:
            inspector = inspect(engine)
            table_exists = 'system_settings' in inspector.get_table_names()
        except Exception as inspect_error:
            # Если inspect не работает, пробуем просто запросить данные
            print(f"Не удалось проверить существование таблицы через inspect: {inspect_error}")
            table_exists = True  # Предполагаем, что таблица существует
        
        if not table_exists:
            print("Таблица system_settings не существует. Создаем таблицу...")
            Base.metadata.create_all(engine, tables=[SystemSettings.__table__])
            print("Таблица system_settings создана")
        
        # Проверяем, есть ли уже настройки в таблице
        try:
            existing_count = session.query(SystemSettings).count()
        except Exception as query_error:
            print(f"Ошибка при проверке настроек: {query_error}")
            print("Возможно, таблица еще не создана. Пропускаем инициализацию.")
            return
        
        if existing_count > 0:
            print(f"Таблица настроек уже содержит {existing_count} записей, пропускаем инициализацию")
            return
        
        # Настройки порогов семантического поиска
        # Значения выбраны эмпирически и могут быть настроены через UI
        # Логика: для коротких запросов порог ниже (embeddings менее информативны),
        # для длинных запросов порог выше (больше контекста для сравнения)
        default_settings = [
            {
                'key': 'semantic_threshold_1_word',
                'value': '0.25',
                'description': 'Порог схожести для запросов из 1 слова (рекомендуется: 0.2-0.3)',
                'category': 'semantic_search'
            },
            {
                'key': 'semantic_threshold_2_words',
                'value': '0.3',
                'description': 'Порог схожести для запросов из 2 слов (рекомендуется: 0.25-0.35)',
                'category': 'semantic_search'
            },
            {
                'key': 'semantic_threshold_3_words',
                'value': '0.35',
                'description': 'Порог схожести для запросов из 3 слов (рекомендуется: 0.3-0.4)',
                'category': 'semantic_search'
            },
            {
                'key': 'semantic_threshold_4_5_words',
                'value': '0.4',
                'description': 'Порог схожести для запросов из 4-5 слов (рекомендуется: 0.35-0.5)',
                'category': 'semantic_search'
            },
            {
                'key': 'semantic_threshold_6_plus_words',
                'value': '0.5',
                'description': 'Порог схожести для запросов из 6+ слов (рекомендуется: 0.4-0.6)',
                'category': 'semantic_search'
            },
            {
                'key': 'semantic_threshold_empty',
                'value': '0.2',
                'description': 'Порог схожести для пустых запросов или только стоп-слов (рекомендуется: 0.15-0.25)',
                'category': 'semantic_search'
            },
            {
                'key': 'keyword_match_min_ratio',
                'value': '0.5',
                'description': 'Минимальный процент совпадения слов для keyword matching (0.0-1.0)',
                'category': 'semantic_search'
            },
            {
                'key': 'keyword_boost_weight',
                'value': '0.1',
                'description': 'Вес буста от keyword matching к semantic similarity (0.0-1.0)',
                'category': 'semantic_search'
            }
        ]
        
        for setting_data in default_settings:
            setting = SystemSettings(**setting_data)
            session.add(setting)
        
        session.commit()
        print(f"Инициализировано {len(default_settings)} настроек по умолчанию")
    except Exception as e:
        session.rollback()
        print(f"Ошибка при инициализации настроек: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


def get_setting(key: str, default_value: str = None):
    """Получение значения настройки по ключу"""
    session = get_db_session()
    try:
        setting = session.query(SystemSettings).filter_by(key=key).first()
        if setting:
            return setting.value
        return default_value
    finally:
        session.close()


def get_setting_float(key: str, default_value: float = None):
    """Получение значения настройки как float"""
    value = get_setting(key)
    if value is None:
        return default_value
    try:
        return float(value)
    except (ValueError, TypeError):
        return default_value


def update_setting(key: str, value: str, description: str = None, category: str = 'general'):
    """Обновление или создание настройки"""
    session = get_db_session()
    try:
        setting = session.query(SystemSettings).filter_by(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
            if category:
                setting.category = category
        else:
            setting = SystemSettings(
                key=key,
                value=value,
                description=description or '',
                category=category
            )
            session.add(setting)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка при обновлении настройки {key}: {e}")
        return False
    finally:
        session.close()


def get_all_settings(category: str = None):
    """Получение всех настроек, опционально отфильтрованных по категории"""
    session = get_db_session()
    try:
        query = session.query(SystemSettings)
        if category:
            query = query.filter_by(category=category)
        settings = query.order_by(SystemSettings.category, SystemSettings.key).all()
        return [
            {
                'key': s.key,
                'value': s.value,
                'description': s.description,
                'category': s.category,
                'updated_at': s.updated_at.isoformat() if s.updated_at else None
            }
            for s in settings
        ]
    finally:
        session.close()


def get_db_session():
    """Получение сессии БД"""
    return SessionLocal()

