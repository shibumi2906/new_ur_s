import time
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
import json

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
from agents.lawyer_agent import LawyerAgent
from tools.error_fix_tool import ErrorFixTool
from logger import get_logger

class MainAgent:
    """Гибридный агент: жёсткая логика до PRELIMINARY_DATA, AI-управление с PRELIMINARY_DATA"""
    
    def __init__(self, driver, credentials: Dict[str, str]):
        self.driver = driver
        self.credentials = credentials
        
        # Инициализация логгера
        self.logger = get_logger("MainAgent")
        self.logger.info("Initializing MainAgent with hybrid architecture")
        
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
        self.lawyer_agent = LawyerAgent(driver=driver, prompt_generator=self.prompt_generator)  # GUI callback будет установлен позже
        self.error_fix_tool = ErrorFixTool()
        
        # Состояние
        self.is_running = False
        self.max_retries = Config.MAX_RETRIES
        self.logger.success("MainAgent initialized successfully")
    
    def run_workflow(self, url: str) -> bool:
        """Основной рабочий процесс с гибридным подходом"""
        self.logger.step("Hybrid Workflow Start", f"URL: {url}")
        self.is_running = True
        
        try:
            # Открываем страницу
            self.logger.selenium_action("Opening URL", url)
            self.driver.get(url)
            self.logger.success(f"Opened URL: {url}")
            
            # Ждем загрузки страницы
            time.sleep(3)
            
            # Проверяем, что страница загрузилась правильно
            current_url = self.driver.current_url
            if current_url == "data:," or not current_url or current_url.startswith("data:"):
                self.logger.error(f"Page failed to load. Current URL: {current_url}")
                return False
            
            # Начальная навигация (жёсткая логика)
            self._handle_initial_navigation(current_url)
            
            self.logger.success(f"Page loaded successfully: {current_url}")
            
            # Запрашиваем учетные данные
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
                navigation_result = self.navigator.determine_page_state(context)
                
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
                
                # 4. Выбираем режим работы: жёсткая логика или AI-управление
                if current_state.value in ['LOGIN', 'PAGE_1', 'PAGE_2', 'OPTIONS', 'DOCUMENTS_PAGE']:
                    # ЖЁСТКАЯ ЛОГИКА для простых этапов
                    self.logger.info("Using HARDCODED LOGIC for simple navigation")
                    success = self._handle_hardcoded_logic(current_state, context)
                elif current_state.value == 'CREATE_FROM_TEMPLATE':
                    # ПЕРЕХОДНОЕ СОСТОЯНИЕ - определяем следующий шаг
                    self.logger.info("CREATE_FROM_TEMPLATE state - analyzing page for next step")
                    success = self._handle_create_from_template(current_state, context)
                else:
                    # AI-УПРАВЛЕНИЕ для сложных этапов (PRELIMINARY_DATA и далее)
                    self.logger.info("Using AI-DRIVEN LOGIC for complex interactions")
                    success = self._handle_ai_logic(current_state, context)
                
                if not success:
                    self.logger.error("Failed to handle current state")
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
            self.logger.info("Hybrid Workflow finished")
    
    def _handle_initial_navigation(self, current_url: str):
        """Жёсткая логика начальной навигации"""
        # Если попали на /projects или другие страницы после входа, перенаправляем на /home
        if any(path in current_url for path in ["/projects", "/dashboard"]) and "/login" not in current_url and "/contracts" not in current_url:
            self.logger.info(f"Redirecting from {current_url} to /home")
            self.driver.get("https://app.conneto.com/home")
            time.sleep(3)
            current_url = self.driver.current_url
            self.logger.info(f"Redirected to: {current_url}")
        
        # Если попали на страницу предварительных данных без правильной последовательности
        if "/create-contract/details" in current_url and not self.memory.user_responses:
            self.logger.info(f"Redirecting from {current_url} to /home - wrong sequence")
            self.driver.get("https://app.conneto.com/home")
            time.sleep(3)
            current_url = self.driver.current_url
            self.logger.info(f"Redirected to: {current_url}")
        
        # Если попали на страницу шаблонов без получения данных от пользователя
        if "/create-contract/templates" in current_url and not self.memory.user_responses:
            self.logger.info(f"Redirecting from {current_url} to /home - no user data collected")
            self.driver.get("https://app.conneto.com/home")
            time.sleep(3)
            current_url = self.driver.current_url
            self.logger.info(f"Redirected to: {current_url}")
        
        # Если попали на страницу авторизации, сначала авторизуемся
        if "/login" in current_url or "/signin" in current_url or "login" in current_url.lower():
            self.logger.info("Detected login page, proceeding with authentication")
    
    def _handle_hardcoded_logic(self, current_state: PageState, context: PageContext) -> bool:
        """Жёсткая логика для простых этапов навигации (LOGIN, PAGE_1, PAGE_2, OPTIONS)"""
        self.logger.step(f"Hardcoded Logic: {current_state}")
        
        # Генерируем промпт для жёсткой логики
        has_user_data = len(self.memory.user_responses) > 0
        user_responses = [{"question": resp.question, "answer": resp.answer} for resp in self.memory.user_responses]
        prompt = self.prompt_generator.generate_action_prompt(
            context=context,
            state=current_state,
            has_user_data=has_user_data,
            user_responses=user_responses
        )
        
        print(f"🔍 HARDCODED LOGIC - State: {current_state}")
        print(f"🔍 HARDCODED LOGIC - URL: {context.current_url}")
        print(f"🔍 HARDCODED LOGIC - Prompt length: {len(prompt)}")
        print(f"🔍 HARDCODED LOGIC - Prompt preview: {prompt[:500]}...")
        
        # Генерируем код
        ai_response = self._generate_code(prompt, current_state)
        
        print(f"🔍 HARDCODED LOGIC - AI Response length: {len(ai_response)}")
        print(f"🔍 HARDCODED LOGIC - AI Response preview: {ai_response[:500]}...")
        
        # Выполняем код
        success = self._execute_code(ai_response, context, prompt)
        
        print(f"🔍 HARDCODED LOGIC - Execution result: {success}")
        return success
    
    def _handle_ai_logic(self, current_state: PageState, context: PageContext) -> bool:
        """AI-управление для сложных этапов (PRELIMINARY_DATA и далее)"""
        self.logger.step(f"AI Logic: {current_state}")
        
        # Генерируем промпт
        has_user_data = len(self.memory.user_responses) > 0
        user_responses = [{"question": resp.question, "answer": resp.answer} for resp in self.memory.user_responses]
        prompt = self.prompt_generator.generate_action_prompt(
            context=context,
            state=current_state,
            has_user_data=has_user_data,
            user_responses=user_responses
        )
        
        # Генерируем код
        ai_response = self._generate_code(prompt, current_state)
        
        # Проверяем, нужны ли вопросы или мы на странице с формой
        has_questions = '```questions' in ai_response or 'questions' in ai_response
        print(f"🔍 CHECKING FOR QUESTIONS: {has_questions}")
        print(f"🔍 AI RESPONSE PREVIEW: {ai_response[:200]}...")
        print(f"🔍 CURRENT STATE: {current_state}")
        print(f"🔍 CURRENT URL: {context.current_url}")
        
        # Проверяем, собраны ли все обязательные поля для текущего состояния
        all_required_fields_collected = self._check_all_required_fields_collected()
        
        # Активируем "юриста" если:
        # 1. LLM сгенерировал секцию questions И мы еще не собрали все данные
        # 2. Мы на странице предварительных данных И еще не собрали все обязательные поля
        # 3. Мы на странице шаблонов (нужно предложить шаблон)
        
        should_activate_lawyer = (
            (has_questions and not all_required_fields_collected) or
            (current_state == PageState.PRELIMINARY_DATA and not all_required_fields_collected) or
            current_state == PageState.TEMPLATE_SELECTION
        )
        
        print(f"🔍 DEBUG LAWYER ACTIVATION:")
        print(f"🔍 has_questions: {has_questions}")
        print(f"🔍 has_user_data: {has_user_data}")
        print(f"🔍 all_required_fields_collected: {all_required_fields_collected}")
        print(f"🔍 current_state: {current_state}")
        print(f"🔍 should_activate_lawyer: {should_activate_lawyer}")
        
        if should_activate_lawyer:
            self.logger.step("Lawyer Agent Activation Required")
            print(f"✅ LAWYER ACTIVATED - State: {current_state}")
            lawyer_result = self.run_lawyer_agent(context, current_state)
            
            # Проверяем, завершил ли LawyerAgent сбор всех данных
            if lawyer_result and lawyer_result.get("all_completed", False):
                print(f"✅ All questions completed, proceeding to form filling")
                # Переходим к заполнению формы: генерируем отдельный промпт для заполнения
                self.logger.step("Form Filling")
                # Собираем user_data из памяти
                user_data_dict = self._extract_user_data_from_responses()
                print(f"🔍 USER DATA FROM RESPONSES: {user_data_dict}")
                if not user_data_dict:
                    # fallback: попытка извлечь из ответа модели (если там есть вызовы функций)
                    user_data_dict = self._parse_function_calls(ai_response)
                if not user_data_dict:
                    self.logger.error("No user data collected for form filling")
                    return False
                # Создаем user_response для генератора промптов
                user_response = {
                    'question': 'Document details collected',
                    'answer': str(user_data_dict),
                    'legal_formulation': str(user_data_dict)
                }
                form_filling_prompt = self.prompt_generator.generate_form_filling_prompt(
                    context=context,
                    state=current_state,
                    user_response=user_response,
                    memory_summary="User data collected from LawyerAgent"
                )
                # Генерируем код для заполнения формы
                form_filling_code = self._generate_code(form_filling_prompt, current_state)
                # Выполняем код заполнения формы
                success = self._execute_code(form_filling_code, context, form_filling_prompt)
                if not success:
                    self.logger.error("Failed to fill form after retries")
                    return False
            else:
                print(f"✅ Lawyer handled, continuing loop for more questions")
                # Продолжаем цикл для получения дополнительных ответов
                return True
        elif all_required_fields_collected and current_state == PageState.PRELIMINARY_DATA:
            # У нас есть данные от пользователя, нужно заполнить форму
            print(f"✅ User data collected, proceeding to form filling")
            self.logger.step("Form Filling with User Data")
            
            # НОВАЯ АРХИТЕКТУРА: Сначала проверяем данные от LawyerAgent
            user_data_dict = {}
            if hasattr(self, 'lawyer_extracted_data') and self.lawyer_extracted_data:
                user_data_dict = self.lawyer_extracted_data.copy()
                print(f"🔍 Using data from LawyerAgent: {user_data_dict}")
            
            # Если нет данных от LawyerAgent, парсим вызовы функции из ответа AI
            if not user_data_dict:
                user_data_dict = self._parse_function_calls(ai_response)
            
            # Если нет вызовов функции, используем старый метод
            if not user_data_dict:
                user_data_dict = self._extract_user_data_from_responses()
            
            print(f"🔍 EXTRACTED USER DATA: {user_data_dict}")
            print(f"🔍 MEMORY RESPONSES COUNT: {len(self.memory.user_responses)}")
            
            # Если данные извлечены успешно, используем их
            if user_data_dict:
                # Создаем user_response в нужном формате для PromptGenerator
                user_response = {
                    'question': 'Document details collected',
                    'answer': str(user_data_dict),
                    'legal_formulation': str(user_data_dict)
                }
                print(f"🔍 USER RESPONSE FOR PROMPT GENERATOR: {user_response}")
                
                form_filling_prompt = self.prompt_generator.generate_form_filling_prompt(
                    context=context,
                    state=current_state,
                    user_response=user_response,
                    memory_summary="User data collected from LawyerAgent"
                )
                
                # Генерируем код для заполнения формы
                form_filling_code = self._generate_code(form_filling_prompt, current_state)
                
                # Выполняем код заполнения формы
                success = self._execute_code(form_filling_code, context, form_filling_prompt)
                if not success:
                    self.logger.error("Failed to fill form after retries")
                    return False
            else:
                print(f"⚠️ No user data extracted, continuing with questions")
                return True
        else:
            # Выполняем код
            self.logger.step("Code Execution")
            print(f"✅ NO LAWYER NEEDED - Executing code")
            success = self._execute_code(ai_response, context, prompt)
            if not success:
                self.logger.error("Failed to execute code after retries")
                return False
        
        return True
    
    def _handle_create_from_template(self, current_state: PageState, context: PageContext) -> bool:
        """Обрабатывает переходное состояние CREATE_FROM_TEMPLATE"""
        self.logger.step(f"Create From Template Handler: {current_state}")
        
        # Анализируем страницу, чтобы понять, что делать дальше
        # Если видим поля для заполнения - переходим к DOCUMENT_FILLING
        # Если это еще промежуточная страница - используем навигационную логику
        
        print(f"🔍 CREATE_FROM_TEMPLATE: Analyzing page")
        print(f"🔍 CREATE_FROM_TEMPLATE: URL: {context.current_url}")
        print(f"🔍 CREATE_FROM_TEMPLATE: Title: {context.title}")
        
        # Проверяем, есть ли на странице поля для заполнения документа
        form_fields = self._analyze_document_form_fields(context)
        
        if form_fields:
            # Есть поля для заполнения - активируем LawyerAgent для сбора данных
            print(f"🔍 CREATE_FROM_TEMPLATE: Found {len(form_fields)} form fields, activating LawyerAgent")
            lawyer_result = self.run_lawyer_agent(context, PageState.DOCUMENT_FILLING)
            
            if lawyer_result and lawyer_result.get("all_completed", False):
                # Данные собраны, переходим к заполнению
                print(f"✅ Document data collected, proceeding to form filling")
                return True
            else:
                # Продолжаем сбор данных
                return True
        else:
            # Нет полей - используем обычную навигационную логику
            print(f"🔍 CREATE_FROM_TEMPLATE: No form fields found, using navigation logic")
            return self._handle_hardcoded_logic(current_state, context)
    
    def _analyze_document_form_fields(self, context: PageContext) -> list:
        """Анализирует, есть ли на странице поля для заполнения документа"""
        html = context.body_html.lower()
        
        # Ищем признаки полей документа (не технических полей)
        document_field_indicators = [
            'party', 'contract', 'agreement', 'client', 'customer',
            'date', 'amount', 'price', 'duration', 'term',
            'address', 'description', 'subject', 'object',
            'сторона', 'договор', 'клиент', 'заказчик',
            'дата', 'сумма', 'цена', 'срок', 'период',
            'адрес', 'описание', 'предмет', 'объект'
        ]
        
        form_fields = []
        for element in context.elements:
            if element.tag in ['input', 'textarea', 'select']:
                element_text = (element.text or '').lower()
                element_id = (element.id or '').lower()
                element_class = (element.class_name or '').lower()
                
                # Проверяем, содержит ли элемент индикаторы полей документа
                all_text = f"{element_text} {element_id} {element_class}"
                if any(indicator in all_text for indicator in document_field_indicators):
                    form_fields.append(element)
                    print(f"🔍 Found document field: {element.tag} - {all_text[:100]}")
        
        return form_fields
    
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
    
    def _get_system_message_for_state(self, state: PageState) -> str:
        """Возвращает системное сообщение (SystemMessage) в зависимости от этапа"""
        
        if state == PageState.PRELIMINARY_DATA:
            return (
                "You are a legal assistant helping the user prepare a new document on https://app.conneto.com.\n\n"
                "Your task is to:\n"
                "- Ask the user ONE question at a time, starting with the most important required fields first.\n"
                "- Required fields (in order of priority): document name, document language.\n"
                "- Optional fields: document number, project.\n"
                "- Format your questions in a JSON block under ```questions with one object per question.\n\n"
                "Example format:\n"
                "```questions\n"
                "[\n"
                "  {\"question\": \"What is the document name?\"}\n"
                "]\n"
                "```\n\n"
                "IMPORTANT: Ask only ONE question at a time. Wait for the user's response before asking the next question.\n"
                "Avoid filling out the form until all required data is collected. Do not generate selenium code yet. Your only task is to generate questions in JSON format.\n\n"
                "🚨 MANDATORY FUNCTION CALL: After receiving ANY user response, you MUST call this function:\n"
                "extract_form_data(user_answer=\"EXACT_USER_TEXT\", question_type=\"FIELD_TYPE\")\n\n"
                "RULES:\n"
                "1. ALWAYS call extract_form_data() after user answers\n"
                "2. Use EXACT text user provided (no modifications)\n"
                "3. question_type depends on current question:\n"
                "   - \"What is the document name\" → question_type=\"name\"\n"
                "   - \"What is the language\" → question_type=\"language\"\n"
                "   - \"What is the number\" → question_type=\"number\"\n"
                "   - \"What is the project\" → question_type=\"project\"\n\n"
                "EXAMPLES:\n"
                "- User: \"p1p\" → extract_form_data(\"p1p\", \"name\")\n"
                "- User: \"договор аренды\" → extract_form_data(\"договор аренды\", \"name\")\n"
                "- User: \"English\" → extract_form_data(\"English\", \"language\")\n"
                "- User: \"123\" → extract_form_data(\"123\", \"number\")\n\n"
                "⚠️ CRITICAL: You MUST call extract_form_data() after EVERY user response. This is NOT optional!"
            )
        
        elif state == PageState.TEMPLATE_SELECTION:
            return (
                "You are assisting the user in selecting the appropriate document template on https://app.conneto.com.\n\n"
                "Your task is to:\n"
                "- Analyze the list of available templates (provided in context).\n"
                "- Ask the user which type of document they intend to create.\n"
                "- Based on their answer, suggest the most relevant template(s).\n"
                "- Format your suggestions in JSON under ```template_suggestions.\n\n"
                "Example format:\n"
                "```template_suggestions\n"
                "[\n"
                "  {\"template_name\": \"Contract of Rent\", \"reason\": \"Matches user's intent to rent equipment\"}\n"
                "]\n"
                "```\n\n"
                "Do not generate selenium code yet. Focus only on guiding the user through template selection."
            )

        elif state == PageState.DOCUMENT_FILLING:
            return (
                "You are assisting the user in filling out a document template on https://app.conneto.com.\n\n"
                "Your task is to:\n"
                "- Ask all required questions needed to complete the template.\n"
                "- Format the questions in JSON under ```questions.\n"
                "- Once all answers are collected, generate ready-to-use python selenium code to fill in the template fields.\n"
                "- Wrap the code block in ```python.\n\n"
                "If any data is missing, ask before generating code. After confirmation, your output must include a single python selenium code block."
            )

        elif state == PageState.COMPLETION:
            return (
                "You are finalizing the document creation process on https://app.conneto.com.\n\n"
                "Your task is to:\n"
                "- Verify that all required fields have been completed.\n"
                "- Generate selenium code to submit the form or proceed to the next step.\n"
                "- Ensure the document creation process is successfully completed.\n\n"
                "Generate ready-to-use python selenium code wrapped in ```python."
            )

        else:
            # Стандартное поведение по умолчанию для других состояний
            return (
                "You are an automated system for creating and filling out documents using python selenium on a website https://app.conneto.com. "
                "Your task is to generate ready-to-use Selenium code for creating and filling out documents using python selenium on the website https://app.conneto.com."
            )
    
    def _generate_code(self, prompt: str, state: PageState = None) -> str:
        """Генерирует код с помощью LLM"""
        try:
            self.logger.llm_request("Code Generation", prompt[:200])
            
            # Логируем полный промпт для отладки
            print(f"🔍 FULL PROMPT LENGTH: {len(prompt)}")
            print(f"🔍 FULL PROMPT PREVIEW: {prompt[:1000]}...")
            
            # Получаем динамическое системное сообщение
            system_message = self._get_system_message_for_state(state) if state else self._get_system_message_for_state(PageState.LOGIN)
            
            messages = [
                SystemMessage(content=system_message),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            self.logger.llm_response("Code Generation", response.content[:200])
            
            # Логируем полный ответ GPT для отладки
            print(f"🔍 FULL GPT RESPONSE LENGTH: {len(response.content)}")
            print(f"🔍 FULL GPT RESPONSE: {response.content}")
            
            return response.content
            
        except Exception as e:
            self.logger.error(f"Code generation error: {str(e)}")
            return ""
    
    def run_lawyer_agent(self, context: PageContext, state: PageState) -> Dict[str, Any]:
        """Запускает LawyerAgent для сбора информации у пользователя"""
        try:
            self.logger.step("Lawyer Agent Starting")
            self.logger.user_interaction("Lawyer agent needs more information")
            
            # Создаем контекст для LawyerAgent
            context_dict = context.dict()
            context_dict['current_state'] = state
            
            # ВАЖНО: Передаем системный промпт от MainAgent в LawyerAgent
            context_dict['system_prompt'] = self._get_system_message_for_state(state)
            
            # Запускаем LawyerAgent
            result = self.lawyer_agent._run(context_dict)
            
            if result["success"]:
                # LawyerAgent уже создал UserResponse, просто добавляем в память
                if hasattr(self.lawyer_agent, 'user_responses') and self.lawyer_agent.user_responses:
                    latest_response = self.lawyer_agent.user_responses[-1]
                    self.memory.add_user_response(latest_response)
                
                # ВАЖНО: Получаем данные, извлеченные LawyerAgent через extract_form_data()
                if 'extracted_data' in context_dict:
                    print(f"🔍 MAIN AGENT: Received extracted_data from LawyerAgent: {context_dict['extracted_data']}")
                    # Сохраняем извлеченные данные для последующего использования
                    if not hasattr(self, 'lawyer_extracted_data'):
                        self.lawyer_extracted_data = {}
                    self.lawyer_extracted_data.update(context_dict['extracted_data'])
                    print(f"🔍 MAIN AGENT: Total lawyer_extracted_data: {self.lawyer_extracted_data}")
                
                self.logger.user_interaction("Response collected", result['answer'][:50])
                self.logger.info(f"Legal formulation: {result.get('legal_formulation', 'N/A')}")
                
                return {
                    "success": True,
                    "all_completed": result.get("all_completed", False),
                    "result": result
                }
            else:
                self.logger.error(f"Failed to collect user response: {result.get('error', 'Unknown error')}")
                return {
                    "success": False,
                    "all_completed": False,
                    "error": result.get('error', 'Unknown error')
                }
                
        except Exception as e:
            self.logger.error(f"LawyerAgent error: {str(e)}")
            return {
                "success": False,
                "all_completed": False,
                "error": str(e)
            }
    
    def _handle_questions(self, ai_response: str, context: PageContext):
        """Обрабатывает вопросы к пользователю через LawyerAgent (устаревший метод)"""
        return self.run_lawyer_agent(context, PageState.PRELIMINARY_DATA)
    
    def _execute_code(self, code: str, context: PageContext, original_prompt: str) -> bool:
        """Выполняет код с обработкой ошибок и повторными попытками"""
        for attempt in range(self.max_retries):
            self.logger.step(f"Code Execution (attempt {attempt + 1}/{self.max_retries})")
            
            # Выполняем код
            self.logger.selenium_action("Executing code", f"Attempt {attempt + 1}")
            # Добавляем credentials и user_data в контекст
            context_dict = context.dict()
            context_dict['credentials'] = self.credentials
            
            # Добавляем данные пользователя
            user_data = {}
            for response in self.memory.user_responses:
                if response.question and response.answer:
                    # Извлекаем ключ из вопроса (например, "document_name" из "What is the document name?")
                    question_lower = response.question.lower()
                    if 'document name' in question_lower or 'название документа' in question_lower:
                        user_data['document_name'] = response.answer
                    elif 'language' in question_lower or 'язык' in question_lower:
                        user_data['document_language'] = response.answer
                    elif 'number' in question_lower or 'номер' in question_lower:
                        user_data['document_number'] = response.answer
                    elif 'project' in question_lower or 'проект' in question_lower:
                        user_data['add_to_project'] = response.answer
            
            context_dict['user_data'] = user_data
            
            # Отладочный вывод перед выполнением Selenium
            print(f"🔍 MAIN AGENT: Executing Selenium with user_data: {user_data}")
            print(f"🔍 MAIN AGENT: Total context keys: {list(context_dict.keys())}")
            
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
        """Запрос учетных данных"""
        self.logger.info("=== Authorization Required ===")
        self.logger.info(f"Using credentials: {self.credentials['email']}")
        # Учетные данные уже переданы в конструкторе
        self.memory.is_authenticated = True
        self.logger.success("Credentials set successfully")
    
    def set_gui_callback(self, callback):
        """Устанавливает callback для взаимодействия с GUI"""
        self.lawyer_agent.gui_callback = callback
        self.logger.info("GUI callback set for LawyerAgent")
    
    def extract_form_data(self, user_answer: str, question_type: str) -> Dict[str, str]:
        """Извлекает данные формы из ответа пользователя по типу вопроса"""
        print(f"🔍 EXTRACTING FORM DATA: answer='{user_answer}', type='{question_type}'")
        
        if question_type == "title" or question_type == "name":
            return {"document_name": user_answer}
        elif question_type == "language":
            return {"document_language": user_answer}
        elif question_type == "number":
            return {"document_number": user_answer}
        elif question_type == "project":
            return {"add_to_project": user_answer}
        else:
            print(f"🔍 UNKNOWN QUESTION TYPE: {question_type}")
            return {}

    def _parse_function_calls(self, ai_response: str) -> Dict[str, str]:
        """Парсит вызовы функции extract_form_data из ответа AI"""
        import re
        
        print(f"🔍 PARSING FUNCTION CALLS from: {ai_response[:200]}...")
        
        # Ищем вызовы функции extract_form_data
        pattern = r'extract_form_data\(user_answer=["\']([^"\']+)["\'],\s*question_type=["\']([^"\']+)["\']\)'
        matches = re.findall(pattern, ai_response)
        
        user_data = {}
        for user_answer, question_type in matches:
            print(f"🔍 FOUND FUNCTION CALL: extract_form_data('{user_answer}', '{question_type}')")
            extracted_data = self.extract_form_data(user_answer, question_type)
            user_data.update(extracted_data)
        
        print(f"🔍 PARSED USER DATA: {user_data}")
        return user_data

    def _extract_user_data_from_responses(self) -> Dict[str, str]:
        """Извлекает структурированные данные из ответов пользователя"""
        user_data = {}
        
        print(f"🔍 PROCESSING {len(self.memory.user_responses)} USER RESPONSES:")
        
        for i, response in enumerate(self.memory.user_responses):
            question_lower = response.question.lower()
            answer = response.answer.strip()
            
            print(f"🔍 Response {i+1}: Q='{response.question}' A='{answer}'")
            
            # Извлекаем данные по ключевым словам в вопросах
            print(f"🔍 CHECKING KEYWORDS for question: '{question_lower}'")
            
            # Расширенный список ключевых слов для названия документа
            if any(keyword in question_lower for keyword in [
                "название", "наименование", "document name", "title", 
                "название документа", "название файла", "введите название"
            ]):
                user_data['document_name'] = answer
                print(f"🔍 Found document_name: {answer}")
            # Расширенный список ключевых слов для языка
            elif any(keyword in question_lower for keyword in [
                "язык", "language", "lang", "язык документа", "выберите язык"
            ]):
                user_data['document_language'] = answer
                print(f"🔍 Found document_language: {answer}")
            # Номер документа
            elif any(keyword in question_lower for keyword in [
                "номер", "number", "num", "номер документа", "введите номер"
            ]):
                if answer and answer.lower() not in ["skip", "пропустить", "нет", "no", ""]:
                    user_data['document_number'] = answer
                    print(f"🔍 Found document_number: {answer}")
            # Проект
            elif any(keyword in question_lower for keyword in [
                "проект", "project", "proj", "выберите проект", "добавить к проекту"
            ]):
                if answer and answer.lower() not in ["skip", "пропустить", "нет", "no", ""]:
                    user_data['add_to_project'] = answer
                    print(f"🔍 Found add_to_project: {answer}")
        
        print(f"🔍 FINAL EXTRACTED USER DATA: {user_data}")
        return user_data
    
    def _check_all_required_fields_collected(self) -> bool:
        """Проверяет, собраны ли все обязательные поля для текущего состояния"""
        required_fields = ["document_name", "document_language"]
        collected_fields = []
        
        for response in self.memory.user_responses:
            question_lower = response.question.lower()
            answer_lower = response.answer.lower()
            
            # Проверяем разные варианты вопросов (без подчёркиваний)
            if (any(keyword in question_lower for keyword in ["название", "document name", "title"]) or
                "название файла" in question_lower):
                if answer_lower and answer_lower not in ["skip", "пропустить", "нет", "no", ""]:
                    collected_fields.append("document_name")
                    print(f"🔍 Found document_name from question: '{question_lower}' -> '{answer_lower}'")
            
            elif (any(keyword in question_lower for keyword in ["язык", "language"]) or
                  "язык документа" in question_lower):
                if answer_lower and answer_lower not in ["skip", "пропустить", "нет", "no", ""]:
                    collected_fields.append("document_language")
                    print(f"🔍 Found document_language from question: '{question_lower}' -> '{answer_lower}'")
        
        all_collected = all(field in collected_fields for field in required_fields)
        print(f"🔍 REQUIRED FIELDS CHECK: {required_fields}")
        print(f"🔍 COLLECTED FIELDS: {collected_fields}")
        print(f"🔍 ALL COLLECTED: {all_collected}")
        return all_collected
    
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