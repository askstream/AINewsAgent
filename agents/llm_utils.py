"""Утилиты для работы с LLM"""
from langchain_openai import ChatOpenAI
from config import Config


def create_llm():
    """Создание LLM с правильной обработкой base_url (использует настройки из Config)"""
    return create_llm_with_settings(Config.LLM_MODEL, Config.LLM_TEMPERATURE)


def create_llm_with_settings(llm_model: str = None, llm_temperature: float = None):
    """Создание LLM с указанными настройками"""
    if llm_model is None:
        llm_model = Config.LLM_MODEL
    if llm_temperature is None:
        llm_temperature = Config.LLM_TEMPERATURE
    
    llm_params = {
        'model': llm_model,
        'temperature': llm_temperature,
        'api_key': Config.OPENAI_API_KEY
    }
    
    # Правильная обработка base_url для ChatOpenAI
    if Config.OPENAI_API_BASE:
        base_url = Config.OPENAI_API_BASE.rstrip('/')
        
        # Для ChatOpenAI из langchain-openai base_url должен указывать на базовый URL API
        # без /v1, так как библиотека сама добавляет /v1/chat/completions
        # Убираем /v1 если он есть в конце URL (может быть /openai/v1 или просто /v1)
        if base_url.endswith('/v1'):
            # Убираем /v1 с конца
            base_url = base_url[:-3].rstrip('/')
        
        llm_params['base_url'] = base_url
        print(f"Используется base_url: {base_url} (исходный: {Config.OPENAI_API_BASE})")
    
    return ChatOpenAI(**llm_params)

