"""Агент для дедупликации новостей"""
from crewai import Agent, Task
from langchain_openai import ChatOpenAI
from config import Config
from models import NewsArticle, get_db_session
from agents.llm_utils import create_llm
from typing import List
import difflib


def calculate_similarity(text1: str, text2: str) -> float:
    """Вычисление схожести двух текстов"""
    text1 = text1.lower().strip()
    text2 = text2.lower().strip()
    
    if not text1 or not text2:
        return 0.0
    
    # Используем SequenceMatcher для вычисления схожести
    similarity = difflib.SequenceMatcher(None, text1, text2).ratio()
    return similarity


def find_duplicates(articles: List[NewsArticle], threshold: float = None, search_history_id: int = None) -> dict:
    """Поиск дубликатов среди статей (в рамках одного запроса)"""
    if threshold is None:
        threshold = Config.SIMILARITY_THRESHOLD
    
    duplicates = {}
    session = get_db_session()
    
    try:
        # Проверка по хешу (точные дубликаты) - только в рамках одного запроса
        for article in articles:
            if not article.id or not article.content_hash:
                continue
            
            query = session.query(NewsArticle).filter(
                NewsArticle.content_hash == article.content_hash,
                NewsArticle.id != article.id
            )
            
            # Если указан search_history_id, ищем дубликаты только в этом запросе
            if search_history_id:
                query = query.filter(NewsArticle.search_history_id == search_history_id)
            
            existing = query.first()
            
            if existing:
                duplicates[article.id] = existing.id
                continue
        
        # Проверка по схожести текста
        for i, article1 in enumerate(articles):
            if not article1.id or article1.id in duplicates:
                continue
                
            for article2 in articles[i+1:]:
                if not article2.id or article2.id in duplicates:
                    continue
                
                # Сравнение заголовков и содержимого
                title_sim = calculate_similarity(article1.title, article2.title)
                content_sim = calculate_similarity(
                    article1.content or '', 
                    article2.content or ''
                )
                
                # Если схожесть высокая, считаем дубликатом
                if title_sim >= threshold or (title_sim >= 0.7 and content_sim >= threshold):
                    # Берем более раннюю статью как оригинал
                    if article1.published_at and article2.published_at:
                        if article1.published_at < article2.published_at:
                            duplicates[article2.id] = article1.id
                        else:
                            duplicates[article1.id] = article2.id
                    else:
                        duplicates[article2.id] = article1.id
                    
    finally:
        session.close()
    
    return duplicates


def mark_duplicates(articles: List[NewsArticle], duplicates: dict):
    """Пометка дубликатов в базе данных"""
    session = get_db_session()
    
    try:
        for article_id, original_id in duplicates.items():
            article = session.query(NewsArticle).filter_by(id=article_id).first()
            if article:
                article.is_duplicate = True
                article.duplicate_of = original_id
        
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Ошибка при пометке дубликатов: {e}")
    finally:
        session.close()


def create_deduplicator_agent() -> Agent:
    """Создание агента для дедупликации"""
    llm = create_llm()
    
    return Agent(
        role='News Deduplicator',
        goal='Найти и пометить дубликаты новостей, оставив только уникальные статьи',
        backstory='Ты эксперт по анализу текстов и поиску дубликатов. '
                 'Ты умеешь определять схожие новости даже если они немного отличаются формулировками.',
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

