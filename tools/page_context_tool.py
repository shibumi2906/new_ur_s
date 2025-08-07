from typing import Dict, Any, List
from selenium import webdriver
from selenium.webdriver.common.by import By
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import PageContext, PageElement

class PageContextToolInput(BaseModel):
    driver: Any = Field(description="Selenium WebDriver instance")

class PageContextTool(BaseTool):
    name: str = "page_context_analyzer"
    description: str = "Analyzes current page context and extracts relevant information"
    args_schema = PageContextToolInput
    
    def _run(self, driver: webdriver.Chrome) -> Dict[str, Any]:
        """Собирает расширенный контекст страницы"""
        try:
            # Проверяем, что страница загружена
            current_url = driver.current_url
            if current_url == "data:," or not current_url or current_url.startswith("data:"):
                return {
                    "success": False,
                    "error": f"Page not loaded properly. Current URL: {current_url}",
                    "current_url": current_url,
                    "title": driver.title,
                    "elements": [],
                    "body_html": ""
                }
            
            # Поиск интерактивных элементов
            elements = driver.find_elements(By.XPATH, '//*[self::input or self::textarea or self::button or self::a or self::select]')
            page_elements = []
            
            for el in elements[:50]:  # Ограничиваем количество элементов
                try:
                    page_elements.append(PageElement(
                        tag=el.tag_name,
                        text=el.text[:1000] if el.text else "",
                        id=el.get_attribute('id'),
                        class_name=el.get_attribute('class'),
                        type=el.get_attribute('type'),
                        visible=el.is_displayed(),
                        xpath=self._get_xpath(el)
                    ))
                except Exception:
                    continue
            
            # Получение HTML содержимого body
            try:
                body_element = driver.find_element(By.TAG_NAME, 'body')
                body_html = body_element.get_attribute('innerHTML')
                print(f"🔍 PAGE CONTEXT: HTML loaded successfully, length: {len(body_html)}")
                print(f"🔍 PAGE CONTEXT: Current URL: {driver.current_url}")
                print(f"🔍 PAGE CONTEXT: Title: {driver.title}")
            except Exception as e:
                body_html = ""
                print(f"🔍 PAGE CONTEXT: Failed to load HTML: {e}")
            
            # Определение состояния страницы
            page_state = self._determine_page_state(driver, page_elements)
            
            return {
                "current_url": driver.current_url,
                "title": driver.title,
                "elements": [elem.dict() for elem in page_elements],
                "body_html": body_html,
                "page_state": page_state,
                "errors_history": [],  # Добавляем пустой список ошибок
                "success": True
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "current_url": driver.current_url if driver else "",
                "title": driver.title if driver else "",
                "elements": [],
                "body_html": "",
                "errors_history": []  # Добавляем пустой список ошибок
            }
    
    def _get_xpath(self, element) -> str:
        """Генерация XPath для элемента"""
        try:
            return element.get_attribute('xpath') or self._generate_xpath(element)
        except:
            return ""
    
    def _generate_xpath(self, element) -> str:
        """Генерация XPath для элемента через JavaScript"""
        try:
            return element.parent.execute_script("""
            function getElementXPath(element) {
                if (element.id) return '//*[@id="' + element.id + '"]';
                if (element === document.body) return '/html/body';

                const siblings = element.parentNode.childNodes;
                let idx = 1;
                for (let sibling of siblings) {
                    if (sibling === element) {
                        return getElementXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + idx + ']';
                    }
                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                        idx++;
                    }
                }
            }
            return getElementXPath(arguments[0]);
            """, element)
        except:
            return ""
    
    def _determine_page_state(self, driver: webdriver.Chrome, elements: List[PageElement]) -> str:
        """Определяет текущее состояние страницы"""
        url = driver.current_url.lower()
        title = driver.title.lower()
        
        # Проверка на страницу авторизации
        if any(keyword in url or keyword in title for keyword in ['login', 'signin', 'auth']):
            return "login"
        
        # Проверка на страницу документов
        if any(keyword in url or keyword in title for keyword in ['document', 'documents']):
            # Проверяем наличие кнопки "New document"
            for elem in elements:
                if 'new document' in elem.text.lower() or 'create' in elem.text.lower():
                    return "documents_page"
            return "documents_page"
        
        # Проверка на выбор шаблона
        if any(keyword in url or keyword in title for keyword in ['template', 'select']):
            return "template_selection"
        
        # Проверка на заполнение документа
        if any(keyword in url or keyword in title for keyword in ['fill', 'form', 'details']):
            return "document_filling"
        
        # Проверка на загрузку файла
        if any(keyword in url or keyword in title for keyword in ['upload', 'file']):
            return "file_upload"
        
        # Проверка на завершение
        if any(keyword in url or keyword in title for keyword in ['complete', 'finish', 'download']):
            return "completion"
        
        return "unknown" 