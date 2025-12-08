"""Flask веб-приложение для управления обработкой новостей"""
from flask import Flask, render_template, request, jsonify
from threading import Thread
import uuid
import time
from datetime import datetime
from crew import NewsProcessingCrew
from config import Config
from models import NewsArticle, get_db_session, init_db, engine

app = Flask(__name__)
app.secret_key = Config.FLASK_SECRET_KEY

# Хранилище статусов задач
tasks_status = {}


@app.errorhandler(500)
def internal_error(error):
    """Обработчик внутренних ошибок - всегда возвращает JSON"""
    return jsonify({
        'success': False,
        'error': 'Внутренняя ошибка сервера'
    }), 500


@app.errorhandler(404)
def not_found(error):
    """Обработчик 404 - всегда возвращает JSON"""
    return jsonify({
        'success': False,
        'error': 'Ресурс не найден'
    }), 404


class ProgressTracker:
    """Класс для отслеживания прогресса выполнения"""
    
    def __init__(self, task_id):
        self.task_id = task_id
        self.status = 'pending'  # pending, running, completed, error
        self.current_step = 0
        self.total_steps = 3
        self.steps = [
            {'name': 'Сбор новостей из RSS каналов', 'status': 'pending', 'progress': 0, 'message': ''},
            {'name': 'Дедупликация статей', 'status': 'pending', 'progress': 0, 'message': ''},
            {'name': 'Классификация по релевантности', 'status': 'pending', 'progress': 0, 'message': ''}
        ]
        self.error_message = ''
        self.statistics = {}
    
    def update_step(self, step_index, status, progress=0, message=''):
        """Обновление статуса шага"""
        if 0 <= step_index < len(self.steps):
            self.steps[step_index]['status'] = status
            self.steps[step_index]['progress'] = progress
            self.steps[step_index]['message'] = message
            self.current_step = step_index
    
    def to_dict(self):
        """Преобразование в словарь для JSON"""
        return {
            'task_id': self.task_id,
            'status': self.status,
            'current_step': self.current_step,
            'total_steps': self.total_steps,
            'steps': self.steps,
            'error_message': self.error_message,
            'statistics': self.statistics
        }


def process_news_with_progress(task_id, feed_urls, criteria):
    """Обработка новостей с отслеживанием прогресса"""
    tracker = tasks_status[task_id]
    
    # Импорты в начале функции
    from agents.rss_collector import collect_rss_news
    from agents.deduplicator import find_duplicates, mark_duplicates
    from agents.classifier import classify_articles
    
    try:
        tracker.status = 'running'
        
        # Инициализация БД
        init_db()
        crew = NewsProcessingCrew()
        
        # Шаг 1: Сбор новостей
        tracker.update_step(0, 'running', 0, 'Начало сбора новостей...')
        
        articles = collect_rss_news(feed_urls)
        tracker.update_step(0, 'running', 50, f'Собрано {len(articles)} статей')
        
        if articles:
            session = get_db_session()
            try:
                for article in articles:
                    session.add(article)
                session.commit()
                tracker.update_step(0, 'completed', 100, f'Сохранено {len(articles)} статей')
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()
        else:
            tracker.update_step(0, 'completed', 100, 'Новых новостей не найдено')
        
        # Получение необработанных статей
        session = get_db_session()
        try:
            unprocessed_articles = session.query(NewsArticle).filter(
                NewsArticle.is_duplicate == False,
                NewsArticle.relevance_score == None
            ).all()
        finally:
            session.close()
        
        if not unprocessed_articles:
            tracker.status = 'completed'
            tracker.statistics = {'message': 'Нет статей для обработки'}
            return
        
        # Шаг 2: Дедупликация
        tracker.update_step(1, 'running', 0, f'Анализ {len(unprocessed_articles)} статей...')
        
        duplicates = find_duplicates(unprocessed_articles, Config.SIMILARITY_THRESHOLD)
        tracker.update_step(1, 'running', 50, f'Найдено {len(duplicates)} дубликатов')
        
        if duplicates:
            mark_duplicates(unprocessed_articles, duplicates)
            tracker.update_step(1, 'completed', 100, f'Помечено {len(duplicates)} дубликатов')
        else:
            tracker.update_step(1, 'completed', 100, 'Дубликаты не найдены')
        
        # Получение уникальных статей
        session = get_db_session()
        try:
            unique_articles = session.query(NewsArticle).filter(
                NewsArticle.is_duplicate == False,
                NewsArticle.relevance_score == None
            ).all()
        finally:
            session.close()
        
        # Шаг 3: Классификация
        if not criteria:
            tracker.update_step(2, 'error', 0, 'Критерий отбора не указан')
            tracker.status = 'error'
            tracker.error_message = 'Критерий отбора не указан'
            return
        
        print(f"Критерий отбора: {criteria}")
        tracker.update_step(2, 'running', 0, f'Классификация {len(unique_articles)} статей по критерию: {criteria[:50]}...')
        
        total = len(unique_articles)
        for i, article in enumerate(unique_articles):
            classify_articles([article], criteria)
            progress = int((i + 1) / total * 100)
            tracker.update_step(2, 'running', progress, f'Обработано {i + 1} из {total} статей')
        
        tracker.update_step(2, 'completed', 100, f'Классифицировано {total} статей')
        
        # Итоговая статистика
        session = get_db_session()
        try:
            total_count = session.query(NewsArticle).count()
            relevant = session.query(NewsArticle).filter(
                NewsArticle.is_relevant == True,
                NewsArticle.is_duplicate == False
            ).count()
            duplicates_count = session.query(NewsArticle).filter(
                NewsArticle.is_duplicate == True
            ).count()
            
            tracker.statistics = {
                'total': total_count,
                'relevant': relevant,
                'duplicates': duplicates_count,
                'unique_non_relevant': total_count - relevant - duplicates_count
            }
        finally:
            session.close()
        
        tracker.status = 'completed'
        
    except Exception as e:
        tracker.status = 'error'
        tracker.error_message = str(e)
        import traceback
        print(f"Ошибка при обработке: {traceback.format_exc()}")


@app.route('/')
def index():
    """Главная страница с формой"""
    return render_template('index.html')


@app.route('/api/start', methods=['POST'])
def start_processing():
    """Запуск обработки новостей"""
    data = request.json
    
    feed_urls = [url.strip() for url in data.get('rss_feeds', '').split('\n') if url.strip()]
    criteria = data.get('criteria', '').strip()
    
    if not feed_urls:
        return jsonify({'error': 'Не указаны RSS каналы'}), 400
    
    if not criteria:
        return jsonify({'error': 'Не указан критерий отбора'}), 400
    
    # Создание задачи
    task_id = str(uuid.uuid4())
    tracker = ProgressTracker(task_id)
    tasks_status[task_id] = tracker
    
    # Запуск обработки в отдельном потоке
    thread = Thread(target=process_news_with_progress, args=(task_id, feed_urls, criteria))
    thread.daemon = True
    thread.start()
    
    return jsonify({'task_id': task_id})


@app.route('/api/status/<task_id>')
def get_status(task_id):
    """Получение статуса задачи"""
    if task_id not in tasks_status:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    return jsonify(tasks_status[task_id].to_dict())


@app.route('/api/results')
def get_results():
    """Получение результатов обработки"""
    session = get_db_session()
    try:
        # Получаем уникальные статьи (не дубликаты), отсортированные по дате
        articles = session.query(NewsArticle).filter(
            NewsArticle.is_duplicate == False
        ).order_by(NewsArticle.published_at.desc() if NewsArticle.published_at else NewsArticle.collected_at.desc()).all()
        
        results = []
        for article in articles:
            results.append({
                'id': article.id,
                'title': article.title,
                'content': article.content or '',
                'link': article.link,
                'source': article.source or 'Неизвестный источник',
                'published_at': article.published_at.isoformat() if article.published_at else None,
                'relevance_score': article.relevance_score,
                'is_relevant': article.is_relevant,
                'classification_reason': article.classification_reason or ''
            })
        
        return jsonify({'articles': results})
    finally:
        session.close()


@app.route('/api/clear-db', methods=['POST'])
def clear_database():
    """Очистка базы данных"""
    session = None
    try:
        from sqlalchemy import inspect
        
        # Проверка существования таблицы
        inspector = inspect(engine)
        if 'news_articles' not in inspector.get_table_names():
            return jsonify({
                'success': True,
                'message': 'База данных уже пуста (таблица не существует)'
            })
        
        session = get_db_session()
        
        # Подсчет статей перед удалением
        count = session.query(NewsArticle).count()
        
        # Удаление всех статей
        if count > 0:
            session.query(NewsArticle).delete()
            session.commit()
        
        return jsonify({
            'success': True,
            'message': f'База данных очищена. Удалено статей: {count}'
        })
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"Ошибка при очистке БД: {error_msg}")
        traceback.print_exc()
        
        if session:
            try:
                session.rollback()
            except Exception as rollback_error:
                print(f"Ошибка при rollback: {rollback_error}")
        
        # Всегда возвращаем JSON, даже при ошибке
        try:
            return jsonify({
                'success': False,
                'error': error_msg
            }), 500
        except Exception as json_error:
            # Если даже jsonify не работает, возвращаем простой текст
            from flask import Response
            return Response(
                f'{{"success": false, "error": "{error_msg}"}}',
                mimetype='application/json',
                status=500
            )
    finally:
        if session:
            try:
                session.close()
            except Exception as close_error:
                print(f"Ошибка при закрытии сессии: {close_error}")


if __name__ == '__main__':
    init_db()
    app.run(
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG
    )

