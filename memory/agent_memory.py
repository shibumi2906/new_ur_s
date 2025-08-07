from typing import List, Dict, Any
from pydantic import BaseModel
import time

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import AgentAction, UserResponse, PageContext, PageState
from config import Config

class AgentMemory(BaseModel):
    """Система памяти агента"""
    actions_history: List[AgentAction] = []
    user_responses: List[UserResponse] = []
    page_contexts: List[PageContext] = []
    error_history: List[str] = []
    current_state: PageState = PageState.LOGIN
    is_authenticated: bool = False
    
    def add_action(self, action: AgentAction):
        """Добавляет действие в историю"""
        self.actions_history.append(action)
        # Ограничиваем размер истории
        if len(self.actions_history) > Config.MAX_MEMORY_ITEMS:
            self.actions_history = self.actions_history[-Config.MAX_MEMORY_ITEMS:]
    
    def add_user_response(self, response: UserResponse):
        """Добавляет ответ пользователя"""
        self.user_responses.append(response)
    
    def add_page_context(self, context: PageContext):
        """Добавляет контекст страницы"""
        self.page_contexts.append(context)
        if len(self.page_contexts) > Config.MAX_MEMORY_ITEMS:
            self.page_contexts = self.page_contexts[-Config.MAX_MEMORY_ITEMS:]
    
    def add_error(self, error: str):
        """Добавляет ошибку в историю"""
        self.error_history.append(f"{time.time()}: {error}")
        if len(self.error_history) > 10:
            self.error_history = self.error_history[-10:]
    
    def get_recent_actions(self, count: int = 5) -> List[AgentAction]:
        """Возвращает последние действия"""
        return self.actions_history[-count:]
    
    def get_recent_errors(self, count: int = 3) -> List[str]:
        """Возвращает последние ошибки"""
        return self.error_history[-count:]
    
    def get_user_responses_summary(self) -> str:
        """Возвращает сводку ответов пользователя"""
        if not self.user_responses:
            return "No user responses yet."
        
        summary = "User responses:\n"
        for i, response in enumerate(self.user_responses, 1):
            summary += f"{i}. Q: {response.question[:100]}...\n"
            summary += f"   A: {response.answer[:100]}...\n"
        return summary
    
    def get_current_context_summary(self) -> Dict[str, Any]:
        """Возвращает сводку текущего контекста"""
        if not self.page_contexts:
            return {}
        
        current_context = self.page_contexts[-1]
        return {
            "current_url": current_context.current_url,
            "title": current_context.title,
            "element_count": len(current_context.elements),
            "state": self.current_state,
            "is_authenticated": self.is_authenticated,
            "recent_errors": self.get_recent_errors()
        }
    
    def update_state(self, new_state: PageState):
        """Обновляет текущее состояние"""
        self.current_state = new_state
    
    def mark_authenticated(self):
        """Отмечает, что пользователь авторизован"""
        self.is_authenticated = True
    
    def get_memory_summary(self) -> str:
        """Возвращает полную сводку памяти"""
        summary = f"""
        Current State: {self.current_state}
        Authenticated: {self.is_authenticated}
        Total Actions: {len(self.actions_history)}
        Total User Responses: {len(self.user_responses)}
        Recent Errors: {len(self.get_recent_errors())}
        
        Recent Actions:
        {chr(10).join([f"- {action.action_type}: {action.description[:50]}..." for action in self.get_recent_actions(3)])}
        
        User Responses Summary:
        {self.get_user_responses_summary()}
        """
        return summary 