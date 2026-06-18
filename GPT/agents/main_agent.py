import time
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
import json

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# пакетные импорты без sys.path-хаков
from ..config import Config
from ..models import PageContext, PageState, AgentAction, ActionType, UserResponse
from ..memory.agent_memory import AgentMemory
from .navigator_agent import NavigatorAgent
from .prompt_generator_agent import PromptGeneratorAgent
from ..tools.selenium_tool import SeleniumTool
from ..tools.page_context_tool import PageContextTool
from ..tools.preliminary_data_tool import PreliminaryDataTool
from .lawyer_agent import LawyerAgent
from ..tools.error_fix_tool import ErrorFixTool
from ..logger import get_logger


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
        self.prelim_tool = PreliminaryDataTool(driver, logger=self.logger)

        self.lawyer_agent = LawyerAgent(driver=driver,
                                        prompt_generator=self.prompt_generator)  # GUI callback будет установлен позже
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
                if current_state in {PageState.LOGIN, PageState.PAGE_1, PageState.DOCUMENTS_PAGE}:
                    # ЖЁСТКАЯ ЛОГИКА для простых этапов
                    self.logger.info("Using HARDCODED LOGIC for simple navigation")
                    success = self._handle_hardcoded_logic(current_state, context)
                elif current_state.value == 'CREATE_FROM_TEMPLATE':
                    # ПЕРЕХОДНОЕ СОСТОЯНИЕ - определяем следующий шаг
                    self.logger.info("CREATE_FROM_TEMPLATE state - analyzing page for next step")
                    success = self._handle_create_from_template(current_state, context)
                else:
                    # AI-УПРАВЛЕНИЕ для сложных этапов (PRELIMINARY_DATA, TEMPLATE_SELECTION и далее)
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
        if any(path in current_url for path in
               ["/projects", "/dashboard"]) and "/login" not in current_url and "/contracts" not in current_url:
            self.logger.info(f"Redirecting from {current_url} to /home")
            self.driver.get("https://app.conneto.com/home")
            time.sleep(3)
            current_url = self.driver.current_url
            self.logger.info(f"Redirected to: {current_url}")

        # Если попали на страницу предварительных данных без правильной последовательности
        if "/create-contract/details" in current_url and not self.memory.user_responses:
            self.logger.info(f"Detected PRELIMINARY_DATA page without user responses - activating LawyerAgent")
            # НЕ делаем редирект - остаёмся на странице для активации LawyerAgent

        # Если попали на страницу шаблонов без получения данных от пользователя
        if "/create-contract/templates" in current_url and not self.memory.user_responses:
            self.logger.info(f"Detected TEMPLATE_SELECTION page without user responses - activating LawyerAgent")
            # НЕ делаем редирект - остаёмся на странице для активации LawyerAgent

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
        """НОВАЯ ПРОСТАЯ ЛОГИКА: пошаговое заполнение формы"""
        self.logger.step(f"AI Logic: {current_state}")

        # РАННЯЯ ОТСЕЧКА: для PRELIMINARY_DATA сначала собираем обязательные поля
        if current_state == PageState.PRELIMINARY_DATA:
            all_required_fields_collected = self._check_all_required_fields_collected()
            if not all_required_fields_collected:
                self.logger.step("Lawyer Agent Activation Required (early)")
                print(f"✅ EARLY LAWYER ACTIVATION - State: {current_state}")
                lawyer_result = self.run_lawyer_agent(context, current_state)

                # Обрабатываем результат LawyerAgent
                if lawyer_result and lawyer_result.get("immediate_fill", False):
                    field_name = lawyer_result.get("field_name")
                    field_value = lawyer_result.get("answer")

                    if field_name and field_name != "unknown" and field_value and field_value.lower() not in {
                        "no answer provided", "skip", "пропустить", "нет", "no", ""}:
                        selenium_code = self._generate_single_field_code(field_name, field_value, context)
                        success = self._execute_code(selenium_code, context, f"Early fill: {field_name}")
                        if success:
                            print(f"✅ Early field {field_name} filled successfully")
                            # Сохраняем в память
                            if not hasattr(self, 'lawyer_extracted_data'):
                                self.lawyer_extracted_data = {}
                            self.lawyer_extracted_data[field_name] = str(field_value).strip()
                            self.memory.add_user_response(
                                UserResponse(
                                    question=f"{field_name} [FIELD:{field_name}]",
                                    answer=str(field_value).strip(),
                                    legal_formulation=str(field_value).strip(),
                                    timestamp=time.time()
                                )
                            )
                        return True  # Продолжаем цикл

                # Если все данные собраны, продолжаем обычную логику
                if lawyer_result and lawyer_result.get("all_completed", False):
                    print(f"✅ All required fields collected, proceeding to form filling")
                else:
                    return True  # Продолжаем сбор данных

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

            # НОВАЯ ЛОГИКА: Обработка immediate_fill для пошагового заполнения полей
            if lawyer_result and lawyer_result.get("immediate_fill", False):
                field_name = lawyer_result.get("field_name")
                field_value = lawyer_result.get("answer")

                print(f"🔍 IMMEDIATE FILL: {field_name} = {field_value}")

                # Фильтруем мусорные значения
                if not field_name or field_name == "unknown":
                    print(f"🔍 Ignoring unknown field in immediate_fill")
                    return True  # Продолжаем цикл
                if not field_value or field_value.lower() in {"no answer provided", "skip", "пропустить", "нет", "no",
                                                              ""}:
                    print(f"🔍 Ignoring empty/technical answer in immediate_fill: '{field_value}'")
                    return True  # Продолжаем цикл

                # Генерируем и выполняем код для заполнения ОДНОГО поля
                selenium_code = self._generate_single_field_code(field_name, field_value, context)
                success = self._execute_code(selenium_code, context, f"Fill {field_name}")

                if success:
                    print(f"✅ Field {field_name} filled successfully")
                    # ⬇️ sync memory & cache
                    if not hasattr(self, 'lawyer_extracted_data'):
                        self.lawyer_extracted_data = {}
                    self.lawyer_extracted_data[field_name] = str(field_value).strip()
                    self.memory.add_user_response(
                        UserResponse(
                            question=f"{field_name} [FIELD:{field_name}]",
                            answer=str(field_value).strip(),
                            legal_formulation=str(field_value).strip(),
                            timestamp=time.time()
                        )
                    )
                    if current_state == PageState.PRELIMINARY_DATA:
                        expected = {field_name: field_value}
                        ok = self.prelim_tool.verify_and_fix(
                            context,
                            expected,
                            error_fix_tool=self.error_fix_tool,
                            selenium_tool=self.selenium_tool,
                            credentials=self.credentials,
                            original_code=selenium_code,
                            original_prompt=f"Immediate fill: {field_name}"
                        )
                        if not ok:
                            self.logger.error(f"PreliminaryData verify_and_fix failed for {expected}")
                            return False

                    return True  # Продолжаем цикл для следующего поля
                else:
                    self.logger.error(f"Failed to fill field {field_name}")
                    return False

            # Проверяем, завершил ли LawyerAgent сбор всех данных
            elif lawyer_result and lawyer_result.get("all_completed", False):
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

            # НОВАЯ АРХИТЕКТУРА: Парсим вызовы функции из ответа AI
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
                if current_state == PageState.PRELIMINARY_DATA:
                    expected = self._extract_user_data_from_responses()
                    # keep only fields relevant to PRELIMINARY_DATA
                    expected = {
                        k: v for k, v in (expected or {}).items()
                        if k in ("document_name", "document_language") and v
                    }

                    ok = self.prelim_tool.verify_and_fix(
                        context,
                        expected,
                        error_fix_tool=self.error_fix_tool,
                        selenium_tool=self.selenium_tool,
                        credentials=self.credentials,
                        original_code=form_filling_code,
                        original_prompt=form_filling_prompt
                    )
                    if not ok:
                        self.logger.error("PreliminaryData verify_and_fix failed after form filling")
                        return False
                    # ensure page advances after verification
                    cont_code = self._generate_continue_button_code(context)
                    self._execute_code(cont_code, context, "click-continue-after-prelim-verify")

            else:
                print(f"⚠️ No user data extracted, continuing with questions")
                return True
        else:
            # Выполняем код
            self.logger.step("Code Execution")
            print(f"✅ NO LAWYER NEEDED - Executing code")
            success = self._execute_code(ai_response, context, prompt)
            if not success:
                self.logger.error("Failed to execute code — invoking ErrorFixTool (final attempt)")
                recent_err = (
                    self.memory.get_recent_errors()[-1] if self.memory.get_recent_errors() else "Unknown error")
                fix = self.error_fix_tool._run(
                    original_code=ai_response,
                    error_message=recent_err,
                    context=context.dict(),
                    initial_prompt=prompt
                )
                if fix.get("success"):
                    corrected_code = fix["corrected_code"]
                    self.logger.info("Retrying with corrected code from ErrorFixTool")
                    success = self._execute_code(corrected_code, context, prompt)
                    if not success:
                        self.logger.error("Corrected code failed after retry")
                        return False
                else:
                    self.logger.error(f"ErrorFixTool failed: {fix.get('error', 'Unknown')}")
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
                "You are a legal assistant helping the user prepare a new document on [https://app.conneto.com](https://app.conneto.com).\n\n"
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
                "Scope ALL element searches to the main content FORM, NEVER header or nav. "
                "First locate a container: container = driver.find_element(By.CSS_SELECTOR, 'main, div[role=\"main\"], form, div.content, div.page'); "
                "Then ONLY search INSIDE it (use container.find_element / container.find_elements). "
                "Avoid header/nav by excluding elements with ancestors header or nav in XPath. "
                "When locating inputs, follow this order INSIDE container: "
                "1) By label → //label[normalize-space()='Document name']/following::*[self::input or self::textarea][1][not(ancestor::header) and not(ancestor::nav)] "
                "2) By attributes → input[placeholder*='Document name' i], input[name*='document_name' i], input[id*='document_name' i] (inside container only). "
                "Never type into global search, header or nav elements. "
                "Use provided variables: user_data['document_name'], user_data['document_language']. "
                "After typing, assert the value belongs to the form field (not header): "
                "  assert field.get_attribute('value') == user_data['document_name'] "
                "  try: hs = driver.find_element(By.CSS_SELECTOR, 'header input, nav input'); "
                "       assert hs.get_attribute('value') != user_data['document_name'] "
                "  except Exception: pass "
                "Wrap the answer in ```python fences (no comments). "

            )

        # === ИСПРАВЛЕНО: Добавлена логика анализа шаблонов ===
        elif state == PageState.TEMPLATE_SELECTION:
            return (
                "Вы — юрист-помощник, который помогает пользователю выбрать шаблон документа на странице [https://app.conneto.com/create-contract/templates](https://app.conneto.com/create-contract/templates).\n"
                "Страница содержит список доступных шаблонов, например: 'NDA official version', 'NDA-7', 'Contract of Service'.\n\n"
                "ВАША ЗАДАЧА:\n"
                "1. **КРИТИЧЕСКИ ВАЖНО:** Проанализируйте предоставленный контекст страницы (`elements` и `body_html`) для поиска названий всех доступных шаблонов.\n"
                "2. Сформируйте вопрос пользователю, явно перечислив все найденные вами варианты шаблонов.\n"
                "3. Вопрос должен быть в формате JSON:\n"
                "```questions\n"
                "[\n"
                "  {\"question\": \"Какой из следующих шаблонов вы хотите использовать? (Доступные варианты: [ПЕРЕЧИСЛИТЕ НАЙДЕННЫЕ ШАБЛОНЫ ИЗ КОНТЕКСТА])\"}\n"
                "]\n"
                "```\n"
                "4. ОБЯЗАТЕЛЬНО: После получения ответа от пользователя (например, 'NDA official version'), вы ДОЛЖНЫ вызвать функцию:\n"
                "extract_form_data(user_answer='NDA official version', question_type='template')\n\n"
                "Не генерируйте Selenium код. Ваша единственная задача — получить название шаблона у пользователя."
            )

        elif state == PageState.DOCUMENT_FILLING:
            return (
                "You are an automation copilot. Output ONLY executable Python code for Selenium 4.\n"
                "Variables available: `driver`, `user_data` (dict: document_name, document_language, etc).\n"
                "Task: Fill the form on the page.\n\n"

                "CRITICAL RULES FOR SELECTORS:\n"
                "1. NEVER target the Global Search bar. The generic 'input' often selects the Header Search.\n"
                "2. ALWAYS check element ancestry: `not(ancestor::header)` and `not(ancestor::nav)`.\n"
                "3. Use `placeholder` attributes that contain 'Document' or 'Name', NOT 'Search'.\n"
                "4. Prefer finding the Form Container first: `form = driver.find_element(By.CSS_SELECTOR, 'main form')` then find inputs INSIDE it.\n\n"

                "Code Pattern for Inputs:\n"
                "try:\n"
                "    # Locate Main Content Area first to avoid Header\n"
                "    main_area = driver.find_element(By.CSS_SELECTOR, 'main, div[role=\"main\"], .page-content')\n"
                "    name_input = main_area.find_element(By.CSS_SELECTOR, \"input[placeholder*='Name'], input[name='name']\")\n"
                "    name_input.send_keys(user_data['document_name'])\n"
                "except Exception:\n"
                "    # Fallback only if scoped search fails\n"
                "    pass\n\n"

                "Fill all fields from `user_data` and click Continue/Next."
            )

        elif state == PageState.COMPLETION:
            return (
                "You are finalizing the document creation process on [https://app.conneto.com](https://app.conneto.com).\n\n"
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
            system_message = self._get_system_message_for_state(state) if state else self._get_system_message_for_state(
                PageState.LOGIN)

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

            # Если это первый запуск для PRELIMINARY_DATA, пробуем пакетный режим
            if (state == PageState.PRELIMINARY_DATA and
                    len(self.memory.user_responses) == 0 and
                    hasattr(self.lawyer_agent, 'collect_all_answers_batch')):

                print(f"🎯 MAIN AGENT: Trying BATCH mode for faster data collection")
                batch_result = self.lawyer_agent.collect_all_answers_batch(context_dict)

                if batch_result.get("success") and batch_result.get("batch_complete"):
                    print(f"🎯 MAIN AGENT: BATCH mode successful! All data collected.")
                    # Данные собраны, используем результат пакетного режима
                    result = batch_result

                    # Нормализуем и сохраняем в контекст для автозаполнения
                    extracted = batch_result.get("extracted_data") or batch_result.get("user_data") or {}
                    if extracted:
                        context_dict["user_data"] = extracted
                        self.logger.info(f"USER_DATA (batch): {extracted}")

                    # Сигнал основному циклу: всё собрано — переходим к заполнению
                    result["all_completed"] = True
                    result["immediate_fill"] = False

                elif batch_result.get("waiting_for_batch_input"):
                    print(f"🎯 MAIN AGENT: BATCH questions asked, waiting for user input")

                    # Проверяем готовность ответа через GUI
                    if hasattr(self, 'gui_instance') and self.gui_instance and hasattr(self.gui_instance,
                                                                                       'get_user_answer_if_ready'):
                        user_answer = self.gui_instance.get_user_answer_if_ready()
                        if user_answer:
                            print(f"🎯 MAIN AGENT: User answer received: '{user_answer[:50]}...'")
                            # Обрабатываем ответ
                            if hasattr(self.lawyer_agent, 'process_batch_answer'):
                                batch_result_final = self.lawyer_agent.process_batch_answer(user_answer)
                                if batch_result_final.get("success") and batch_result_final.get("batch_complete"):
                                    print(f"🎯 MAIN AGENT: BATCH processing complete!")
                                    result = batch_result_final
                                else:
                                    print(f"🎯 MAIN AGENT: BATCH processing failed, using standard mode")
                                    result = self.lawyer_agent._run(context_dict)
                            else:
                                print(f"🎯 MAIN AGENT: No batch processing method, using standard mode")
                                result = self.lawyer_agent._run(context_dict)
                        else:
                            print(f"🎯 MAIN AGENT: Still waiting for user input...")
                            return {"success": True, "waiting_for_input": True}  # Продолжаем ждать
                    else:
                        print(f"🎯 MAIN AGENT: No GUI available for answer checking, using standard mode")
                        result = self.lawyer_agent._run(context_dict)
                else:
                    print(f"🎯 MAIN AGENT: BATCH mode failed, falling back to step-by-step")
                    # Запускаем стандартный LawyerAgent (как было раньше)
                    print(f"🔍 MAIN AGENT: Calling LawyerAgent._run() with context")
                    result = self.lawyer_agent._run(context_dict)
            else:
                # Если пакетный режим недоступен - запускаем стандартный LawyerAgent
                print(f"🔍 MAIN AGENT: Calling LawyerAgent._run() with context")
                result = self.lawyer_agent._run(context_dict)

            if result["success"]:

                # LawyerAgent уже создал UserResponse, просто добавляем в память
                if hasattr(self.lawyer_agent, 'user_responses') and self.lawyer_agent.user_responses:
                    latest_response = self.lawyer_agent.user_responses[-1]
                    self.memory.add_user_response(latest_response)

                    # ОТЛАДОЧНЫЕ ЛОГИ: отслеживаем все ответы пользователя
                    print(f"🔍 MAIN AGENT: Total user responses in memory: {len(self.memory.user_responses)}")
                    for i, resp in enumerate(self.memory.user_responses):
                        print(f"🔍 MAIN AGENT: Response {i + 1}: '{resp.question}' -> '{resp.answer}'")

                    # ВАЖНО: Получаем данные, извлеченные LawyerAgent через extract_form_data()
                    extracted = result.get("extracted_data") or context_dict.get("extracted_data")
                    if extracted:
                        if not hasattr(self, 'lawyer_extracted_data'):
                            self.lawyer_extracted_data = {}
                        self.lawyer_extracted_data.update(extracted)

                    # Сохраняем извлеченные данные для последующего использования
                    if not hasattr(self, 'lawyer_extracted_data'):
                        self.lawyer_extracted_data = {}

                    print(f"🔍 MAIN AGENT: Total lawyer_extracted_data: {self.lawyer_extracted_data}")

                # ОТЛАДОЧНЫЕ ЛОГИ: проверяем статус завершения
                all_completed = result.get("all_completed", False)
                print(f"🔍 MAIN AGENT: LawyerAgent all_completed status: {all_completed}")

                # Логируем в зависимости от типа результата
                if result.get("question_asked", False):
                    self.logger.user_interaction(f"Question asked: {result.get('question', 'N/A')[:50]}")
                    self.logger.info("Waiting for user response...")
                elif result.get("answer"):
                    self.logger.user_interaction("Response collected", result['answer'][:50])
                    self.logger.info(f"Legal formulation: {result.get('legal_formulation', 'N/A')}")
                else:
                    self.logger.user_interaction("LawyerAgent processing...")
                    self.logger.info("No answer yet")

                return {
                    "success": True,
                    "all_completed": all_completed,
                    "immediate_fill": result.get("immediate_fill", False),
                    "field_name": result.get("field_name"),
                    "answer": result.get("answer"),
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
        # Не исполняем вопросы или не-python ответы от LLM
        clean = code or ""
        if "```questions" in clean:
            print("✅ Skipping execution: questions handled by LawyerAgent/loop.")
            return True

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
                    # Извлекаем триггер поля из вопроса
                    import re
                    field_match = re.search(r'\[FIELD:(\w+)\]', response.question)
                    if field_match:
                        field_name = field_match.group(1)
                        user_data[field_name] = response.answer
                        print(
                            f"🔍 MAIN AGENT: Extracted field '{field_name}' with value '{response.answer}' from question: {response.question}")
                    else:
                        # Fallback на старый метод для совместимости
                        question_lower = response.question.lower()
                        if 'document name' in question_lower or 'название документа' in question_lower:
                            user_data['document_name'] = response.answer
                        elif 'language' in question_lower or 'язык' in question_lower:
                            user_data['document_language'] = response.answer
                        elif 'number' in question_lower or 'номер' in question_lower:
                            user_data['document_number'] = response.answer
                        elif 'project' in question_lower or 'проект' in question_lower:
                            user_data['add_to_project'] = response.answer
                        # === НОВОЕ: Обработка шаблона по ключевым словам ===
                        elif 'шаблон' in question_lower or 'template' in question_lower:
                            user_data['selected_template'] = response.answer
                        # =================================================

            context_dict['user_data'] = user_data
            # объединяем с тем, что накопил LawyerAgent
            if hasattr(self, 'lawyer_extracted_data') and isinstance(self.lawyer_extracted_data, dict):
                for k, v in self.lawyer_extracted_data.items():
                    if v:
                        user_data[k] = v

            # Отладочный вывод перед выполнением Selenium
            print(f"🔍 MAIN AGENT: Executing Selenium with user_data: {user_data}")
            print(f"🔍 MAIN AGENT: Total context keys: {list(context_dict.keys())}")
            print(f"🔍 MAIN AGENT: Total user responses: {len(self.memory.user_responses)}")

            # КРИТИЧЕСКИ ВАЖНО: отладочная информация для каждого поля
            if user_data:
                print(f"🔍 MAIN AGENT: USER DATA DETAILS:")
                for key, value in user_data.items():
                    print(f"🔍 MAIN AGENT:   {key}: '{value}'")
            else:
                print(f"🔍 MAIN AGENT: ❌ USER_DATA IS EMPTY! Checking why...")
                if self.memory.user_responses:
                    print(f"🔍 MAIN AGENT: Available responses:")
                    for i, resp in enumerate(self.memory.user_responses):
                        print(f"🔍 MAIN AGENT:   {i + 1}. Q: '{resp.question}' -> A: '{resp.answer}'")
                        # Проверяем триггеры
                        import re
                        field_match = re.search(r'\[FIELD:(\w+)\]', resp.question)
                        if field_match:
                            print(f"🔍 MAIN AGENT:      TRIGGER FOUND: {field_match.group(1)}")
                        else:
                            print(f"🔍 MAIN AGENT:      NO TRIGGER FOUND!")
                else:
                    print(f"🔍 MAIN AGENT: No user responses in memory!")

            # Проверяем, что код содержит данные пользователя
            if user_data and 'user_data' in code:
                print(f"🔍 MAIN AGENT: Code contains user_data references ✅")
            elif user_data:
                print(f"🔍 MAIN AGENT: ⚠️ Code does NOT contain user_data references!")
            else:
                print(f"🔍 MAIN AGENT: ❌ No user_data to pass to Selenium!")

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
        self.logger.info(f"GUI callback set for LawyerAgent: {callback}")
        print(f"🔍 MAIN AGENT: GUI callback set: {callback}")

    def set_gui_instance(self, gui_instance):
        """Устанавливает экземпляр GUI для проверки ответов пользователя"""
        self.gui_instance = gui_instance
        self.logger.info(f"GUI instance set for MainAgent: {gui_instance}")
        print(f"🔍 MAIN AGENT: GUI instance set: {gui_instance}")

    # === ИСПРАВЛЕНО: Добавлен selected_template ===
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
        elif question_type == "template":
            return {"selected_template": user_answer}
        else:
            print(f"🔍 UNKNOWN QUESTION TYPE: {question_type}")
            return {}

    # ==============================================

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
            question = response.question
            answer = response.answer.strip()

            print(f"🔍 Response {i + 1}: Q='{question}' A='{answer}'")

            # Сначала пытаемся извлечь триггер поля
            import re
            field_match = re.search(r'\[FIELD:(\w+)\]', question)
            if field_match:
                field_name = field_match.group(1)
                # Игнорируем unknown и пустые ответы
                if field_name == "unknown":
                    print(f"🔍 Ignoring unknown field")
                    continue
                if not answer or answer.lower() in {"no answer provided", "skip", "пропустить", "нет", "no", ""}:
                    print(f"🔍 Ignoring empty/technical answer: '{answer}'")
                    continue
                user_data[field_name] = answer
                print(f"🔍 Found field '{field_name}' from trigger: {answer}")
            else:
                # Fallback на старый метод с ключевыми словами
                question_lower = question.lower()
                print(f"🔍 CHECKING KEYWORDS for question: '{question_lower}'")

                # Проверяем точные ключи сначала
                if question_lower.strip() == "document_name":
                    user_data['document_name'] = answer
                    print(f"🔍 Found document_name (exact key): {answer}")
                elif question_lower.strip() == "document_language":
                    user_data['document_language'] = answer
                    print(f"🔍 Found document_language (exact key): {answer}")
                # Расширенный список ключевых слов для названия документа
                elif any(keyword in question_lower for keyword in [
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
                # === НОВОЕ: Шаблон ===
                elif any(keyword in question_lower for keyword in [
                    "шаблон", "template", "выберите шаблон"
                ]):
                    if answer and answer.lower() not in ["skip", "пропустить", "нет", "no", ""]:
                        user_data['selected_template'] = answer
                        print(f"🔍 Found selected_template: {answer}")
                # =======================

        print(f"🔍 FINAL EXTRACTED USER DATA: {user_data}")
        return user_data

    def _check_all_required_fields_collected(self) -> bool:
        """Проверяет, собраны ли все обязательные поля для текущего состояния"""
        required_fields = ["document_name", "document_language"]
        collected_fields = []

        # === НОВОЕ: Проверка для TEMPLATE_SELECTION ===
        if self.memory.current_state == PageState.TEMPLATE_SELECTION:
            has_template = False

            # Ищем в данных, извлеченных LawyerAgent
            if hasattr(self, 'lawyer_extracted_data') and 'selected_template' in self.lawyer_extracted_data:
                has_template = True

            # Ищем в ответах пользователя по ключевым словам или триггерам
            for resp in self.memory.user_responses:
                # Поле 'template'
                if "[FIELD:template]" in resp.question or "selected_template" in resp.question or "шаблон" in resp.question.lower():
                    if resp.answer and resp.answer.lower() not in ["no answer provided", "skip", "пропустить", "нет",
                                                                   "no", ""]:
                        has_template = True
                        break

            print(f"🔍 TEMPLATE SELECTION CHECK: Has template? {has_template}")
            return has_template
        # =============================================

        for response in self.memory.user_responses:
            question = response.question
            answer_lower = response.answer.lower()

            # Сначала проверяем триггеры полей
            import re
            field_match = re.search(r'\[FIELD:(\w+)\]', question)
            if field_match:
                field_name = field_match.group(1)
                if answer_lower and answer_lower not in ["skip", "пропустить", "нет", "no", ""]:
                    collected_fields.append(field_name)
                    print(f"🔍 Found {field_name} from trigger: '{question}' -> '{response.answer}'")
            else:
                # Fallback на старый метод с ключевыми словами
                question_lower = question.lower()

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

    def _generate_single_field_code(self, field_name: str, field_value: str, context: PageContext) -> str:
        """Генерирует Selenium код для заполнения одного поля с защитой от попадания в Header/Search"""

        # === НОВОЕ: Логика выбора шаблона ===
        if field_name == "selected_template":
            return f"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time

wait = WebDriverWait(driver, 15)
target_template = "{field_value}".strip()
print(f"🔍 Searching for template: {{target_template}}")

try:
    # Стратегия 1: Ищем элемент (например, <h2>, <h4>), содержащий точное название шаблона.
    # Затем ищем кнопку "Select" в пределах родительского контейнера.
    xpath_text = f"//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{{target_template.lower()}}')]"

    # Пытаемся найти кнопку в родительском элементе, который содержит текст. 
    # Этот XPath ищет кнопку "Select" в контейнере-предке, который находится близко к тексту.
    # Используем normalize-space() для обрезки пробелов.
    xpath_btn = f"//div[.//text()[normalize-space(.)='{{target_template}}']]/descendant::button[contains(., 'Select')]"

    # Более общий XPath, который ищет кнопку "Select" рядом с текстом
    xpath_alt = f"//button[contains(., 'Select') and (ancestor::div[.//text()[contains(., '{{target_template}}')]] or preceding::*[contains(., '{{target_template}}')])]"

    btn = None

    try:
        # Пробуем прямой поиск по точному тексту в контейнере
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_btn)))
        print("✅ Found template button via Specific Row XPath")
    except TimeoutException:
         try:
            # Пробуем более широкий поиск (на случай, если текст не в контейнере)
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_alt)))
            print("✅ Found template button via Broad Text Search XPath")
         except TimeoutException:
            pass

    if btn:
        driver.execute_script("arguments[0].scrollIntoView({{block: 'center'}});", btn)
        time.sleep(1)
        try:
            btn.click()
        except:
            driver.execute_script("arguments[0].click();", btn)
        print(f"✅ Clicked 'Select template' for: {{target_template}}")
    else:
        raise Exception(f"TEMPLATE_BUTTON_NOT_FOUND: Could not find 'Select template' button for '{{target_template}}'")

except Exception as e:
    print(f"❌ Error selecting template: {{e}}")
    raise e

"""
        # =======================================================
        elif field_name == "document_name":
            return f"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time

wait = WebDriverWait(driver, 15)

def is_element_in_header(element):
    try:
        # Проверка 1: Поиск родителя header или nav
        parent = element.find_element(By.XPATH, "./ancestor::header | ./ancestor::nav | ./ancestor::*[contains(@class, 'header')] | ./ancestor::*[contains(@class, 'navbar')]")
        return True
    except NoSuchElementException:
        pass

    # Проверка 2: Атрибуты самого элемента намекают на поиск
    outer_html = element.get_attribute("outerHTML").lower()
    if "search" in outer_html or "poisk" in outer_html:
        return True

    return False

try:
    print(f"🔄 Attempting to fill Document Name: {field_value}")

    # 1. Сначала ищем по очень специфичным плейсхолдерам, которые точно не поиск
    precise_selectors = [
        "input[placeholder*='Document name' i]",
        "input[placeholder*='Name of document' i]",
        "input[placeholder*='Contract title' i]",
        "input[name='document_name']", # Часто уникальное имя
        "input[id='documentName']"
    ]

    target_input = None

    # Попытка найти точный инпут
    for sel in precise_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elements:
                if el.is_displayed() and not is_element_in_header(el):
                    target_input = el
                    print(f"✅ Found by precise selector: {{sel}}")
                    break
            if target_input: break
        except: continue

    # 2. Если точный не найден, ищем через Label (самый надежный способ для форм)
    if not target_input:
        try:
            # XPath: найти label с текстом "Name" или "Title", взять следующий input
            xpath = "//label[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'name') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'title')]/following::input[1]"
            elements = driver.find_elements(By.XPATH, xpath)
            for el in elements:
                if el.is_displayed() and not is_element_in_header(el):
                    target_input = el
                    print(f"✅ Found by Label association")
                    break
        except: pass

    # 3. Fallback: Ищем внутри контейнера формы, исключая header
    if not target_input:
        try:
            # Находим контейнер формы, исключая навигацию
            container = driver.find_element(By.CSS_SELECTOR, "main, form, div[class*='content'], div[class*='page-body']")
            inputs = container.find_elements(By.TAG_NAME, "input")

            for inp in inputs:
                if not inp.is_displayed(): continue
                if inp.get_attribute("type") in ["hidden", "checkbox", "radio", "submit", "button"]: continue

                # Пропускаем, если это поиск
                if is_element_in_header(inp): continue

                # Если это текстовое поле в контенте, берем первое (обычно это Name)
                target_input = inp
                print(f"⚠️ Used fallback container search")
                break
        except: pass

    if target_input is None:
        raise Exception("DOCUMENT_NAME_INPUT_NOT_FOUND: Could not locate a valid input field outside of header")

    # 4. Ввод значения с очисткой
    driver.execute_script("arguments[0].scrollIntoView({{block: 'center'}});", target_input)
    time.sleep(0.5)

    try:
        target_input.click()
    except:
        driver.execute_script("arguments[0].click();", target_input)

    target_input.clear()

    # Эмуляция посимвольного ввода для React/Vue форм
    target_input.send_keys("{field_value}")

    # Проверка (Assertion)
    val = target_input.get_attribute("value")
    if val != "{field_value}":
        print(f"⚠️ Value mismatch via send_keys. Trying JS set.")
        driver.execute_script("arguments[0].value = '{field_value}'; arguments[0].dispatchEvent(new Event('input', {{ bubbles: true }}));", target_input)

    print(f"✅ Document name successfully filled: {field_value}")

except Exception as e:
    print(f"❌ Error filling document name: {{str(e)}}")
    raise e
"""

        elif field_name == "document_language":
            return f"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

wait = WebDriverWait(driver, 15)
try:
    print(f"🔄 Selecting language: {field_value}")
    # Ищем dropdown, исключая хедер
    dropdowns = driver.find_elements(By.CSS_SELECTOR, ".vs__dropdown-toggle, [role='combobox'], .g-select-search__wrapper, select")

    target_dd = None
    for dd in dropdowns:
        # Простая проверка: дропдаун не должен быть в хедере
        try:
            dd.find_element(By.XPATH, "./ancestor::header")
            continue 
        except: 
            if dd.is_displayed():
                target_dd = dd
                break

    if target_dd:
        driver.execute_script("arguments[0].scrollIntoView({{block: 'center'}});", target_dd)
        driver.execute_script("arguments[0].click();", target_dd)
        time.sleep(1)

        # Клик по опции
        xpath = f"//li[contains(text(), '{{field_value}}')] | //div[contains(text(), '{{field_value}}')] | //option[contains(text(), '{{field_value}}')]"
        option = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        option.click()
        print(f"✅ Language selected")
    else:
        print("❌ Language dropdown not found")
except Exception as e:
    print(f"❌ Error selecting language: {{e}}")
"""

        else:
            return f"""
# Заполнение поля {field_name} значением {field_value}
print(f"Filling field {{field_name}} with value {{field_value}}")
"""

    def _generate_continue_button_code(self, context: PageContext) -> str:
        """Генерирует код для нажатия кнопки Continue"""
        return """
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time

wait = WebDriverWait(driver, 15)

try:
    # Сначала пробуем CSS селекторы
    continue_css_selectors = [
        "button[type='submit']",
        "input[type='submit']", 
        "button.btn-primary",
        "button.btn"
    ]

    # Затем XPath селекторы
    continue_xpath_selectors = [
        "//button[contains(text(), 'Continue')]",
        "//button[contains(text(), 'Submit')]",
        "//button[contains(text(), 'Next')]",
        "//button[contains(text(), 'Create')]",
        "//input[@value='Continue']",
        "//input[@value='Submit']",
        "//input[@value='Next']"
    ]

    continue_button = None

    # Пробуем CSS селекторы
    for selector in continue_css_selectors:
        try:
            continue_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            break
        except TimeoutException:
            continue

    # Если CSS не сработал, пробуем XPath
    if not continue_button:
        for xpath in continue_xpath_selectors:
            try:
                continue_button = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                break
            except TimeoutException:
                continue

    if continue_button:
        driver.execute_script("arguments[0].scrollIntoView(true);", continue_button)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", continue_button)
        print("✅ Continue button clicked successfully")
    else:
        print("❌ Continue button not found")

except Exception as e:
    print(f"❌ Error clicking continue button: {e}")
"""

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