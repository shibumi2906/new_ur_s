from typing import Dict, Any
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
    
    def generate_action_prompt(self, context: PageContext, state: PageState, 
                               memory_summary: str, user_responses: str = "") -> str:
        """Генерирует промпт для выполнения действия"""
        
        # Логируем HTML для отладки
        html_preview = context.body_html[:500] + "..." if len(context.body_html) > 500 else context.body_html
        print(f"🔍 HTML PREVIEW (first 500 chars): {html_preview}")
        print(f"🔍 HTML LENGTH: {len(context.body_html)}")
        
        base_prompt = f"""
        Я уже заполнил "driver.get(url)", и мой драйвер открыт.
        Твоя задача написать код python используя Selenium 4+ для выполнения текущего шага.
        
        Текущее состояние: {state}
        URL: {context.current_url}
        Title: {context.title}
        
        Код текущей страницы, на которой мы находимся: {context.body_html}
        
        История действий и контекст:
        {memory_summary}
        
        {user_responses}
        """
        
        if state == PageState.LOGIN:
            return self._generate_login_prompt(base_prompt, context)
        elif state == PageState.PAGE_1:
            return self._generate_page1_prompt(base_prompt, context)
        elif state == PageState.PRELIMINARY_DATA or state == PageState.CREATE_FROM_TEMPLATE or state == PageState.TEMPLATE_SELECTION or state == PageState.DOCUMENT_FILLING:
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
        - Используйте универсальные методы нажатия на нужный элемент или кнопку который будет работать даже если элемент вложенный (например: //button[.//*[contains(text(), "Create from template")
        - Базовый URL сайта https://app.conneto.com/
        - Не закрывайте драйвер
        - Использовать явные ожидания
        - Используй только CSS_SELECTOR
        - Используйте обработку исключений
        - Всегда используйте мой уже открытый "driver.get(url)"
        - Не забудьте закрыть скобки в сгенерированном коде
        - Учетные данные доступны через credentials['email'] и credentials['password']
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
        - Use explicit waits (WebDriverWait up to 10 seconds)
        - Use XPath to search for elements by text
        - Do not consider the search field as a data entry field
        - Do not send Python code and questions in one answer
        - Use exception handling
        - Always use my already opened "driver.get(url)"
        - Do not forget to close brackets in the generated code
        
        **XPath EXAMPLES for finding the "Documents" button:**
        - //a[contains(text(), "Documents")]
        - //span[contains(text(), "Documents")]
        - //div[contains(text(), "Documents")]
        - //li[contains(text(), "Documents")]
        - //*[contains(text(), "Documents")]
        - //nav//a[contains(text(), "Documents")]
        - //aside//a[contains(text(), "Documents")]
        - //div[contains(@class, "sidebar")]//a[contains(text(), "Documents")]
        - //div[contains(@class, "menu")]//a[contains(text(), "Documents")]
        
        **IMPORTANT:** If the element is not found, try different XPath options and check that the element is visible and clickable
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
        if "/documents" in context.current_url:
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
            
            **ПРИМЕРЫ XPath для поиска кнопки "New Document":**
            - //button[contains(text(), "New Document")]
            - //button[contains(text(), "+ New Document")]
            - //a[contains(text(), "New Document")]
            - //span[contains(text(), "New Document")]
            - //*[contains(text(), "New Document")]
            
            **ВАЖНО:** Если элемент не найден, попробуй разные варианты XPath и проверь, что элемент видимый и кликабельный
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
        - Для "New Document": //button[contains(text(), "New Document")] или //button[contains(text(), "+ New Document")]
        - Для "Create from template": //button[contains(text(), "Create from template")]
        
        **ВАЖНО:** Если элемент не найден, попробуй разные варианты XPath и проверь, что элемент видимый и кликабельный
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
        Elements: {[elem.dict() for elem in context.elements[:5]]}
        
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