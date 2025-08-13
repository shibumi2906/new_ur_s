from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
from models import PageContext, PageState, AgentAction

class PromptGeneratorAgent:
    """Агент для генерации промптов для LLM"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=Config.LLM_MODEL,
            temperature=0.3,
            api_key=Config.OPENAI_API_KEY
        )
        self.model = self.llm  # Алиас для совместимости
    
    def generate_action_prompt(self, context: PageContext, state: PageState, has_user_data: bool = False, user_responses: List[Dict] = None) -> str:
        """Генерирует промпт для выполнения действия"""
        
        # Логируем HTML для отладки
        html_preview = context.body_html[:500] + "..." if len(context.body_html) > 500 else context.body_html
        print(f"🔍 HTML PREVIEW (first 500 chars): {html_preview}")
        print(f"🔍 HTML LENGTH: {len(context.body_html)}")
        print(f"🔍 FULL HTML (first 2000 chars): {context.body_html[:2000]}")
        print(f"🔍 HTML CONTAINS 'Documents': {'Documents' in context.body_html}")
        print(f"🔍 HTML CONTAINS 'documents': {'documents' in context.body_html.lower()}")
        
        base_prompt = f"""
        Я уже заполнил "driver.get(url)", и мой драйвер открыт.
        Твоя задача написать код python используя Selenium 4+ для выполнения текущего шага.
        
        Текущее состояние: {state}
        URL: {context.current_url}
        Title: {context.title}
        
        Код текущей страницы, на которой мы находимся: {context.body_html}
        """
        
        if state == PageState.LOGIN:
            return self._generate_login_prompt(base_prompt, context)
        elif state == PageState.PAGE_1:
            return self._generate_page1_prompt(base_prompt, context)
        elif state == PageState.DOCUMENTS_PAGE:
            # Если мы на странице выбора опций, генерируем промпт на "Create from template"
            if "/create-contract/options" in context.current_url:
                return self._generate_create_from_template_prompt(base_prompt, context)
            return self._generate_documents_page_prompt(base_prompt, context)
        elif state == PageState.CREATE_FROM_TEMPLATE:
            return self._generate_create_from_template_prompt(base_prompt, context)
        elif state == PageState.PRELIMINARY_DATA:
            if has_user_data and user_responses:
                return self._generate_preliminary_form_filling_prompt(base_prompt, context, user_responses)
            else:
                return self._generate_preliminary_data_prompt(base_prompt, context)
        elif state == PageState.TEMPLATE_SELECTION:
            return self._generate_template_selection_prompt(base_prompt, context)
        elif state == PageState.CREATE_FROM_TEMPLATE or state == PageState.DOCUMENT_FILLING:
            return self._generate_filling_prompt(base_prompt, context)
        else:
            return self._generate_navigation_prompt(base_prompt, context)
    
    def _generate_login_prompt(self, base_prompt: str, context: PageContext) -> str:
        """Генерирует промпт для авторизации"""
        return f"""
        {base_prompt}
        
        **Требования для авторизации:** 
        - Используй только мой уже открытый драйвер driver.get(url)
        - Не используй переходы по разным ссылкам, взаимодействуй только с элементами страницы.
        - Войдите в систему с помощью электронной почты и пароля: 
        используй только "credentials['email']" и "credentials['password']", которые я уже определил
        - Первое, что нужно сделать в коде каждого шага, это проверить, 
        есть ли на сайте всплывающее окно или модальный режим, если они есть, 
        закройте их или нажмите "Показать мне позже", если их нет на сайте, выполните основной код шага.
        - Используйте универсальные методы нажатия на нужный элемент или кнопку который будет работать даже если элемент вложенный
        - Базовый URL сайта https://app.conneto.com/
        - Не закрывайте драйвер
        - Использовать явные ожидания (WebDriverWait до 15 секунд)
        - Используй CSS_SELECTOR для поиска элементов
        - Используйте обработку исключений
        - Всегда используйте мой уже открытый "driver.get(url)"
        - Не забудьте закрыть скобки в сгенерированном коде
        - Учетные данные доступны через credentials['email'] и credentials['password']
        
        **ПРИМЕР КОДА ДЛЯ ВХОДА:**
        ```python
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException
        import time
        
        wait = WebDriverWait(driver, 15)
        
        try:
            # Закрываем модальные окна если есть
            modal_patterns = [
                "//button[contains(text(), 'Close')]",
                "//button[contains(text(), 'Dismiss')]",
                "//button[contains(text(), 'Not Now')]",
                "//button[contains(text(), 'Show me later')]"
            ]
            
            for pattern in modal_patterns:
                try:
                    modal_button = driver.find_element(By.XPATH, pattern)
                    modal_button.click()
                    time.sleep(1)
                    break
                except:
                    continue
            
            # Находим поле email
            email_input = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email']")))
            email_input.clear()
            email_input.send_keys(credentials['email'])
            
            # Находим поле password
            password_input = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
            password_input.clear()
            password_input.send_keys(credentials['password'])
            
            # Находим кнопку входа
            login_button_patterns = [
                "//button[contains(text(), 'Log in')]",
                "//button[contains(text(), 'Sign in')]",
                "//button[contains(text(), 'Login')]",
                "//button[contains(@class, 'btn__first')]",
                "//button[@type='submit']",
                "//input[@type='submit']",
                "//button[contains(@class, 'login')]",
                "//button[contains(@class, 'signin')]"
            ]
            
            login_clicked = False
            for pattern in login_button_patterns:
                try:
                    login_button = wait.until(EC.element_to_be_clickable((By.XPATH, pattern)))
                    login_button.click()
                    login_clicked = True
                    print("Login button clicked successfully")
                    break
                except:
                    continue
            
            if not login_clicked:
                raise NoSuchElementException("Login button not found")
                
        except Exception as e:
            print(f"Login error: {{e}}")
        ```
        """
    
    def _generate_page1_prompt(self, base_prompt: str, context: PageContext) -> str:
        """Генерирует промпт для Page 1 (Home страница) - найти кнопку Documents"""
        return f"""
        {base_prompt}
        
        **IMPORTANT: We are on Page 1 (Home). We need to find only the "Documents" button in the left menu!**
        
        **Current task:** Find and click the "Documents" button in the left navigation menu
        
        **Navigation requirements:** 
        - Use only my already opened driver driver.get(url)
        - Do not use navigation to different links, interact only with page elements
        - First thing to do in each step code is to check if there are popup windows or modal mode on the site, if they exist, 
        close them or click "Show me later", if they don't exist on the site, execute the main step code
        - Use universal methods of clicking on the desired element or button that will work even if the element is nested
        - Base URL of the site https://app.conneto.com/
        - Do not close the driver
        - Use explicit waits (WebDriverWait up to 15 seconds)
        - Use XPath to search for elements by text
        - Do not consider the search field as a data entry field
        - Do not send Python code and questions in one answer
        - Use exception handling
        - Always use my already opened "driver.get(url)"
        - Do not forget to close brackets in the generated code
        
        **CRITICAL DEBUGGING FIRST:**
        - Print current page title and URL
        - List all clickable elements on the page
        - Look specifically in the left sidebar area
        
        **XPath EXAMPLES for finding the "Documents" button (try in this order):**
        1. //a[contains(text(), "Documents")]
        2. //span[contains(text(), "Documents")]
        3. //div[contains(text(), "Documents")]
        4. //li[contains(text(), "Documents")]
        5. //*[contains(text(), "Documents")]
        6. //nav//a[contains(text(), "Documents")]
        7. //aside//a[contains(text(), "Documents")]
        8. //div[contains(@class, "sidebar")]//a[contains(text(), "Documents")]
        9. //div[contains(@class, "menu")]//a[contains(text(), "Documents")]
        10. //button[contains(text(), "Documents")]
        11. //*[contains(@class, "nav")]//*[contains(text(), "Documents")]
        12. //*[contains(@class, "menu")]//*[contains(text(), "Documents")]
        13. //*[contains(@class, "navigation")]//*[contains(text(), "Documents")]
        14. //*[contains(@class, "sidebar")]//*[contains(text(), "Documents")]
        15. //*[contains(@class, "left")]//*[contains(text(), "Documents")]
        16. //*[contains(@class, "menu-item")]//*[contains(text(), "Documents")]
        17. //*[contains(@class, "nav-item")]//*[contains(text(), "Documents")]
        18. //*[contains(@class, "sidebar")]//*[contains(text(), "Documents")]
        19. //*[contains(@class, "left-panel")]//*[contains(text(), "Documents")]
        20. //*[contains(@class, "left-menu")]//*[contains(text(), "Documents")]
        21. //*[contains(@class, "side-menu")]//*[contains(text(), "Documents")]
        22. //*[contains(@class, "main-menu")]//*[contains(text(), "Documents")]
        23. //*[contains(@class, "primary-nav")]//*[contains(text(), "Documents")]
        24. //*[contains(@class, "secondary-nav")]//*[contains(text(), "Documents")]
        25. //*[contains(@class, "header")]//*[contains(text(), "Documents")]
        26. //*[contains(@class, "footer")]//*[contains(text(), "Documents")]
        27. //*[contains(@class, "toolbar")]//*[contains(text(), "Documents")]
        28. //*[contains(@class, "breadcrumb")]//*[contains(text(), "Documents")]
        29. //*[contains(@class, "tabs")]//*[contains(text(), "Documents")]
        30. //*[contains(@class, "tab")]//*[contains(text(), "Documents")]
        
        **CSS SELECTOR EXAMPLES (alternative approach):**
        1. a[href*="documents"]
        2. [data-testid*="documents"]
        3. [aria-label*="Documents"]
        4. [title*="Documents"]
        5. .sidebar a[href*="documents"]
        6. .nav a[href*="documents"]
        7. .menu a[href*="documents"]
        8. .left-panel a[href*="documents"]
        9. .left-menu a[href*="documents"]
        10. .side-menu a[href*="documents"]
        
        **SPECIFIC SITE SELECTORS (try these first):**
        1. //a[contains(@href, "/contracts")]
        2. //a[contains(@href, "/documents")]
        3. //a[contains(@href, "contracts")]
        4. //a[contains(@href, "documents")]
        5. //*[contains(@class, "sidebar")]//a[contains(@href, "/contracts")]
        6. //*[contains(@class, "sidebar")]//a[contains(@href, "/documents")]
        7. //*[contains(@class, "left")]//a[contains(@href, "/contracts")]
        8. //*[contains(@class, "left")]//a[contains(@href, "/documents")]
        
        **CRITICAL:** 
        - Try multiple XPath patterns in a loop with try-except blocks
        - If XPath fails, try CSS selectors
        - Check for both exact text "Documents" and partial matches
        - Look for elements in left sidebar, navigation, menu areas
        - Don't give up after the first failure!
        - Print the current page title and URL for debugging
        - List all clickable elements found on the page
        - Try clicking on any element that contains "contract" or "document" in href
        """
    
    def _generate_documents_page_prompt(self, base_prompt: str, context: PageContext) -> str:
        """Генерирует промпт для страницы документов - найти кнопку New Document"""
        return f"""
        {base_prompt}
        
        **IMPORTANT: We are on Documents Page. We need to find and click the "New Document" button!**
        
        **Current task:** Find and click the "New Document" button to start creating a document
        
        **Navigation requirements:** 
        - Use only my already opened driver driver.get(url)
        - Do not use navigation to different links, interact only with page elements
        - First thing to do in each step code is to check if there are popup windows or modal mode on the site, if they exist, 
        close them or click "Show me later", if they don't exist on the site, execute the main step code
        - Use universal methods of clicking on the desired element or button that will work even if the element is nested
        - Base URL of the site https://app.conneto.com/
        - Do not close the driver
        - Use explicit waits (WebDriverWait up to 10 seconds)
        - Use XPath to search for elements by text
        - Do not consider the search field as a data entry field
        - Do not send Python code and questions in one answer
        - Use exception handling
        - Always use my already opened "driver.get(url)"
        - Do not forget to close brackets in the generated code
        
        **XPath EXAMPLES for finding the "New Document" button (try in this order):**
        1. //button[contains(text(), "New document")]  # Обратите внимание на строчную букву
        2. //button[contains(text(), "New Document")]
        3. //a[contains(text(), "New document")]
        4. //a[contains(text(), "New Document")]
        5. //span[contains(text(), "New document")]
        6. //div[contains(text(), "New document")]
        7. //*[contains(text(), "New document") and not(ancestor::tr)]  # Исключаем элементы в таблице
        8. //button[contains(text(), "Create")]
        9. //a[contains(text(), "Create")]
        10. //button[contains(text(), "Add")]
        11. //a[contains(text(), "Add")]
        12. //*[contains(@class, "new")]//*[contains(text(), "document")]
        13. //*[contains(@class, "create")]//*[contains(text(), "document")]
        14. //*[contains(@class, "add")]//*[contains(text(), "document")]
        15. //*[contains(@data-testid, "new")]//*[contains(text(), "document")]
        16. //*[contains(@aria-label, "New document")]
        17. //*[contains(@title, "New document")]
        
        **CSS SELECTOR EXAMPLES (alternative approach):**
        1. button[data-testid*="new"]
        2. a[href*="create"]
        3. button.new-document
        4. .create-button
        5. .add-document
        6. [data-testid*="new-document"]
        7. [aria-label*="New Document"]
        8. [title*="New Document"]
        
        **CRITICAL:** 
        - Try multiple XPath patterns in a loop with try-except blocks
        - If XPath fails, try CSS selectors
        - Check for both exact text "New Document" and partial matches like "Create", "Add"
        - Look for buttons, links, and clickable elements
        - Don't give up after the first failure!
        - Print the current page title and URL for debugging
        - List all clickable elements found on the page
        - **ВАЖНО: НЕ кликайте на документы в списке! Ищите только кнопку "New document"**
        - **Исключайте элементы в таблице документов (ancestor::tr)**
        - **Кнопка "New document" должна быть отдельной кнопкой, а не элементом в списке документов**
        """
    
    def _generate_preliminary_data_prompt(self, base_prompt: str, context: PageContext) -> str:
        """Генерирует промпт для предварительных данных - запрос информации у пользователя"""
        return f"""
        {base_prompt}
        
        **КРИТИЧЕСКИ ВАЖНО: МЫ НА СТРАНИЦЕ ПРЕДВАРИТЕЛЬНЫХ ДАННЫХ!**
        
        **ВАША ЕДИНСТВЕННАЯ ЗАДАЧА:** ЗАПРОСИТЬ данные у пользователя через секцию ```questions```
        
        **ЗАПРЕЩЕНО:**
        - ❌ Заполнять форму автоматически
        - ❌ Генерировать код Python для заполнения полей
        - ❌ Нажимать кнопки на странице
        - ❌ Выполнять любые действия с формой
        
        **ОБЯЗАТЕЛЬНО:**
        - ✅ Сгенерировать секцию ```questions``` с вопросами
        - ✅ Запросить информацию у пользователя
        - ✅ Дождаться ответов пользователя
        
        **ВАЖНО О ПОЛЯХ ФОРМЫ:**
        - Поля формы заполняются данными, полученными от юриста
        - Юрист транслирует вопросы из формы пользователю
        - Юрист получает ответы пользователя и передает их для заполнения полей
        - Юрист может вступить в диалог, если пользователь что-то спросит
        
        **ПРИМЕРЫ ВОПРОСОВ ДЛЯ ЗАПРОСА:**
        - Название документа (обязательное)
        - Язык документа (обязательное)
        - Номер документа (необязательное - спрашивать только если нужно)
        - Проект (необязательное - спрашивать только если нужно)
        
        **ВАЖНО О НЕОБЯЗАТЕЛЬНЫХ ПОЛЯХ:**
        - Необязательные поля можно пропустить
        - Если пользователь не хочет заполнять необязательные поля, не настаивать
        - Сначала собрать обязательные поля, потом спросить о необязательных
        
        **СТРУКТУРА ОТВЕТА (ОБЯЗАТЕЛЬНО):**
        ```
        questions
        Вопрос 1: Какое название документа вам нужно? (обязательное поле)
        Вопрос 2: На каком языке должен быть документ? (обязательное поле)
        Вопрос 3: Нужен ли номер документа? (необязательное поле)
        Вопрос 4: К какому проекту следует добавить документ? (необязательное поле)
        ```
        
        **ВАЖНО:** 
        - ВСЕГДА используйте секцию ```questions```
        - НЕ генерируйте код Python
        - НЕ заполняйте форму
        - ТОЛЬКО вопросы пользователю
        - После получения ответов юрист продолжит разговор для выяснения типа документа
        """
    
    def _generate_create_from_template_prompt(self, base_prompt: str, context: PageContext) -> str:
        """Генерирует промпт для страницы выбора опций - найти кнопку Create from template"""
        return f"""
        {base_prompt}
        
        **ВАЖНО: Мы на странице выбора опций создания документа. Нужно найти кнопку "Create from template"!**
        
        **Текущая задача:** Найти и нажать кнопку "Create from template" на странице выбора опций
        
        **Требования для навигации:** 
        - Используй только мой уже открытый драйвер driver.get(url)
        - Не используй переходы по разным ссылкам, взаимодействуй только с элементами страницы
        - Первое, что нужно сделать в коде каждого шага, это проверить, 
        есть ли на сайте всплывающее окно или модальный режим, если они есть, 
        закройте их или нажмите "Показать мне позже", если их нет на сайте, выполните основной код шага
        - Используйте универсальные методы нажатия на нужный элемент или кнопку который будет работать даже если элемент вложенный
        - Базовый URL сайта https://app.conneto.com/
        - Не закрывайте драйвер
        - Использовать явные ожидания (WebDriverWait до 10 секунд)
        - Используй только XPath для поиска элементов по тексту (НЕ используйте CSS :contains)
        - Не учитывай поле для поиска как поле для заполнения данных
        - Не отправляйте код на Python и вопросы в одном ответе
        - Используйте обработку исключений
        - Всегда используйте мой уже открытый "driver.get(url)"
        - Не забудьте закрыть скобки в сгенерированном коде
        
        **ПРИМЕРЫ XPath для поиска кнопки "Create from template" (попробуй в этом порядке):**
        1. //*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create from template')]/ancestor-or-self::*[self::button or self::a][1]
        2. //button[.//text()[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create from template')]]
        3. //a[.//text()[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create from template')]]
        4. //*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'создать из шаблона')]/ancestor-or-self::*[self::button or self::a][1]
        5. //*[contains(@class,'btn') or contains(@class,'button')]//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'create from template')]
        
        **ВАЖНО:** 
        - Кнопка "Create from template" находится в карточке "Choose a template"
        - Попробуй все варианты XPath в цикле с try-except
        - Если XPath не работает, попробуй CSS селекторы
        - Проверь, что элемент видимый и кликабельный
        - Выведи текущий URL и заголовок страницы для отладки
        - Выведи список всех кликабельных элементов на странице
        - После клика ЖДИ смену URL на /create-contract/details или /create-contract/templates (timeout 15s)
        - Если URL не поменялся — скроль к кнопке, кликни JS (driver.execute_script('arguments[0].click();', el)) и повтори ожидание
        """
    
    def _generate_preliminary_form_filling_prompt(self, base_prompt: str, context: PageContext, user_responses: List[Dict] = None) -> str:
        """Генерирует промпт для заполнения формы предварительных данных"""
        
        # Извлекаем данные из ответов пользователя
        user_data = {}
        if user_responses:
            for response in user_responses:
                question = response.get('question', '').lower()
                answer = response.get('answer', '')
                
                # Заполняем только те поля, на которые пользователь действительно ответил
                if any(keyword in question for keyword in ["название", "наименование", "document name"]):
                    user_data['document_name'] = answer
                elif any(keyword in question for keyword in ["язык", "language"]):
                    user_data['document_language'] = answer
                elif any(keyword in question for keyword in ["номер", "number"]):
                    # Заполняем номер только если пользователь дал конкретный ответ
                    if answer and answer.strip() and answer.lower() not in ["skip", "пропустить", "нет", "no", ""]:
                        user_data['document_number'] = answer
                elif any(keyword in question for keyword in ["проект", "project"]):
                    # Заполняем проект только если пользователь дал конкретный ответ
                    if answer and answer.strip() and answer.lower() not in ["skip", "пропустить", "нет", "no", ""]:
                        user_data['add_to_project'] = answer
        
        user_data_str = "\n".join([f"- {key}: {value}" for key, value in user_data.items()])
        
        return f"""
        {base_prompt}
        
        **КРИТИЧЕСКИ ВАЖНО: МЫ НА СТРАНИЦЕ ПРЕДВАРИТЕЛЬНЫХ ДАННЫХ И У НАС ЕСТЬ ДАННЫЕ ОТ ПОЛЬЗОВАТЕЛЯ!**
        
        **ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:**
        {user_data_str}
        
        **ВАША ЗАДАЧА:** ЗАПОЛНИТЬ форму данными, полученными от пользователя
        
        **ОБЯЗАТЕЛЬНО:**
        - ✅ Заполнить все поля формы данными от пользователя
        - ✅ Нажать кнопку "Continue" после заполнения
        - ✅ Использовать данные из ответов пользователя
        
        **ВАЖНО О ПОЛЯХ ФОРМЫ:**
        - Document name * (обязательное) - использовать ответ пользователя о названии
        - Document language * (обязательное) - использовать ответ пользователя о языке
        - Document number (необязательное) - заполнять ТОЛЬКО если пользователь дал конкретный ответ
        - Add to project (необязательное) - заполнять ТОЛЬКО если пользователь дал конкретный ответ
        
        **КРИТИЧЕСКИ ВАЖНО:**
        - НЕ заполняй поля, которые пользователь не указал
        - НЕ используй значения по умолчанию для необязательных полей
        - Заполняй только те поля, для которых есть данные от пользователя
        
        **КРИТИЧЕСКИ ВАЖНЫЕ ТРЕБОВАНИЯ К КОДУ:**
        - Используй только мой уже открытый драйвер driver.get(url)
        - Не используй переходы по разным ссылкам, взаимодействуй только с элементами страницы
        - Используй явные ожидания (WebDriverWait до 15 секунд)
        - Используй только CSS_SELECTOR
        - Используй обработку исключений для каждого элемента
        - После заполнения всех полей найди и нажми кнопку "Continue"
        
        **ОСОБЫЕ ТРЕБОВАНИЯ ДЛЯ DROPDOWN (Document language):**
        - Для dropdown используй JavaScript клик: driver.execute_script("arguments[0].click();", element)
        - Если dropdown не открывается, попробуй найти input внутри dropdown и ввести текст напрямую
        - Для dropdown ищи селекторы: ".vs__dropdown-toggle", "[role='combobox']", ".g-select-search__wrapper"
        - После клика на dropdown жди появления опций и кликай на нужную опцию
        - НИКОГДА не используй пустые строки в селекторах опций
        - Всегда проверяй наличие данных перед генерацией селекторов
        
        **ОСОБЫЕ ТРЕБОВАНИЯ ДЛЯ ПЕРЕКРЫТИЙ ЭЛЕМЕНТОВ:**
        - Если элемент перекрыт, используй JavaScript для скролла к элементу: driver.execute_script("arguments[0].scrollIntoView(true);", element)
        - Добавь паузу после скролла: time.sleep(1)
        - Используй JavaScript клик вместо обычного: driver.execute_script("arguments[0].click();", element)
        - Если элемент все еще не кликается, попробуй найти родительский элемент и кликнуть по нему
        
        **СТРУКТУРА КОДА:**
        ```python
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
        import time
        
        wait = WebDriverWait(driver, 15)
        
        # Данные пользователя (заполнять только те, которые есть)
        document_name = user_data.get('document_name', '')
        document_language = user_data.get('document_language', '')
        document_number = user_data.get('document_number', '')  # Только если пользователь указал
        add_to_project = user_data.get('add_to_project', '')  # Только если пользователь указал
        
        try:
            # 1. Заполнить Document name (обязательное) - ТОЛЬКО если есть данные
            if document_name and document_name.strip():
                try:
                    # Попробуем разные селекторы для поля Document name
                    selectors = [
                        "input[placeholder*='Document name']",
                        "input[name*='document']",
                        "input[name*='name']",
                        "input[placeholder*='name']",
                        "input[type='text']"
                    ]
                    document_name_input = None
                    for selector in selectors:
                        try:
                            document_name_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                            break
                        except TimeoutException:
                            continue
                    
                    if document_name_input:
                        document_name_input.clear()
                        document_name_input.send_keys(document_name)
                        print(f"Document name filled: {{user_data.get('document_name', '')}}")
                    else:
                        print("Document name input not found with any selector")
                except Exception as e:
                    print(f"Error filling document name: {{e}}")
            
            # 2. Заполнить Document language (обязательное) - ТОЛЬКО если есть данные
            if document_language and document_language.strip():
                try:
                    # Попробуем разные селекторы для dropdown
                    dropdown_selectors = [
                        ".vs__dropdown-toggle",
                        "[role='combobox']",
                        ".g-select-search__wrapper",
                        "select",
                        ".dropdown-toggle"
                    ]
                    
                    language_dropdown = None
                    for selector in dropdown_selectors:
                        try:
                            language_dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                            break
                        except TimeoutException:
                            continue
                    
                    if language_dropdown:
                        # Кликаем на dropdown
                        driver.execute_script("arguments[0].click();", language_dropdown)
                        time.sleep(1)
                        
                        # Ищем опцию с нужным языком
                        option_selectors = [
                                                    f"li[role='option']:contains('{{document_language}}')",
                        f"option:contains('{{document_language}}')",
                        f"[role='option']:contains('{{document_language}}')",
                        f"li:contains('{{document_language}}')"
                        ]
                        
                        language_option = None
                        for selector in option_selectors:
                            try:
                                language_option = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                                break
                            except TimeoutException:
                                continue
                        
                        if language_option:
                            driver.execute_script("arguments[0].click();", language_option)
                            print(f"Document language selected: {{user_data.get('document_language', '')}}")
                        else:
                            print(f"Language option '{{user_data.get('document_language', '')}}' not found")
                    else:
                        print("Document language dropdown not found")
                except Exception as e:
                    print(f"Error filling document language: {{e}}")
            
            # 3. Заполнить Document number (ТОЛЬКО если есть данные)
            if document_number and document_number.strip():
                try:
                    number_selectors = [
                        "input[placeholder*='Document number']",
                        "input[name*='number']",
                        "input[placeholder*='number']"
                    ]
                    document_number_input = None
                    for selector in number_selectors:
                        try:
                            document_number_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                            break
                        except TimeoutException:
                            continue
                    
                    if document_number_input:
                        document_number_input.clear()
                        document_number_input.send_keys(document_number)
                        print(f"Document number filled: {{user_data.get('document_number', '')}}")
                    else:
                        print("Document number input not found")
                except Exception as e:
                    print(f"Error filling document number: {{e}}")
            
            # 4. Заполнить Add to project (ТОЛЬКО если есть данные)
            if add_to_project and add_to_project.strip():
                try:
                    project_selectors = [
                        "input[placeholder*='Add to project']",
                        "input[name*='project']",
                        "input[placeholder*='project']"
                    ]
                    add_to_project_input = None
                    for selector in project_selectors:
                        try:
                            add_to_project_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                            break
                        except TimeoutException:
                            continue
                    
                    if add_to_project_input:
                        add_to_project_input.clear()
                        add_to_project_input.send_keys(add_to_project)
                        print(f"Add to project filled: {{user_data.get('add_to_project', '')}}")
                    else:
                        print("Add to project input not found")
                except Exception as e:
                    print(f"Error filling add to project: {{e}}")
            
            # 5. Нажать кнопку "Continue"
            try:
                continue_selectors = [
                    "button:contains('Continue')",
                    "button[type='submit']",
                    "input[type='submit']",
                    "button.btn-primary",
                    "button.btn",
                    "button:contains('Submit')",
                    "button:contains('Next')",
                    "button:contains('Create')"
                ]
                
                continue_button = None
                for selector in continue_selectors:
                    try:
                        continue_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                        break
                    except TimeoutException:
                        continue
                
                if continue_button:
                    # Скроллим к кнопке и кликаем
                    driver.execute_script("arguments[0].scrollIntoView(true);", continue_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", continue_button)
                    print("Continue button clicked successfully")
                else:
                    print("Continue button not found with any selector")
            except Exception as e:
                print(f"Error clicking continue button: {{e}}")
                
        except Exception as e:
            print(f"General error: {{e}}")
        ```
        
        **ВАЖНО:** 
        - НЕ генерируй секцию ```questions```
        - Генерируй ТОЛЬКО код Python для заполнения формы
        - Используй данные из ответов пользователя
        - После заполнения обязательно нажми "Continue"
        - Обрабатывай каждое поле отдельно с try-except
        - ПРОВЕРЯЙ наличие данных перед заполнением ЛЮБЫХ полей (обязательных и необязательных)
        - НЕ заполняй поля пустыми значениями или значениями по умолчанию
        - Используй множественные селекторы для каждого элемента
        - Добавляй подробное логирование для отладки
        """
    
    def _generate_filling_prompt(self, base_prompt: str, context: PageContext) -> str:
        """Генерирует промпт для заполнения документа"""
        return f"""
        {base_prompt}
        
        **Требования для заполнения документа:**
        - Если нужна дополнительная информация, попросите меня ответить только на вопросы в разделе ````questions```. 
        При формировании вопросов не спрашивайте о коде или технических деталях, 
        запрашивай информацию как юрист - только бизнес‑данные, необходимые для заполнения только текущих имеющихся полей документа.
        Вопросы должны основываться на имеющихся полях на текущей странице, для которых ты собираешь информацию, потому что я не вижу что отображено на сайте по вопросу я должен понять какую именно информация необходимо предоставить, 
        во всех остальных случаях возвращайте только код Python в поле ```python``` соответствует следующему шагу на определенном этапе. 
        
        **ВАЖНЫЕ ПРАВИЛА:**
        - Если мы находимся на этапе предварительных данных, задай вопросы в разделе ```questions``` для сбора данных для идентификации файла
        - Если мы на странице шаблонов - предложи подходящий шаблон, покажи другие только если пользователь захочет
        - При заполнении шаблона ВСЕГДА используй только английский язык в полях формы
        - Общение с пользователем веди на том языке, на котором он отвечает (русский/английский)
        - Если пользователь отвечает на русском - переведи его ответ на английский для заполнения формы
        - Не учитывай поле для поиска "vs__search" как поле для заполнения данных
        - Не отправляйте код на Python и вопросы в одном ответе
        - Используй только мой уже открытый драйвер driver.get(url)
        - Не используй переходы по разным ссылкам, взаимодействуй только с элементами страницы.
        - Используй универсальный метод нажатия на нужный элемент или кнопку который будет работать даже если элемент вложенный (например: //button[.//*[contains(text(), "Create from template")
        - Базовый URL сайта https://app.conneto.com/
        - Не закрывайте драйвер
        - Использовать явные ожидания
        - Используй только CSS_SELECTOR
        - Используйте обработку исключений
        - Всегда используйте мой уже открытый "driver.get(url)"
        - Не забудьте закрыть скобки в сгенерированном коде
        - После сохранения документа покажи путь к папке в логах и диалоге с пользователем
        """
    
    def _generate_navigation_prompt(self, base_prompt: str, context: PageContext) -> str:
        """Генерирует промпт для навигации"""
        
        # Проверяем, находимся ли мы на Page 2 (Documents страница)
        # На сайте используется URL /contracts для страницы Documents
        if "/documents" in context.current_url or "/contracts" in context.current_url:
            return f"""
            {base_prompt}
            
            **ВАЖНО: Мы на странице 2 (Documents). Нужно найти кнопку "New Document"!**
            
            **Текущая задача:** Найти и нажать кнопку "New Document" или "+ New Document" на странице Documents
            
            **Требования для навигации:** 
            - Используй только мой уже открытый драйвер driver.get(url)
            - Не используй переходы по разным ссылкам, взаимодействуй только с элементами страницы
            - Первое, что нужно сделать в коде каждого шага, это проверить, 
            есть ли на сайте всплывающее окно или модальный режим, если они есть, 
            закройте их или нажмите "Показать мне позже", если их нет на сайте, выполните основной код шага
            - Используйте универсальные методы нажатия на нужный элемент или кнопку который будет работать даже если элемент вложенный
            - Базовый URL сайта https://app.conneto.com/
            - Не закрывайте драйвер
            - Использовать явные ожидания (WebDriverWait до 10 секунд)
            - Используй XPath для поиска элементов по тексту
            - Не учитывай поле для поиска как поле для заполнения данных
            - Не отправляйте код на Python и вопросы в одном ответе
            - Используйте обработку исключений
            - Всегда используйте мой уже открытый "driver.get(url)"
            - Не забудьте закрыть скобки в сгенерированном коде
            
            **ПРИМЕРЫ XPath для поиска кнопки "New Document" (попробуй в этом порядке):**
            1. //button[contains(text(), "+ New document")]
            2. //button[contains(text(), "New document")]
            3. //button[contains(text(), "New Document")]
            4. //button[contains(text(), "+ New Document")]
            5. //a[contains(text(), "New document")]
            6. //a[contains(text(), "New Document")]
            7. //span[contains(text(), "New document")]
            8. //span[contains(text(), "New Document")]
            9. //*[contains(text(), "New document")]
            10. //*[contains(text(), "New Document")]
            11. //button[.//*[contains(text(), "New document")]]
            12. //button[.//*[contains(text(), "New Document")]]
            13. //*[contains(@class, "btn")]//*[contains(text(), "New document")]
            14. //*[contains(@class, "button")]//*[contains(text(), "New document")]
            15. //*[contains(@class, "primary")]//*[contains(text(), "New document")]
            16. //*[contains(@class, "action")]//*[contains(text(), "New document")]
            17. //*[contains(@class, "create")]//*[contains(text(), "New document")]
            18. //*[contains(@class, "add")]//*[contains(text(), "New document")]
            
            **CSS SELECTOR EXAMPLES (альтернативный подход):**
            1. button:contains("New document")
            2. button:contains("+ New document")
            3. a:contains("New document")
            4. [data-testid*="new-document"]
            5. [aria-label*="New document"]
            6. [title*="New document"]
            7. .btn:contains("New document")
            8. .button:contains("New document")
            9. .primary:contains("New document")
            10. .action:contains("New document")
            
            **ВАЖНО:** 
            - Кнопка "New document" обычно находится в правом верхнем углу страницы
            - Попробуй все варианты XPath в цикле с try-except
            - Если XPath не работает, попробуй CSS селекторы
            - Проверь, что элемент видимый и кликабельный
            """
        
        # Проверяем, находимся ли мы на странице выбора опций создания документа
        if "/create-contract/options" in context.current_url:
            return f"""
            {base_prompt}
            
            **ВАЖНО: Мы на странице выбора опций создания документа. Нужно найти кнопку "Create from template"!**
            
            **Текущая задача:** Найти и нажать кнопку "Create from template" на странице выбора опций
            
            **Требования для навигации:** 
            - Используй только мой уже открытый драйвер driver.get(url)
            - Не используй переходы по разным ссылкам, взаимодействуй только с элементами страницы
            - Первое, что нужно сделать в коде каждого шага, это проверить, 
            есть ли на сайте всплывающее окно или модальный режим, если они есть, 
            закройте их или нажмите "Показать мне позже", если их нет на сайте, выполните основной код шага
            - Используйте универсальные методы нажатия на нужный элемент или кнопку который будет работать даже если элемент вложенный
            - Базовый URL сайта https://app.conneto.com/
            - Не закрывайте драйвер
            - Использовать явные ожидания (WebDriverWait до 10 секунд)
            - Используй XPath для поиска элементов по тексту
            - Не учитывай поле для поиска как поле для заполнения данных
            - Не отправляйте код на Python и вопросы в одном ответе
            - Используйте обработку исключений
            - Всегда используйте мой уже открытый "driver.get(url)"
            - Не забудьте закрыть скобки в сгенерированном коде
            
            **ПРИМЕРЫ XPath для поиска кнопки "Create from template" (попробуй в этом порядке):**
            1. //button[contains(text(), "Create from template")]
            2. //button[contains(text(), "Create from Template")]
            3. //button[contains(text(), "create from template")]
            4. //a[contains(text(), "Create from template")]
            5. //span[contains(text(), "Create from template")]
            6. //*[contains(text(), "Create from template")]
            7. //button[.//*[contains(text(), "Create from template")]]
            8. //*[contains(@class, "btn")]//*[contains(text(), "Create from template")]
            9. //*[contains(@class, "button")]//*[contains(text(), "Create from template")]
            10. //*[contains(@class, "primary")]//*[contains(text(), "Create from template")]
            11. //*[contains(@class, "action")]//*[contains(text(), "Create from template")]
            12. //*[contains(@class, "template")]//*[contains(text(), "Create from template")]
            13. //*[contains(@class, "create")]//*[contains(text(), "Create from template")]
            14. //*[contains(@class, "option")]//*[contains(text(), "Create from template")]
            
            **CSS SELECTOR EXAMPLES (альтернативный подход):**
            1. button:contains("Create from template")
            2. a:contains("Create from template")
            3. [data-testid*="create-template"]
            4. [aria-label*="Create from template"]
            5. [title*="Create from template"]
            6. .btn:contains("Create from template")
            7. .button:contains("Create from template")
            8. .primary:contains("Create from template")
            9. .action:contains("Create from template")
            10. .template:contains("Create from template")
            
            **ВАЖНО:** 
            - Кнопка "Create from template" находится в карточке "Choose a template"
            - Попробуй все варианты XPath в цикле с try-except
            - Если XPath не работает, попробуй CSS селекторы
            - Проверь, что элемент видимый и кликабельный
            - Выведи текущий URL и заголовок страницы для отладки
            - Выведи список всех кликабельных элементов на странице
            """
        
        return f"""
        {base_prompt}
        
        **ФИНАЛЬНЫЙ АЛГОРИТМ ДЕЙСТВИЙ (ВАЖНО СЛЕДОВАТЬ ПОШАГОВО):**
        1. Если мы на странице 1 (Home) - найти и нажать "Documents" в левом меню
        2. Если мы на странице 2 (Documents) - найти и нажать кнопку "New Document" или "+ New Document" справа
        3. Если мы на странице создания документа - выбрать "Create from template"
        4. Если мы на странице предварительных данных - ЗАПРОСИТЬ ПРЕДВАРИТЕЛЬНЫЕ ДАННЫЕ у пользователя для идентификации файла
        5. Если мы на странице шаблонов - предложить подходящий шаблон, показать другие только если пользователь захочет
        6. Если мы на странице заполнения - заполнять шаблон на английском языке, общаться с пользователем на его языке
        7. После заполнения - сохранить документ и показать путь к папке
        
        **Требования для навигации:** 
        - Используй только мой уже открытый драйвер driver.get(url)
        - Не используй переходы по разным ссылкам, взаимодействуй только с элементами страницы
        - Первое, что нужно сделать в коде каждого шага, это проверить, 
        есть ли на сайте всплывающее окно или модальный режим, если они есть, 
        закройте их или нажмите "Показать мне позже", если их нет на сайте, выполните основной код шага
        - Используйте универсальные методы нажатия на нужный элемент или кнопку который будет работать даже если элемент вложенный
        - Базовый URL сайта https://app.conneto.com/
        - Не закрывайте драйвер
        - Использовать явные ожидания (WebDriverWait до 10 секунд)
        - Используй XPath для поиска элементов по тексту
        - Не учитывай поле для поиска как поле для заполнения данных
        - Не отправляйте код на Python и вопросы в одном ответе
        - Используйте обработку исключений
        - Всегда используйте мой уже открытый "driver.get(url)"
        - Не забудьте закрыть скобки в сгенерированном коде
        
        **ПРИМЕРЫ XPath для поиска элементов:**
        - Для "Documents" в меню: //a[contains(text(), "Documents")] или //span[contains(text(), "Documents")]
        - Для "New Document": //button[contains(text(), "New document")] или //button[contains(text(), "+ New document")]
        - Для "Create from template": //button[contains(text(), "Create from template")]
        
        **ВАЖНО:** Если элемент не найден, попробуй разные варианты XPath и проверь, что элемент видимый и кликабельный
        """
    
    def _generate_template_selection_prompt(self, base_prompt: str, context: PageContext) -> str:
        """Генерирует промпт для выбора шаблона - анализ шаблонов и предложение пользователю"""
        return f"""
        {base_prompt}
        
        **КРИТИЧЕСКИ ВАЖНО: МЫ НА СТРАНИЦЕ ВЫБОРА ШАБЛОНОВ!**
        
        **ВАША ЕДИНСТВЕННАЯ ЗАДАЧА:** ПРОАНАЛИЗИРОВАТЬ шаблоны и предложить подходящий пользователю
        
        **ЗАПРЕЩЕНО:**
        - ❌ Автоматически выбирать шаблон
        - ❌ Генерировать код Python для выбора шаблона
        - ❌ Нажимать кнопки на странице без согласия пользователя
        
        **ОБЯЗАТЕЛЬНО:**
        - ✅ Проанализировать названия шаблонов на странице
        - ✅ Предложить подходящий шаблон пользователю
        - ✅ Показать другие шаблоны только если пользователь захочет
        - ✅ Дождаться выбора пользователя
        
        **ВАЖНО О ШАБЛОНАХ:**
        - Юрист анализирует названия шаблонов на странице
        - Юрист предлагает подходящий шаблон на основе предыдущих ответов пользователя
        - Юрист может вступить в диалог для уточнения типа документа
        - Поля шаблона заполняются данными, полученными от юриста
        
        **СТРУКТУРА ОТВЕТА (ОБЯЗАТЕЛЬНО):**
        ```
        questions
        Вопрос 1: Я проанализировал доступные шаблоны. Какой тип документа вам нужен?
        Вопрос 2: [Список доступных шаблонов с описанием]
        Вопрос 3: Какой шаблон вы предпочитаете?
        ```
        
        **ВАЖНО:** 
        - ВСЕГДА используйте секцию ```questions```
        - НЕ генерируйте код Python
        - НЕ выбирайте шаблон автоматически
        - ТОЛЬКО анализ и предложение пользователю
        - Учитывайте предыдущие ответы пользователя для рекомендации
        """
    
    def generate_error_fix_prompt(self, original_code: str, error_message: str, 
                                context: PageContext, initial_prompt: str) -> str:
        """Генерирует промпт для исправления ошибки"""
        return f"""
        I have already completed "driver.get(url)" and my driver is open. Fix the error in this Selenium code:
        
        Original Code: {original_code}
        
        Error: {error_message}
        
        Page Context:
        URL: {context.current_url}
        Title: {context.title}
        HTML: {context.body_html[:2000]}
        Elements: {[elem.dict() for elem in context.elements[:10]]}
        
        Initial Prompt: {initial_prompt}
        
        **CRITICAL REQUIREMENTS:**
        - The error shows that the XPath "//aside//a[contains(text(), 'Documents')]" is not working
        - You MUST try different XPath patterns for finding the "Documents" button
        - Use these alternative XPath patterns in order:
          1. //a[contains(text(), "Documents")]
          2. //span[contains(text(), "Documents")]
          3. //div[contains(text(), "Documents")]
          4. //li[contains(text(), "Documents")]
          5. //*[contains(text(), "Documents")]
          6. //nav//a[contains(text(), "Documents")]
          7. //div[contains(@class, "sidebar")]//a[contains(text(), "Documents")]
          8. //div[contains(@class, "menu")]//a[contains(text(), "Documents")]
          9. //button[contains(text(), "Documents")]
          10. //*[contains(@class, "nav")]//*[contains(text(), "Documents")]
        
        **Error Fix Strategy:**
        - Try multiple XPath patterns in a loop
        - Use try-except for each XPath attempt
        - If one XPath fails, try the next one
        - Return only the corrected Python code inside ```python```
        - Don't shorten the code
        - Always use only my already open "driver.get(url)"
        - Use explicit waits with WebDriverWait
        - Include proper error handling
        """
    
    def generate_form_filling_prompt(self, context: PageContext, state: PageState, user_response: Dict[str, Any], memory_summary: str) -> str:
        """Генерирует промпт для заполнения формы с данными пользователя"""
        
        # Разные промпты для разных типов заполнения
        if state == PageState.PRELIMINARY_DATA:
            # НОВАЯ АРХИТЕКТУРА: Обрабатываем данные от LawyerAgent
            try:
                # Пытаемся извлечь данные из строки ответа
                import ast
                user_data_str = user_response.get('answer', '{}')
                if user_data_str.startswith('{') and user_data_str.endswith('}'):
                    user_data = ast.literal_eval(user_data_str)
                else:
                    user_data = {}
            except:
                user_data = {}
            
            base_prompt = f"""
            Я уже заполнил "driver.get(url)", и мой драйвер открыт.
            Твоя задача заполнить форму предварительных данных используя данные от пользователя.
            
            Текущее состояние: PRELIMINARY_DATA
            URL: {context.current_url}
            Title: {context.title}
            
            История действий: {memory_summary}
            
            Код текущей страницы:
            {context.body_html[:3000]}
            """
            
            # Создаем user_responses в нужном формате для существующего метода
            user_responses = []
            for key, value in user_data.items():
                user_responses.append({
                    'question': f'What is the {key}?',
                    'answer': str(value)
                })
            
            print(f"🔍 PROMPT GENERATOR: Created {len(user_responses)} user_responses from {len(user_data)} data items")
            print(f"🔍 PROMPT GENERATOR: user_data = {user_data}")
            print(f"🔍 PROMPT GENERATOR: user_responses = {user_responses}")
            
            return self._generate_preliminary_form_filling_prompt(base_prompt, context, user_responses)
        elif state == PageState.DOCUMENT_FILLING:
            return self._generate_template_filling_prompt(context, user_response, memory_summary)
        else:
            return self._generate_generic_form_filling_prompt(context, state, user_response, memory_summary)
    
    def _generate_template_filling_prompt(self, context: PageContext, user_response: Dict[str, Any], memory_summary: str) -> str:
        """Промпт для заполнения шаблона документа"""
        return f"""
        Я уже заполнил "driver.get(url)", и мой драйвер открыт.
        Твоя задача заполнить шаблон документа используя данные от пользователя.
        
        Текущее состояние: DOCUMENT_FILLING
        URL: {context.current_url}
        Title: {context.title}
        
        Данные от пользователя:
        Вопрос: {user_response.get('question', 'N/A')}
        Ответ: {user_response.get('answer', 'N/A')}
        Юридическая формулировка: {user_response.get('legal_formulation', 'N/A')}
        
        История действий: {memory_summary}
        
        Код текущей страницы:
        {context.body_html[:3000]}
        
        **CRITICAL REQUIREMENTS:**
        - Заполни шаблон документа используя юридическую формулировку из ответа пользователя
        - Найди соответствующие поля шаблона по XPath или CSS селекторам
        - Используй явные ожидания с WebDriverWait
        - После заполнения шаблона нажми кнопку "Save", "Download", "Complete" или аналогичную
        - Верни только Python код внутри ```python```
        - Не сокращай код
        - Всегда используй только мой уже открытый "driver.get(url)"
        - Если есть несколько полей, заполни их все
        - Используй CSS_SELECTOR для поиска элементов
        - Обрабатывай исключения
        - Заполнение должно быть на английском языке
        """
    
    def _generate_generic_form_filling_prompt(self, context: PageContext, state: PageState, user_response: Dict[str, Any], memory_summary: str) -> str:
        """Общий промпт для заполнения формы"""
        return f"""
        Я уже заполнил "driver.get(url)", и мой драйвер открыт.
        Твоя задача заполнить форму на странице используя данные от пользователя.
        
        Текущее состояние: {state}
        URL: {context.current_url}
        Title: {context.title}
        
        Данные от пользователя:
        Вопрос: {user_response.get('question', 'N/A')}
        Ответ: {user_response.get('answer', 'N/A')}
        Юридическая формулировка: {user_response.get('legal_formulation', 'N/A')}
        
        История действий: {memory_summary}
        
        Код текущей страницы:
        {context.body_html[:3000]}
        
        **CRITICAL REQUIREMENTS:**
        - Заполни форму используя юридическую формулировку из ответа пользователя
        - Найди соответствующие поля формы по XPath или CSS селекторам
        - Используй явные ожидания с WebDriverWait
        - После заполнения формы нажми кнопку "Next", "Continue", "Submit" или аналогичную
        - Верни только Python код внутри ```python```
        - Не сокращай код
        - Всегда используй только мой уже открытый "driver.get(url)"
        - Если есть несколько полей, заполни их все
        - Используй CSS_SELECTOR для поиска элементов
        - Обрабатывай исключения
        """
    
    def parse_actions(self, ai_response: str) -> List[AgentAction]:
        """Парсит действия из ответа LLM"""
        actions = []
        
        try:
            # Ищем блоки кода в ответе
            if '```python' in ai_response:
                # Извлекаем код из блоков
                code_blocks = ai_response.split('```python')
                for i, block in enumerate(code_blocks[1:], 1):  # Пропускаем первый элемент (до первого блока)
                    if '```' in block:
                        code = block.split('```')[0].strip()
                        if code:
                            action = AgentAction(
                                action_type=ActionType.EXECUTE_CODE,
                                code=code,
                                description=f"Generated code block {i}"
                            )
                            actions.append(action)
            
            # Если нет блоков кода, но есть код напрямую
            elif 'from selenium' in ai_response or 'driver.' in ai_response:
                # Извлекаем код после маркеров
                lines = ai_response.split('\n')
                code_lines = []
                in_code = False
                
                for line in lines:
                    if any(marker in line for marker in ['from selenium', 'driver.', 'WebDriverWait', 'try:', 'except:']):
                        in_code = True
                    if in_code:
                        code_lines.append(line)
                
                if code_lines:
                    code = '\n'.join(code_lines)
                    action = AgentAction(
                        action_type=ActionType.EXECUTE_CODE,
                        code=code,
                        description="Extracted code from response"
                    )
                    actions.append(action)
            
            # Если нет кода, но есть инструкции
            else:
                action = AgentAction(
                    action_type=ActionType.INSTRUCTION,
                    code="",
                    description=ai_response[:200] + "..." if len(ai_response) > 200 else ai_response
                )
                actions.append(action)
                
        except Exception as e:
            # В случае ошибки создаем действие с исходным ответом
            action = AgentAction(
                action_type=ActionType.INSTRUCTION,
                code="",
                description=f"Error parsing actions: {str(e)}. Original response: {ai_response[:100]}..."
            )
            actions.append(action)
        
        return actions