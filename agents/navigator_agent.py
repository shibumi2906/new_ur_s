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
    
    def determine_page_state(self, context: PageContext, user_responses_summary: str = "") -> Dict[str, Any]:
        """Определяет текущее состояние страницы и что нужно делать дальше"""
        
        # Проверяем URL для определения Page 1 (Home страница)
        if "/home" in context.current_url:
            return {
                "state": PageState.PAGE_1,  # Page 1 = Home страница
                "analysis": "Мы на странице 1 (Home). Нужно найти кнопку 'Documents' в левом меню.",
                "needs_user_input": False,
                "is_authenticated": True
            }
        
        # Проверяем URL для определения Page 2 (Documents страница)
        if "/documents" in context.current_url:
            return {
                "state": PageState.PAGE_2,
                "analysis": "Мы на странице 2 (Documents). Нужно найти кнопку 'New Document'.",
                "needs_user_input": False,
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
        6. ПОПАДАЕТЕ НА СТРАНИЦУ ШАБЛОНОВ - а) спроси у пользователя какой документ ему нужен, если надо вступи в диалог и помоги определится.б)проанализируй названия шаблонов и подбери нужный для пользователя.в)предложите подходящий шаблон, покажите другие только если пользователь захочет
        7. После выбора шаблона - заполните документ (на английском языке, общение с пользователем на его языке)
        8. Сохраните документ и покажите путь к папке
        
        **Информация о текущей странице:**
        URL: {context.current_url}
        Title: {context.title}
        Elements: {[elem.dict() for elem in context.elements[:10]]}
        
        {user_responses_summary}
        
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
        """
        
        messages = [
            SystemMessage(content="You are an expert web navigation analyzer. Your task is to determine the current page state and what needs to be done next."),
            HumanMessage(content=prompt)
        ]
        
        response = self.llm.invoke(messages)
        
        # Парсим ответ для определения состояния
        content = response.content.lower()
        state = self._parse_state_from_response(content)
        
        return {
            "state": state,
            "analysis": response.content,
            "needs_user_input": "запросить данные у пользователя" in content,
            "is_authenticated": "уже авторизовались" in content
        }
    
    def _parse_state_from_response(self, response: str) -> PageState:
        """Парсит состояние из ответа LLM"""
        if "этапе авторизации" in response:
            return PageState.LOGIN
        elif "home" in response or "главная" in response:
            return PageState.PAGE_1  # Home страница = отдельное состояние
        elif "documents_page" in response or ("documents" in response and "уже авторизовались" in response) or "new document" in response:
            return PageState.PAGE_2
        elif "предварительные данные" in response or "preliminary_data" in response:
            return PageState.PRELIMINARY_DATA
        elif "create from template" in response or "выбрать create from template" in response:
            return PageState.CREATE_FROM_TEMPLATE
        elif "template" in response or "шаблон" in response:
            return PageState.TEMPLATE_SELECTION
        elif "заполнить документ" in response or "заполнить детали" in response:
            return PageState.DOCUMENT_FILLING
        elif "upload" in response or "file" in response:
            return PageState.FILE_UPLOAD
        elif "complete" in response or "finish" in response:
            return PageState.COMPLETION
        else:
            return PageState.LOGIN  # По умолчанию 