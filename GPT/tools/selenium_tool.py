import ast
import re
import time
from typing import Dict, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import PageContext, AgentAction, ActionType

class SeleniumToolInput(BaseModel):
    code: str = Field(description="Python Selenium code to execute")
    context: Dict[str, Any] = Field(description="Current page context")

class SeleniumTool(BaseTool):
    name: str = "selenium_executor"
    description: str = "Executes Selenium WebDriver code for web automation"
    args_schema = SeleniumToolInput
    driver: webdriver.Chrome = None
    error_history: list = []
    
    def __init__(self, driver: webdriver.Chrome):
        super().__init__()
        self.driver = driver
        self.error_history = []
    
    def _run(self, code: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Выполняет Selenium код с обработкой ошибок"""
        try:
            # Извлечение кода из блока ```python
            code_block = re.search(r'```python(.*?)```', code, re.DOTALL)
            if code_block:
                code = code_block.group(1).strip()
            else:
                code = code.strip()

            # Удаление лишних комментариев и пустых строк
            code = '\n'.join([line for line in code.split('\n') 
                            if not line.strip().startswith('#') and line.strip()])
            
            # Проверка синтаксиса
            ast.parse(code)
            
            # Подготовка глобальных переменных для выполнения
            exec_globals = {
                'driver': self.driver,
                'By': By,
                'WebDriverWait': WebDriverWait,
                'EC': EC,
                'time': time,
                'print': print
            }
            
            # Добавляем credentials из контекста, если они есть
            if 'credentials' in context:
                exec_globals['credentials'] = context['credentials']
            # Добавляем user_data из контекста, если оно есть
            if 'user_data' in context:
                exec_globals['user_data'] = context['user_data']
            
            # Логируем код перед выполнением
            print(f"🔍 EXECUTING SELENIUM CODE:")
            print(f"🔍 CODE LENGTH: {len(code)}")
            print(f"🔍 CODE: {code}")
            
            # Перехватываем вывод print для проверки ошибок
            import io
            import sys
            old_stdout = sys.stdout
            captured_output = io.StringIO()
            sys.stdout = captured_output
            
            try:
                # Выполнение кода
                exec(code, exec_globals)
            finally:
                # Восстанавливаем stdout
                sys.stdout = old_stdout
                captured_output.seek(0)
                output = captured_output.read()
                print(f"🔍 CAPTURED OUTPUT: {output}")
                
                # Проверяем, есть ли в выводе сообщения об ошибках
                if any(error_keyword in output for error_keyword in [
                    "An error occurred:", "TimeoutException", "NoSuchElementException",
                    "ElementNotInteractableException", "StaleElementReferenceException",
                    "WebDriverException", "InvalidSelectorException"
                ]):
                    print(f"🔍 ERROR DETECTED IN OUTPUT")
                    return {
                        "success": False,
                        "error": f"Code executed but encountered an error: {output.strip()}",
                        "error_type": "execution"
                    }
            
            # Проверяем, не было ли ошибок в коде
            # Если код выполнился без исключений, считаем успешным
            print(f"🔍 SELENIUM CODE EXECUTED SUCCESSFULLY")
            
            return {
                "success": True,
                "message": "Code executed successfully",
                "code": code
            }
            
        except SyntaxError as se:
            error_msg = f"SyntaxError: {str(se)}"
            self.error_history.append(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "syntax"
            }
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.error_history.append(error_msg)
            # Логируем ошибку для отладки
            print(f"Selenium execution error: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "error_type": "execution"
            }
    
    def get_error_history(self) -> list:
        """Возвращает историю ошибок"""
        return self.error_history[-5:]  # Последние 5 ошибок 