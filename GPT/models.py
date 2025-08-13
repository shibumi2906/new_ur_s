from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from enum import Enum

class PageState(str, Enum):
    """Состояния страницы в процессе работы"""
    LOGIN = "login"
    PAGE_1 = "page_1"  # Главная страница после авторизации (Home)
    DOCUMENTS_PAGE = "documents_page"  # Страница Documents
    PRELIMINARY_DATA = "preliminary_data"
    CREATE_FROM_TEMPLATE = "create_from_template"
    TEMPLATE_SELECTION = "template_selection"
    DOCUMENT_FILLING = "document_filling"
    FILE_UPLOAD = "file_upload"
    COMPLETION = "completion"
    ERROR = "error"

# Флаги для состояний, требующих обязательного ввода пользователя
REQUIRES_USER_INPUT = {
    PageState.PRELIMINARY_DATA: True,
    PageState.TEMPLATE_SELECTION: True,
    PageState.DOCUMENT_FILLING: True
}

class ActionType(str, Enum):
    """Типы действий агента"""
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL_FORM = "fill_form"
    UPLOAD_FILE = "upload_file"
    ASK_QUESTION = "ask_question"
    WAIT = "wait"
    ERROR_FIX = "error_fix"

class PageElement(BaseModel):
    """Информация об элементе страницы"""
    tag: str
    text: str
    id: Optional[str] = None
    class_name: Optional[str] = None
    type: Optional[str] = None
    visible: bool = True
    xpath: Optional[str] = None

class PageContext(BaseModel):
    """Контекст текущей страницы"""
    current_url: str
    title: str
    elements: List[PageElement]
    body_html: str
    errors_history: List[str] = []

class UserResponse(BaseModel):
    """Ответ пользователя на вопрос"""
    question: str
    answer: str
    timestamp: float

class AgentAction(BaseModel):
    """Действие агента"""
    action_type: ActionType
    description: str
    code: str
    parameters: Dict[str, Any] = {}
    success: bool = False
    error_message: Optional[str] = None

class AgentState(BaseModel):
    """Состояние агента"""
    current_page_state: PageState
    page_context: PageContext
    user_responses: List[UserResponse] = []
    action_history: List[AgentAction] = []
    error_count: int = 0
    is_authenticated: bool = False 