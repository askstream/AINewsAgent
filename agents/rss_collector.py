"""Агент для сбора новостей из RSS каналов"""
import feedparser
from datetime import datetime
from crewai import Agent
from langchain_openai import ChatOpenAI
from config import Config
from models import NewsArticle, RSSFeed, get_db_session
from agents.llm_utils import create_llm
import hashlib


def get_content_hash(title: str, content: str) -> str:
    """Генерация хеша для проверки дубликатов"""
    text = f"{title}{content or ''}".strip().lower()
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def collect_rss_news(feed_urls: list) -> list:
    """Сбор новостей из RSS каналов"""
    all_articles = []
    session = get_db_session()
    
    try:
        for feed_url in feed_urls:
            if not feed_url.strip():
                continue
                
            try:
                feed = feedparser.parse(feed_url.strip())
                
                for entry in feed.entries:
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    content = entry.get('summary', '') or entry.get('description', '')
                    
                    # Парсинг даты публикации
                    published_at = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published_at = datetime(*entry.published_parsed[:6])
                    
                    # Проверка на существование статьи
                    existing = session.query(NewsArticle).filter_by(link=link).first()
                    if existing:
                        continue
                    
                    content_hash = get_content_hash(title, content)
                    
                    article = NewsArticle(
                        title=title,
                        content=content,
                        link=link,
                        source=feed.feed.get('title', feed_url),
                        published_at=published_at,
                        content_hash=content_hash
                    )
                    all_articles.append(article)
                    
            except Exception as e:
                print(f"Ошибка при парсинге RSS канала {feed_url}: {e}")
                continue
                
    finally:
        session.close()
    
    return all_articles


def create_rss_collector_agent() -> Agent:
    """Создание агента для сбора RSS новостей"""
    llm = create_llm()
    
    return Agent(
        role='RSS Collector',
        goal='Собрать все новости из указанных RSS каналов и сохранить их в базу данных',
        backstory='Ты опытный специалист по сбору новостей из различных RSS источников. '
                 'Ты умеешь эффективно парсить RSS каналы и извлекать актуальную информацию.',
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

