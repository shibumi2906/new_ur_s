from typing import Dict, Any
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

class ErrorFixToolInput(BaseModel):
    original_code: str = Field(description="Original code that failed")
    error_message: str = Field(description="Error message from execution")
    context: Dict[str, Any] = Field(description="Current page context")
    initial_prompt: str = Field(description="Initial prompt that generated the code")

class ErrorFixTool(BaseTool):
    name: str = "error_fixer"
    description: str = "Fixes errors in Selenium code based on error messages and context"
    args_schema = ErrorFixToolInput
    llm: ChatOpenAI = None
    
    def __init__(self):
        super().__init__()
        self.llm = ChatOpenAI(
            model=Config.LLM_MODEL,
            temperature=Config.LLM_TEMPERATURE,
            api_key=Config.OPENAI_API_KEY
        )
    
    def _run(self, original_code: str, error_message: str, context: Dict[str, Any], initial_prompt: str) -> Dict[str, Any]:
        """Генерирует исправленный код на основе ошибки"""
        try:
            prompt = f"""
            I have already completed "driver.get(url)" and my driver is open. Fix the error in this Selenium code:
            
            Original Code: {original_code}
            
            Error: {error_message}
            
            Page Context:
            URL: {context.get('current_url', '')}
            Title: {context.get('title', '')}
            Elements: {context.get('elements', [])}
            
            Initial Prompt: {initial_prompt}
            
            **Requirements:**
            - When correcting an error, take into account at what stage we are in accordance with the initial prompt and the current context of the error
            - Return only the corrected Python code inside ```python```
            - Consider my original prompt and the original variables in the code
            - Don't shorten the code
            - Always use only my already open "driver.get(url)"
            - Use universal methods of clicking on text that will work even if the text is inside nested spans and others (example: //button[.//*[contains(text(), "Create from template")])
            - Don't close my driver
            - Use explicit waits with WebDriverWait
            - Use CSS_SELECTOR when possible
            - Include proper error handling
            """
            
            response = self.llm.invoke(prompt)
            corrected_code = response.content
            
            return {
                "success": True,
                "corrected_code": corrected_code,
                "original_error": error_message,
                "message": "Error fix generated successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to generate error fix"
            } 