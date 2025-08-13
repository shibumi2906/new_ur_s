import logging
import os
from datetime import datetime
from typing import Optional

class AgentLogger:
    """Кастомный логгер для агента"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Создаем папку для логов если её нет
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        # Файловый обработчик
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(f'logs/agent_{timestamp}.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # Консольный обработчик
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        
        # Форматтер
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Добавляем обработчики
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def debug(self, message: str):
        self.logger.debug(message)
    
    def info(self, message: str):
        self.logger.info(message)
    
    def warning(self, message: str):
        self.logger.warning(message)
    
    def error(self, message: str):
        self.logger.error(message)
    
    def critical(self, message: str):
        self.logger.critical(message)
    
    def step(self, step_name: str, details: str = ""):
        message = f"STEP: {step_name}"
        if details:
            message += f" - {details}"
        self.logger.info(message)
    
    def success(self, message: str):
        self.logger.info(f"SUCCESS: {message}")
    
    def selenium_action(self, action: str, details: str = ""):
        message = f"SELENIUM: {action}"
        if details:
            message += f" - {details}"
        self.logger.info(message)
    
    def llm_request(self, request_type: str, content: str = ""):
        message = f"LLM REQUEST ({request_type})"
        if content:
            message += f" - {content}"
        self.logger.info(message)
    
    def llm_response(self, response_type: str, content: str = ""):
        message = f"LLM RESPONSE ({response_type})"
        if content:
            message += f" - {content}"
        self.logger.info(message)
    
    def user_interaction(self, interaction_type: str, details: str = ""):
        message = f"USER INTERACTION: {interaction_type}"
        if details:
            message += f" - {details}"
        self.logger.info(message)
    
    def state_change(self, old_state: str, new_state: str):
        self.logger.info(f"STATE CHANGE: {old_state} -> {new_state}")

def get_logger(name: str) -> AgentLogger:
    """Возвращает экземпляр логгера"""
    return AgentLogger(name) 