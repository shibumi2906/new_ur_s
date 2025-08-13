from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
from models import PageContext, PageState

class NavigatorAgent:
    """Агент для определения текущего состояния страницы"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=Config.LLM_MODEL,
            temperature=0.1,  # Низкая температура для точности
            api_key=Config.OPENAI_API_KEY
        )
    
    def determine_page_state(self, context: PageContext) -> Dict[str, Any]:
        """Определяет текущее состояние страницы и что нужно делать дальше"""
        
        # Проверяем URL для определения Page 1 (Home страница)
        # После входа пользователь может попасть на разные URL: /home, /projects, /dashboard и т.д.
        # НО НЕ /contracts - это уже страница Documents!
        if any(path in context.current_url for path in ["/home", "/projects", "/dashboard"]) or (
            "app.conneto.com" in context.current_url and 
            not any(path in context.current_url for path in ["/login", "/signin", "/documents", "/contracts", "/create-contract"])
        ):
            return {
                "state": PageState.PAGE_1,
                "analysis": "Мы на странице 1 (Home). Нужно найти кнопку 'Documents' в левом меню.",
                "needs_user_input": False,
                "is_authenticated": True
            }
        
        # Проверяем URL для определения страницы авторизации
        if "/login" in context.current_url or "/signin" in context.current_url or "login" in context.current_url.lower():
            return {
                "state": PageState.LOGIN,
                "analysis": "Мы на странице авторизации. Нужно войти в систему.",
                "needs_user_input": False,
                "is_authenticated": False
            }
        
        # Проверяем URL для определения Page 2 (Documents страница)
        # На сайте используется URL /contracts для страницы Documents
        if "/documents" in context.current_url or "/contracts" in context.current_url:
            return {
                "state": PageState.DOCUMENTS_PAGE,
                "analysis": "Мы на странице Documents. Нужно найти кнопку 'New Document'.",
                "needs_user_input": False,
                "is_authenticated": True
            }
        
        # Проверяем URL для определения страницы выбора опций создания документа
        if "/create-contract/options" in context.current_url:
            return {
                "state": PageState.DOCUMENTS_PAGE,
                "analysis": "Мы на странице выбора опций создания документа. Нужно найти кнопку 'Create from template'.",
                "needs_user_input": False,
                "is_authenticated": True
            }
        
        # Проверяем URL для определения предварительных данных
        if "/create-contract/details" in context.current_url:
            return {
                "state": PageState.PRELIMINARY_DATA,
                "analysis": "Мы на странице предварительных данных. Нужно ЗАПРОСИТЬ ИНФОРМАЦИЮ У ПОЛЬЗОВАТЕЛЯ перед заполнением формы.",
                "needs_user_input": True,
                "is_authenticated": True
            }
        
        # Проверяем URL для определения страницы шаблонов (если попали сюда без предварительных данных)
        if "/create-contract/templates" in context.current_url:
            return {
                "state": PageState.TEMPLATE_SELECTION,
                "analysis": "Мы на странице выбора шаблона. Нужно ЗАПРОСИТЬ ИНФОРМАЦИЮ У ПОЛЬЗОВАТЕЛЯ для выбора подходящего шаблона.",
                "needs_user_input": True,
                "is_authenticated": True
            }
        
        prompt = f"""
        Ты Эксперт по анализу состояния веб-страниц для автоматизации документации. Определи, какой стадии процесса соответствует общая информация о текущей странице, 
        на которой мы находимся и что на текущей странице нужно выполнить для достижения конечной задачи 
        "создать документ по шаблону, заполнить документ и сохранить на сайте".
        
        **ФИНАЛЬНЫЙ АЛГОРИТМ ДЕЙСТВИЙ:**
        1. Войдите в систему с помощью электронной почты и пароля: используйте "credentials['email']" и "credentials['password']"
        2. Найдите на странице на которую ты попадёшь после входа, где находится кнопка "Documents", и нажмите кнопку "Documents" она будет в левой части экрана
        3. Найдите на следующей странице, где находится кнопка "New document", и нажмите кнопку "New document" он будет в правой части экрана
        4. на следующей странице ВЫБЕРИТЕ "Create from template"
        5. ЗАПРОСИТЕ ПРЕДВАРИТЕЛЬНЫЕ ДАННЫЕ у пользователя для идентификации файла, введите эти данные в форму и нажми кнопку "CONTINUE"
        6. ПОПАДАЕТЕ НА СТРАНИЦУ ШАБЛОНОВ - а) спроси у пользователя какой документ ему нужен, если надо вступи в диалог и помоги определится.б)проанализируй названия шаблонов и подбери нужный для пользователя.в)предложите подходящий шаблон, покажите другие только если пользователь захочет.г)ПОСЛЕ ВЫБОРА ШАБЛОНА НАЖМИТЕ НА ВЫБРАННЫЙ ШАБЛОН ДЛЯ ПЕРЕХОДА К ЗАПОЛНЕНИЮ
        7. После выбора шаблона - заполните документ (на английском языке, общение с пользователем на его языке)
        8. Сохраните документ и покажите путь к папке
        
        **Информация о текущей странице:**
        URL: {context.current_url}
        Title: {context.title}
        Elements: {context.elements[:10]}
        
        **Requirements:** 
        - Базовый URL сайта https://app.conneto.com/
        - Отвечай как будто ты пишешь ответ для нейросети
        - Не предлагай код
        - Дай однозначный, краткий и содержательный ответ
        - Определи точное состояние из списка: login, documents_page, new_document, create_from_template, preliminary_data, template_selection, document_filling, file_upload, completion
        - Если не находимся на странице авторизации и пользователь уже авторизован, в конце ответа допиши "- Мы уже авторизовались на сайте."
        - Если мы авторизовались но не находимся на этапе заполнения документа, в конце ответа допиши "- Мы должны найти где заполняется документ! Используя универсальный метод нажатия на элемент."
        - Если мы находимся на этапе заполнения документа, в конце ответа допиши "- Мы должны запросить данные у пользователя и заполнить документ!"
        - Если мы находимся на этапе заполнения деталей, в конце ответа допиши "- Мы должны запросить данные у пользователя и заполнить детали!"
        - Если мы находимся на этапе авторизации, в конце ответа допиши "- Мы на этапе авторизации!"
        - Если мы на странице создания документа, допиши "- Мы должны выбрать 'Create from template'!"
        - Если мы на странице предварительных данных, допиши "- Мы должны запросить предварительные данные для идентификации файла!"
                 - Если мы на странице шаблонов, допиши "- Мы должны предложить подходящий шаблон, показать другие только если пользователь захочет!"
         - Если нужна информация от пользователя, используйте триггер "```questions```" для начала диалога
        """
        
        messages = [
            SystemMessage(content="You are an expert web navigation analyzer. Your task is to determine the current page state and what needs to be done next."),
            HumanMessage(content=prompt)
        ]
        
        response = self.llm.invoke(messages)
        
        # Парсим ответ для определения состояния
        content = response.content.lower()
        state = self._parse_state_from_response(content)
        
        # Возвращаем полный словарь с анализом
        analysis = self._analyze_state(context, state)
        needs_user_input = state in [PageState.PRELIMINARY_DATA, PageState.TEMPLATE_SELECTION, PageState.DOCUMENT_FILLING]
        is_authenticated = state != PageState.LOGIN
        
        return {
            "state": state,
            "analysis": analysis,
            "needs_user_input": needs_user_input,
            "is_authenticated": is_authenticated
        }
    
    def _analyze_state(self, context: PageContext, state: PageState) -> str:
        """Анализирует текущее состояние и возвращает описание что нужно делать"""
        if state == PageState.LOGIN:
            return "Мы на странице авторизации. Нужно войти в систему."
        elif state == PageState.PAGE_1:
            return "Мы на странице 1 (Home). Нужно найти кнопку 'Documents' в левом меню."
        elif state == PageState.DOCUMENTS_PAGE:
            return "Мы на странице Documents. Нужно найти кнопку 'New Document'."
        elif state == PageState.PRELIMINARY_DATA:
            return "Мы на странице предварительных данных. Нужно ЗАПРОСИТЬ ИНФОРМАЦИЮ У ПОЛЬЗОВАТЕЛЯ перед заполнением формы."
        elif state == PageState.TEMPLATE_SELECTION:
            return "Мы на странице выбора шаблона. Нужно ЗАПРОСИТЬ ИНФОРМАЦИЮ У ПОЛЬЗОВАТЕЛЯ для выбора подходящего шаблона."
        elif state == PageState.DOCUMENT_FILLING:
            return "Мы на странице заполнения документа. Нужно заполнить шаблон данными пользователя."
        elif state == PageState.COMPLETION:
            return "Документ создан успешно. Процесс завершен."
        else:
            return "Неизвестное состояние. Нужно определить текущую страницу."
    
    def _parse_state_from_response(self, response: str) -> PageState:
        """Парсит состояние из ответа LLM"""
        response_lower = response.lower()
        
        if "этапе авторизации" in response_lower or "login" in response_lower:
            return PageState.LOGIN
        elif "home" in response_lower or "главная" in response_lower:
            return PageState.PAGE_1  # Home страница = отдельное состояние
        elif "documents_page" in response_lower or ("documents" in response_lower and "уже авторизовались" in response_lower) or "new document" in response_lower:
            return PageState.DOCUMENTS_PAGE
        elif ("предварительные данные" in response_lower or "preliminary_data" in response_lower or 
              "запросить предварительные данные" in response_lower or "идентификации файла" in response_lower or
              "create-contract/details" in response_lower):
            return PageState.PRELIMINARY_DATA
        elif "create from template" in response_lower or "выбрать create from template" in response_lower:
            return PageState.CREATE_FROM_TEMPLATE
        elif ("template" in response_lower or "шаблон" in response_lower) and "предварительные данные" not in response_lower:
            return PageState.TEMPLATE_SELECTION
        elif "заполнить документ" in response_lower or "заполнить детали" in response_lower:
            return PageState.DOCUMENT_FILLING
        elif "upload" in response_lower or "file" in response_lower:
            return PageState.FILE_UPLOAD
        elif "complete" in response_lower or "finish" in response_lower:
            return PageState.COMPLETION
        else:
            return PageState.LOGIN  # По умолчанию 
    
    def _run(self, context: PageContext) -> Dict[str, Any]:
        """Основной метод для определения состояния страницы"""
        return self.determine_page_state(context)