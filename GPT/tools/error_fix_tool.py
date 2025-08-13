from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

class ErrorFixTool(BaseModel):
    """Инструмент для исправления ошибок в Selenium коде"""
    
    name: str = "error_fix_tool"
    description: str = "Исправляет ошибки в Selenium коде на основе анализа ошибки и контекста страницы"
    llm: ChatOpenAI = Field(default_factory=lambda: ChatOpenAI(
        model=Config.LLM_MODEL,
        temperature=0.3,
        api_key=Config.OPENAI_API_KEY
    ))
    
    def _run(self, original_code: str, error_message: str, context: Dict[str, Any], initial_prompt: str) -> Dict[str, Any]:
        """Исправляет ошибку в коде"""
        try:
            # Генерируем промпт для исправления ошибки
            fix_prompt = self._generate_fix_prompt(original_code, error_message, context, initial_prompt)
            
            # Получаем исправленный код от LLM
            messages = [
                SystemMessage(content="You are an expert Selenium automation engineer. Fix the error in the provided code."),
                HumanMessage(content=fix_prompt)
            ]
            
            response = self.llm.invoke(messages)
            corrected_code = self._extract_code(response.content)
            
            if corrected_code:
                return {
                    "success": True,
                    "corrected_code": corrected_code,
                    "explanation": response.content
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to extract corrected code from LLM response"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Error fix failed: {str(e)}"
            }
    
    def _generate_fix_prompt(self, original_code: str, error_message: str, context: Dict[str, Any], initial_prompt: str) -> str:
        """Генерирует промпт для исправления ошибки"""
        
        # Определяем тип ошибки и добавляем специальные инструкции
        special_instructions = ""
        if "ElementClickInterceptedException" in error_message:
            special_instructions = """
        **SPECIAL INSTRUCTIONS FOR ElementClickInterceptedException:**
        - The element is being intercepted by another element (usually a form or overlay)
        - Use JavaScript to scroll to the element: driver.execute_script("arguments[0].scrollIntoView(true);", element)
        - Add a pause after scrolling: time.sleep(1)
        - Use JavaScript click instead of regular click: driver.execute_script("arguments[0].click();", element)
        - If still not working, try to find the parent element and click on it
        - For dropdowns, try to find the input field inside and send keys directly
        - Import time module: import time
        """
        elif "TimeoutException" in error_message:
            special_instructions = """
        **SPECIAL INSTRUCTIONS FOR TimeoutException:**
        - Increase wait time to 15-20 seconds
        - Try different selectors (XPath and CSS)
        - Check if element is in iframe
        - Wait for page to fully load
        """
        elif "NoSuchElementException" in error_message:
            special_instructions = """
        **SPECIAL INSTRUCTIONS FOR NoSuchElementException:**
        - Try multiple different selectors
        - Check if element is dynamically loaded
        - Wait for element to be present
        - Try parent/child element combinations
        """
        
        return f"""
        I have already completed "driver.get(url)" and my driver is open. Fix the error in this Selenium code:
        
        Original Code: {original_code}
        
        Error: {error_message}
        
        Page Context:
        URL: {context.get('current_url', '')}
        Title: {context.get('title', '')}
        HTML: {context.get('body_html', '')[:2000]}
        
        Initial Prompt: {initial_prompt}
        
        {special_instructions}
        
        **CRITICAL REQUIREMENTS:**
        - The error shows that the XPath or CSS selector is not working
        - You MUST try different XPath patterns and CSS selectors for finding elements
        - Use these alternative patterns in order:
          1. //a[contains(text(), "Text")]
          2. //span[contains(text(), "Text")]
          3. //div[contains(text(), "Text")]
          4. //button[contains(text(), "Text")]
          5. //*[contains(text(), "Text")]
          6. CSS selectors like "button:contains('Text')"
          7. //*[contains(@class, "class-name")]
          8. //*[contains(@id, "id-name")]
        
        **Error Fix Strategy:**
        - Try multiple XPath patterns in a loop
        - Use try-except for each pattern attempt
        - If one pattern fails, try the next one
        - Return only the corrected Python code inside ```python```
        - Don't shorten the code
        - Always use only my already open "driver.get(url)"
        - Use explicit waits with WebDriverWait (15-20 seconds)
        - Include proper error handling
        - Import necessary modules: from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException
        - Import time module: import time
        """
    
    def _extract_code(self, response: str) -> str:
        """Извлекает код из ответа LLM"""
        if '```python' in response:
            start = response.find('```python') + len('```python')
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        # Если нет блоков кода, возвращаем весь ответ
        return response.strip() 