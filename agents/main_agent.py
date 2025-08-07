import time
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
from models import PageContext, PageState, AgentAction, ActionType, UserResponse
from memory.agent_memory import AgentMemory
from .navigator_agent import NavigatorAgent
from .prompt_generator_agent import PromptGeneratorAgent
from tools.selenium_tool import SeleniumTool
from tools.page_context_tool import PageContextTool
from tools.question_tool import QuestionTool
from tools.error_fix_tool import ErrorFixTool
from logger import get_logger

class MainAgent:
    """Основной агент, координирующий всю работу"""
    
    def __init__(self, driver, credentials: Dict[str, str]):
        self.driver = driver
        self.credentials = credentials
        
        # Инициализация логгера
        self.logger = get_logger("MainAgent")
        self.logger.info("Initializing MainAgent")
        
        # Инициализация LLM
        self.logger.step("LLM Initialization", f"Model: {Config.LLM_MODEL}")
        self.llm = ChatOpenAI(
            model=Config.LLM_MODEL,
            temperature=Config.LLM_TEMPERATURE,
            api_key=Config.OPENAI_API_KEY
        )
        
        # Инициализация памяти
        self.logger.step("Memory Initialization")
        self.memory = AgentMemory()
        
        # Инициализация агентов
        self.logger.step("Agent Initialization")
        self.navigator = NavigatorAgent()
        self.prompt_generator = PromptGeneratorAgent()
        
        # Инициализация инструментов
        self.logger.step("Tools Initialization")
        self.selenium_tool = SeleniumTool(driver)
        self.page_context_tool = PageContextTool()
        self.question_tool = QuestionTool()
        self.error_fix_tool = ErrorFixTool()
        
        # Состояние
        self.is_running = False
        self.max_retries = Config.MAX_RETRIES
        self.logger.success("MainAgent initialized successfully")
    
    def run_workflow(self, url: str) -> bool:
        """Основной рабочий процесс"""
        self.logger.step("Workflow Start", f"URL: {url}")
        self.is_running = True
        
        try:
            # Открываем страницу
            self.logger.selenium_action("Opening URL", url)
            self.driver.get(url)
            self.logger.success(f"Opened URL: {url}")
            
            # Ждем загрузки страницы (как в оригинальном файле)
            import time
            time.sleep(3)  # Увеличиваем время ожидания
            
            # Проверяем, что страница загрузилась правильно
            current_url = self.driver.current_url
            if current_url == "data:," or not current_url or current_url.startswith("data:"):
                self.logger.error(f"Page failed to load. Current URL: {current_url}")
                return False
            
            # Если попали на /projects, перенаправляем на /home
            if "/projects" in current_url:
                self.logger.info("Redirecting from /projects to /home")
                self.driver.get("https://app.conneto.com/home")
                time.sleep(2)
                current_url = self.driver.current_url
            
            self.logger.success(f"Page loaded successfully: {current_url}")
            
            # Запрашиваем учетные данные (как в оригинальном файле)
            self.logger.step("Requesting Credentials")
            self._request_credentials()
            
            # Основной цикл работы
            iteration = 0
            while self.is_running:
                iteration += 1
                self.logger.step(f"Workflow Iteration {iteration}")
                
                # 1. Анализируем текущую страницу
                self.logger.step("Page Analysis")
                context = self._analyze_page()
                if not context:
                    self.logger.error("Failed to analyze page")
                    return False
                
                # 2. Определяем состояние
                self.logger.step("State Determination")
                navigation_result = self.navigator.determine_page_state(
                    context, 
                    self.memory.get_user_responses_summary()
                )
                
                current_state = navigation_result["state"]
                old_state = self.memory.current_state
                self.memory.update_state(current_state)
                
                if old_state != current_state:
                    self.logger.state_change(str(old_state), str(current_state))
                
                self.logger.info(f"Current state: {current_state}")
                self.logger.info(f"Analysis: {navigation_result['analysis'][:100]}...")
                
                # 3. Проверяем завершение
                if current_state == PageState.COMPLETION:
                    self.logger.success("Document creation completed successfully!")
                    return True
                
                # 4. Генерируем промпт
                self.logger.step("Prompt Generation")
                prompt = self.prompt_generator.generate_action_prompt(
                    context=context,
                    state=current_state,
                    memory_summary=self.memory.get_memory_summary(),
                    user_responses=self.memory.get_user_responses_summary()
                )
                
                # 5. Генерируем код
                self.logger.step("Code Generation")
                ai_response = self._generate_code(prompt)
                
                # 6. Проверяем, нужны ли вопросы
                if '```questions' in ai_response:
                    self.logger.step("User Questions Required")
                    self._handle_questions(ai_response, context)
                else:
                    # 7. Выполняем код
                    self.logger.step("Code Execution")
                    success = self._execute_code(ai_response, context, prompt)
                    if not success:
                        self.logger.error("Failed to execute code after retries")
                        return False
                
                # Небольшая пауза между итерациями
                time.sleep(1)
                
        except Exception as e:
            self.logger.critical(f"Critical error: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        finally:
            self.is_running = False
            self.logger.info("Workflow finished")
    
    def _analyze_page(self) -> PageContext:
        """Анализирует текущую страницу"""
        try:
            self.logger.debug("Running page context analysis")
            result = self.page_context_tool._run(self.driver)
            if result["success"]:
                self.logger.success("Page analysis completed")
                return PageContext(**result)
            else:
                self.logger.error(f"Page analysis failed: {result.get('error', 'Unknown error')}")
                return None
        except Exception as e:
            self.logger.error(f"Page analysis error: {str(e)}")
            return None
    
    def _generate_code(self, prompt: str) -> str:
        """Генерирует код с помощью LLM"""
        try:
            self.logger.llm_request("Code Generation", prompt[:200])
            
            # Логируем полный промпт для отладки
            print(f"🔍 FULL PROMPT LENGTH: {len(prompt)}")
            print(f"🔍 FULL PROMPT PREVIEW: {prompt[:1000]}...")
            
            messages = [
                SystemMessage(content="You are an automated system for creating and filling out documents using python selenium on a website https://app.conneto.com/ your task is to generate ready-to-use Selenium code for creating and filling out documents using python selenium on the website https://app.conneto.com/"),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            self.logger.llm_response("Code Generation", response.content[:200])
            return response.content
            
        except Exception as e:
            self.logger.error(f"Code generation error: {str(e)}")
            return ""
    
    def _handle_questions(self, ai_response: str, context: PageContext):
        """Обрабатывает вопросы к пользователю"""
        self.logger.user_interaction("AI needs more information")
        
        # Задаем вопросы пользователю
        result = self.question_tool._run(ai_response, context.dict())
        
        if result["success"]:
            # Сохраняем ответ в память
            response = UserResponse(
                question=result["question"],
                answer=result["answer"],
                timestamp=time.time()
            )
            self.memory.add_user_response(response)
            self.logger.user_interaction("Response collected", result['answer'][:50])
        else:
            self.logger.error(f"Failed to collect user response: {result.get('error', 'Unknown error')}")
    
    def _execute_code(self, code: str, context: PageContext, original_prompt: str) -> bool:
        """Выполняет код с обработкой ошибок и повторными попытками"""
        for attempt in range(self.max_retries):
            self.logger.step(f"Code Execution (attempt {attempt + 1}/{self.max_retries})")
            
            # Выполняем код
            self.logger.selenium_action("Executing code", f"Attempt {attempt + 1}")
            # Добавляем credentials в контекст
            context_dict = context.dict()
            context_dict['credentials'] = self.credentials
            result = self.selenium_tool._run(code, context_dict)
            
            if result["success"]:
                # Сохраняем успешное действие
                action = AgentAction(
                    action_type=ActionType.NAVIGATE,
                    description="Code execution successful",
                    code=code,
                    success=True
                )
                self.memory.add_action(action)
                self.logger.success("Code executed successfully")
                return True
            
            else:
                # Обрабатываем ошибку
                error_msg = result.get("error", "Unknown error")
                self.logger.error(f"Code execution failed: {error_msg}")
                
                # Сохраняем неудачное действие
                action = AgentAction(
                    action_type=ActionType.ERROR_FIX,
                    description=f"Code execution failed: {error_msg}",
                    code=code,
                    success=False,
                    error_message=error_msg
                )
                self.memory.add_action(action)
                self.memory.add_error(error_msg)
                
                # Пытаемся исправить ошибку
                if attempt < self.max_retries - 1:
                    self.logger.step("Error Fix Attempt")
                    fix_result = self.error_fix_tool._run(
                        original_code=code,
                        error_message=error_msg,
                        context=context.dict(),
                        initial_prompt=original_prompt
                    )
                    
                    if fix_result["success"]:
                        code = fix_result["corrected_code"]
                        self.logger.success("Error fix generated, retrying...")
                        continue
                    else:
                        self.logger.error(f"Failed to generate error fix: {fix_result.get('error', 'Unknown error')}")
        
        return False
    
    def _request_credentials(self):
        """Запрос учетных данных (как в оригинальном файле)"""
        self.logger.info("=== Authorization Required ===")
        self.logger.info(f"Using credentials: {self.credentials['email']}")
        # Учетные данные уже переданы в конструкторе
        self.memory.is_authenticated = True
        self.logger.success("Credentials set successfully")
    
    def get_status(self) -> Dict[str, Any]:
        """Возвращает текущий статус агента"""
        return {
            "is_running": self.is_running,
            "current_state": self.memory.current_state,
            "is_authenticated": self.memory.is_authenticated,
            "total_actions": len(self.memory.actions_history),
            "total_user_responses": len(self.memory.user_responses),
            "recent_errors": len(self.memory.get_recent_errors())
        } 