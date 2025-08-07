import time
from typing import Dict, Any, List
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import UserResponse

class QuestionToolInput(BaseModel):
    questions: str = Field(description="Questions to ask the user")
    context: Dict[str, Any] = Field(description="Current context for questions")

class QuestionTool(BaseTool):
    name: str = "question_asker"
    description: str = "Asks questions to the user and collects responses"
    args_schema = QuestionToolInput
    user_responses: List[UserResponse] = []
    
    def __init__(self):
        super().__init__()
        self.user_responses = []
    
    def _run(self, questions: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Задает вопросы пользователю и собирает ответы"""
        try:
            # Извлечение вопросов из блока ```questions
            import re
            question_block = re.search(r'```questions(.*?)```', questions, re.DOTALL)
            if question_block:
                questions_text = question_block.group(1).strip()
            else:
                questions_text = questions.strip()
            
            # Вывод вопросов пользователю
            print("\n" + "="*50)
            print("🤖 AI Agent needs information:")
            print("="*50)
            print(questions_text)
            print("="*50)
            
            # Получение ответа от пользователя
            user_answer = input("Your answer: ").strip()
            
            # Сохранение ответа
            response = UserResponse(
                question=questions_text,
                answer=user_answer,
                timestamp=time.time()
            )
            self.user_responses.append(response)
            
            return {
                "success": True,
                "question": questions_text,
                "answer": user_answer,
                "message": "User response collected successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to collect user response"
            }
    
    def get_user_responses(self) -> List[UserResponse]:
        """Возвращает все ответы пользователя"""
        return self.user_responses
    
    def get_last_response(self) -> UserResponse:
        """Возвращает последний ответ пользователя"""
        return self.user_responses[-1] if self.user_responses else None 