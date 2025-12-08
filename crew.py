"""Оркестрация CrewAI агентов для обработки новостей"""
from crewai import Crew, Process
from agents.rss_collector import create_rss_collector_agent, collect_rss_news
from agents.deduplicator import create_deduplicator_agent, find_duplicates, mark_duplicates
from agents.classifier import create_classifier_agent, classify_articles
from config import Config
from models import NewsArticle, get_db_session, init_db
from typing import List


class NewsProcessingCrew:
    """Crew для обработки новостей"""
    
    def __init__(self):
        """Инициализация crew"""
        init_db()
        
        self.rss_collector = create_rss_collector_agent()
        self.deduplicator = create_deduplicator_agent()
        self.classifier = create_classifier_agent()
    
    def process_news(self, feed_urls: List[str] = None, criteria: str = None):
        """Основной процесс обработки новостей"""
        if feed_urls is None:
            feed_urls = Config.RSS_FEEDS
        
        if criteria is None:
            criteria = Config.SELECTION_CRITERIA
        
        if not feed_urls:
            print("Ошибка: не указаны RSS каналы")
            return
        
        if not criteria:
            print("Ошибка: не указан критерий отбора")
            return
        
        print(f"Начало обработки новостей из {len(feed_urls)} каналов...")
        print(f"Критерий отбора: {criteria}")
        
        # Шаг 1: Сбор новостей
        print("\n=== Шаг 1: Сбор новостей из RSS каналов ===")
        articles = collect_rss_news(feed_urls)
        
        if articles:
            print(f"Собрано {len(articles)} новых статей")
            
            # Сохранение статей в БД
            session = get_db_session()
            try:
                for article in articles:
                    session.add(article)
                session.commit()
                print(f"Сохранено {len(articles)} статей в базу данных")
            except Exception as e:
                session.rollback()
                print(f"Ошибка при сохранении статей: {e}")
            finally:
                session.close()
        else:
            print("Новых новостей не найдено")
        
        # Получение всех необработанных статей
        session = get_db_session()
        try:
            unprocessed_articles = session.query(NewsArticle).filter(
                NewsArticle.is_duplicate == False,
                NewsArticle.relevance_score == None
            ).all()
        finally:
            session.close()
        
        if not unprocessed_articles:
            print("Нет статей для обработки")
            return
        
        # Шаг 2: Дедупликация
        print(f"\n=== Шаг 2: Дедупликация {len(unprocessed_articles)} статей ===")
        duplicates = find_duplicates(unprocessed_articles, Config.SIMILARITY_THRESHOLD)
        
        if duplicates:
            mark_duplicates(unprocessed_articles, duplicates)
            print(f"Найдено {len(duplicates)} дубликатов")
        
        # Получение уникальных статей для классификации
        session = get_db_session()
        try:
            unique_articles = session.query(NewsArticle).filter(
                NewsArticle.is_duplicate == False,
                NewsArticle.relevance_score == None
            ).all()
        finally:
            session.close()
        
        # Шаг 3: Классификация
        print(f"\n=== Шаг 3: Классификация {len(unique_articles)} уникальных статей ===")
        classify_articles(unique_articles, criteria)
        
        # Итоговая статистика
        session = get_db_session()
        try:
            total = session.query(NewsArticle).count()
            relevant = session.query(NewsArticle).filter(
                NewsArticle.is_relevant == True,
                NewsArticle.is_duplicate == False
            ).count()
            duplicates_count = session.query(NewsArticle).filter(
                NewsArticle.is_duplicate == True
            ).count()
        finally:
            session.close()
        
        print(f"\n=== Итоговая статистика ===")
        print(f"Всего статей: {total}")
        print(f"Релевантных: {relevant}")
        print(f"Дубликатов: {duplicates_count}")
        print(f"Уникальных нерелевантных: {total - relevant - duplicates_count}")


def run_crew():
    """Запуск crew"""
    crew = NewsProcessingCrew()
    crew.process_news()

