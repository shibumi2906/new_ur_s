from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
from ..models import PageContext, UserResponse, PageState


class LawyerAgent:
    """Ты опытный американский юрист, специалист по договорному и авторскому праву.
    Ты должен вести диалог с пользователем, помогать, объяснять пользователю то, что ему не понятно.
    Твоя основная задача найти шаблон, который нужен пользователю, заполнить его юридически грамотными формулировками с точки зрения американского права, так чтобы выполнить задачу пользователя.
    """

    def __init__(self, driver=None, prompt_generator=None, gui_callback=None):
        self.driver = driver
        self.prompt_generator = prompt_generator
        self.llm = ChatOpenAI(
            model=Config.LLM_MODEL,
            temperature=0.7,  # Более креативный для диалога
            api_key=Config.OPENAI_API_KEY
        )
        self.user_responses: List[UserResponse] = []
        self.gui_callback = gui_callback  # Callback для взаимодействия с GUI
        self.current_question_index = 0  # Индекс текущего вопроса
        self.all_questions = []  # Все вопросы для текущего состояния
        self.last_state = None   # Запоминаем последнее состояние для сброса вопросов

    def _run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Основной метод для обработки диалога с пользователем"""
        try:
            # Получаем текущее состояние
            current_state = context.get('current_state')

            # 1. ПРОВЕРКА СМЕНЫ СОСТОЯНИЯ (FIX)
            # Если состояние изменилось, сбрасываем вопросы, чтобы не спрашивать про 'document_name' на странице шаблонов
            if current_state != self.last_state:
                print(f"🔄 LAWYER AGENT: State changed from {self.last_state} to {current_state}. Resetting questions.")
                self.all_questions = []
                self.current_question_index = 0
                self.last_state = current_state

            # Если это новый набор вопросов, генерируем их
            if not self.all_questions:
                self.all_questions = self._generate_questions_from_form(context)
                self.current_question_index = 0

            if not self.all_questions:
                return {
                    "success": False,
                    "error": "No questions found in AI response"
                }

            # Проверяем, есть ли еще вопросы
            if self.current_question_index >= len(self.all_questions):
                # Проверяем, собраны ли обязательные поля
                required_fields_collected = self._check_required_fields(context)

                if required_fields_collected:
                    # Все обязательные поля собраны, возвращаем успех
                    print(f"✅ All required fields collected: {[resp.question for resp in self.user_responses]}")
                    return {
                        "success": True,
                        "all_completed": True,
                        "question": "All questions completed",
                        "answer": "All questions completed",
                        "legal_formulation": "All questions completed"
                    }
                else:
                    # Не все обязательные поля собраны, продолжаем с новым вопросом
                    print(
                        f"⚠️ Not all required fields collected. Current responses: {[resp.question for resp in self.user_responses]}")
                    # Сбрасываем индекс для нового цикла вопросов
                    self.current_question_index = 0
                    return {
                        "success": True,
                        "question": "Need more required fields",
                        "answer": "Continuing",
                        "legal_formulation": "Continuing"
                    }

            # Берем текущий вопрос (тип поля)
            current_question_type = self.all_questions[self.current_question_index]

            # Генерируем формулировку вопроса
            formatted_question = self._format_question(current_question_type, context)

            # Диалог с обработкой встречных вопросов пользователя
            while True:
                # Отображаем вопрос пользователю и ждем ответ
                print(f"🤖 LAWYER AGENT: {formatted_question}")
                print(f"📝 Ожидаем ответ от пользователя...")
                user_answer = self._get_user_input(formatted_question)
                if not user_answer:
                    return {"success": False, "error": "No user input received"}

                # Если пользователь задает встречный вопрос — отвечаем и повторяем исходный вопрос
                if self._is_user_question(user_answer):
                    assistant_reply = self._answer_user_question(user_answer, context, current_question_type)
                    # Соединяем ответ с повторением исходного вопроса, чтобы пользователь дал конкретный ответ
                    followup = f"{assistant_reply}\n\n{formatted_question}"
                    # Показать пояснение и снова запросить ответ через тот же callback
                    print(f"🤖 LAWYER AGENT: {assistant_reply}")
                    # Перейдем к следующей итерации цикла, чтобы повторно задать тот же вопрос
                    formatted_question = formatted_question  # для читабельности
                    continue

                # Семантическая валидация ответов
                if current_question_type == "document_language":
                    options = self._extract_language_options(context)
                    normalized_options = {opt.strip().lower(): opt for opt in options}
                    answer_norm = user_answer.strip().lower()
                    if options and answer_norm not in normalized_options:
                        # Ответ не из списка — подскажем варианты и повторим вопрос
                        hint = "; ".join(options[:10])
                        print(f"🤖 LAWYER AGENT: Доступные языки: {hint}. Пожалуйста, выберите один из списка.")
                        # Продолжаем цикл без сохранения ответа и без увеличения индекса
                        continue

                # Ответ валиден — нормализуем и сохраняем
                normalized_answer = self._normalize_user_answer(user_answer, current_question_type)
                response = UserResponse(
                    question=formatted_question,
                    answer=normalized_answer,
                    timestamp=time.time()
                )
                self.user_responses.append(response)
                print(f"✅ Ответ получен: {user_answer}")
                break

            # Увеличиваем индекс для следующего вопроса
            self.current_question_index += 1

            # Проверяем, есть ли еще вопросы
            if self.current_question_index >= len(self.all_questions):
                # Проверяем, собраны ли все обязательные поля
                required_fields_collected = self._check_required_fields(context)
                all_completed = required_fields_collected
            else:
                all_completed = False

            # Создаем маппинг для полей
            field_name_map = {
                "document_name": "document_name",
                "document_language": "document_language",
                "document_number": "document_number",
                "add_to_project": "add_to_project",
                "selected_template": "selected_template"  # Добавлено поле шаблона
            }
            field_name = field_name_map.get(current_question_type)

            return {
                "success": True,
                "immediate_fill": True,  # сигнал MainAgent для немедленного заполнения
                "field_name": field_name,  # какое поле заполнять
                "all_completed": all_completed,
                "question_asked": True,
                "question": formatted_question,
                "answer": user_answer,
                "legal_formulation": self._generate_legal_formulation(user_answer, context)
            }

        except Exception as e:
            print(f"❌ Ошибка в LawyerAgent: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }

    def _get_user_input(self, question: str) -> str:
        """Получает ввод от пользователя через GUI или консоль"""
        if self.gui_callback:
            # Используем GUI callback если доступен
            return self.gui_callback(question)
        else:
            # Fallback на консольный ввод
            print(f"\n🤖 Вопрос: {question}")
            return input("💬 Ваш ответ: ").strip()

    def _extract_questions(self, ai_response: str) -> List[str]:
        """Извлекает вопросы из ответа AI в JSON формате"""
        questions = []

        # Ищем блок questions с разными вариантами разделителей
        patterns = [
            ('```questions', '```'),
            ('``` questions', '```'),
            ('questions', '```'),
        ]

        for start_pattern, end_pattern in patterns:
            if start_pattern in ai_response:
                start = ai_response.find(start_pattern) + len(start_pattern)
                end = ai_response.find(end_pattern, start)
                if end != -1:
                    questions_text = ai_response[start:end].strip()

                    # Пытаемся парсить как JSON
                    try:
                        import json
                        questions_data = json.loads(questions_text)
                        if isinstance(questions_data, list):
                            for item in questions_data:
                                if isinstance(item, dict) and 'question' in item:
                                    questions.append(item['question'])
                        elif isinstance(questions_data, dict) and 'question' in questions_data:
                            questions.append(questions_data['question'])
                    except json.JSONDecodeError:
                        # Если JSON не парсится, ищем вопросы в тексте
                        lines = [line.strip() for line in questions_text.split('\n') if line.strip()]
                        questions = [line for line in lines if '?' in line and line.strip()]

                    if questions:
                        break

        # Если не нашли вопросы в блоках, ищем строки с вопросами
        if not questions:
            lines = ai_response.split('\n')
            questions = [line.strip() for line in lines if '?' in line and line.strip()]

        print(f"🔍 EXTRACTED QUESTIONS: {questions}")
        return questions

    def _format_question(self, question: str, context: Dict[str, Any]) -> str:
        """Форматирует вопрос в вежливой и профессиональной форме с триггерами полей"""

        # Определяем, какое поле нужно заполнить
        field_type = self._identify_field_type(question)

        if field_type == "document_name":
            return "Введите название файла: [FIELD:document_name]"
        elif field_type == "document_language":
            return "Выберите язык документа: [FIELD:document_language]"
        elif field_type == "document_number":
            return "Введите номер документа (необязательно): [FIELD:document_number]"
        elif field_type == "add_to_project":
            return "Выберите проект (необязательно): [FIELD:add_to_project]"
        elif field_type == "selected_template":
            # Извлекаем список шаблонов из промпта LLM или контекста для более точного вопроса
            # Но для простоты оставим общий вопрос, так как LLM ранее сгенерировала список
            return "Какой шаблон документа вы хотите использовать? (Например: NDA, Contract of Rent): [FIELD:selected_template]"
        else:
            return f"{question} [FIELD:unknown]"

    def _identify_field_type(self, question: str) -> str:
        """Определяет тип поля на основе вопроса с поддержкой snake_case"""
        q = (question or "").strip().lower()
        # Нормализуем snake_case -> пробелы
        q_norm = q.replace("_", " ")

        # Прямые токены тоже считаем валидными
        if q in {"document_name", "document language", "document_number", "add_to_project", "selected_template"}:
            return {
                "document_name": "document_name",
                "document language": "document_language",
                "document_number": "document_number",
                "add_to_project": "add_to_project",
                "selected_template": "selected_template"
            }[q]

        if any(k in q or k in q_norm for k in ["название", "наименование", "document name", "title", "название файла"]):
            return "document_name"
        if any(k in q or k in q_norm for k in ["язык", "language", "язык документа", "выберите язык"]):
            return "document_language"
        if any(k in q or k in q_norm for k in ["номер", "number"]):
            return "document_number"
        if any(k in q or k in q_norm for k in ["проект", "project"]):
            return "add_to_project"
        if any(k in q or k in q_norm for k in ["шаблон", "template", "выберите шаблон"]):
            return "selected_template"

        return "unknown"

    def _generate_legal_formulation(self, user_answer: str, context: Dict[str, Any]) -> str:
        """Генерирует юридически корректную формулировку на основе ответа пользователя"""
        prompt = f"""
        Ты опытный юрист. Преобразуй ответ пользователя в профессиональную юридическую формулировку для заполнения документа.

        Ответ пользователя: {user_answer}
        Контекст: {context.get('current_url', '')}

        Требования:
        - Используй официально-деловой стиль
        - Применяй юридическую терминологию
        - Обеспечь точность и однозначность формулировки
        - Если ответ на русском, переведи на английский для заполнения формы
        - Сохрани смысл, но сделай формулировку более профессиональной

        Верни только юридическую формулировку.
        """

        messages = [
            SystemMessage(content="You are an experienced lawyer creating professional legal formulations."),
            HumanMessage(content=prompt)
        ]

        response = self.llm.invoke(messages)
        return response.content.strip()

    def _check_required_fields(self, context: Dict[str, Any] = None) -> bool:
        """Проверяет, собраны ли все обязательные поля"""

        # Определяем обязательные поля в зависимости от состояния
        current_state = None
        if context:
            current_state = context.get('current_state')

        # Базовые обязательные поля для Preliminary Data
        required_fields = {
            "document_name": False,
            "document_language": False
        }

        # Если мы выбираем шаблон, то обязательным является шаблон, а не имя/язык
        if current_state == PageState.TEMPLATE_SELECTION:
            required_fields = {
                "selected_template": False
            }

        print(f"🔍 Checking required fields ({required_fields.keys()}). Total responses: {len(self.user_responses)}")

        # Проверяем ответы пользователя на наличие обязательных полей
        for response in self.user_responses:
            question_lower = response.question.lower()
            answer_lower = response.answer.lower()

            print(f"🔍 Checking response: '{question_lower}' -> '{answer_lower}'")

            # Проверяем название документа (только если требуется в текущем состоянии)
            if "document_name" in required_fields:
                if (any(keyword in question_lower for keyword in
                        ["название", "наименование", "document name", "title", "название файла"]) or
                        "document_name" in question_lower or "[field:document_name]" in question_lower):
                    if answer_lower and answer_lower not in ["skip", "пропустить", "нет", "no", ""]:
                        required_fields["document_name"] = True
                        print(f"✅ Document name found: {answer_lower}")

            # Проверяем язык документа (только если требуется)
            if "document_language" in required_fields:
                if (any(keyword in question_lower for keyword in
                        ["язык", "language", "язык документа", "выберите язык"]) or
                        "document_language" in question_lower or "[field:document_language]" in question_lower):
                    if answer_lower and answer_lower not in ["skip", "пропустить", "нет", "no", ""]:
                        required_fields["document_language"] = True
                        print(f"✅ Document language found: {answer_lower}")

            # Проверяем шаблон (только если требуется)
            if "selected_template" in required_fields:
                if (any(keyword in question_lower for keyword in ["шаблон", "template", "выберите шаблон"]) or
                        "selected_template" in question_lower or "[field:selected_template]" in question_lower):
                    if answer_lower and answer_lower not in ["skip", "пропустить", "нет", "no", ""]:
                        required_fields["selected_template"] = True
                        print(f"✅ Selected template found: {answer_lower}")

        print(f"🔍 Required fields status: {required_fields}")

        # Возвращаем True только если все обязательные поля заполнены
        return all(required_fields.values())

    def get_user_responses_summary(self) -> str:
        """Возвращает сводку ответов пользователя"""
        if not self.user_responses:
            return ""

        summary = "Предыдущие ответы пользователя:\n"
        for i, response in enumerate(self.user_responses, 1):
            summary += f"{i}. Вопрос: {response.question}\n   Ответ: {response.answer}\n\n"
        return summary

    def _generate_questions_from_form(self, context: Dict[str, Any]) -> List[str]:
        """Генерирует вопросы на основе полей формы или текущего состояния"""
        questions = []

        # == ВАЖНОЕ ИЗМЕНЕНИЕ: Проверка состояния ==
        current_state = context.get('current_state')
        if current_state == PageState.TEMPLATE_SELECTION:
            print("🔍 State is TEMPLATE_SELECTION, adding 'selected_template' question")
            # На странице шаблонов нет формы, но нам НУЖНО задать этот вопрос
            return ["selected_template"]
        # ==========================================

        # Анализируем поля формы
        form_fields = self._analyze_form_fields(context)

        print(f"🔍 ANALYZED FORM FIELDS: {form_fields}")

        # Генерируем вопросы на основе найденных полей
        for field in form_fields:
            field_name = field.get('name', '').lower()
            field_type = field.get('type', '')
            is_required = field.get('required', False)

            print(f"🔍 PROCESSING FIELD: {field_name} (type: {field_type}, required: {is_required})")

            # Определяем тип вопроса на основе названия поля
            if any(keyword in field_name for keyword in ["name", "title", "название", "наименование"]):
                questions.append("document_name")
                print(f"🔍 Added document_name question for field: {field_name}")
            elif any(keyword in field_name for keyword in ["language", "lang", "язык"]):
                questions.append("document_language")
                print(f"🔍 Added document_language question for field: {field_name}")
            elif any(keyword in field_name for keyword in ["number", "номер", "num"]):
                questions.append("document_number")
                print(f"🔍 Added document_number question for field: {field_name}")
            elif any(keyword in field_name for keyword in ["project", "проект", "proj"]):
                questions.append("add_to_project")
                print(f"🔍 Added add_to_project question for field: {field_name}")

        # Если не нашли поля в HTML, используем стандартные обязательные поля
        # Но только если мы НЕ в режиме выбора шаблона (это обработано выше)
        if not questions and current_state == PageState.PRELIMINARY_DATA:
            print(f"🔍 No form fields found, using default questions for PRELIMINARY_DATA")
            questions = ["document_name", "document_language"]

        # Убираем дубликаты, сохраняя порядок
        unique_questions = []
        for question in questions:
            if question not in unique_questions:
                unique_questions.append(question)

        print(f"🔍 FINAL GENERATED QUESTIONS: {unique_questions}")
        return unique_questions

    def _analyze_form_fields(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Анализирует поля формы на странице"""
        html = context.get('body_html', '')
        fields = []

        # Ищем поля ввода в HTML
        import re

        # Ограничим размер анализируемого HTML для скорости, если он огромен
        if len(html) > 500000:
            html = html[:500000]

        print(f"🔍 ANALYZING HTML FOR FORM FIELDS (length: {len(html)})")

        # Ищем input поля с более детальным анализом
        input_pattern = r'<input[^>]*>'
        input_matches = re.findall(input_pattern, html, re.IGNORECASE)

        for input_tag in input_matches:
            # Извлекаем атрибуты
            name_match = re.search(r'name=["\']([^"\']*)["\']', input_tag, re.IGNORECASE)
            id_match = re.search(r'id=["\']([^"\']*)["\']', input_tag, re.IGNORECASE)
            placeholder_match = re.search(r'placeholder=["\']([^"\']*)["\']', input_tag, re.IGNORECASE)
            type_match = re.search(r'type=["\']([^"\']*)["\']', input_tag, re.IGNORECASE)
            required_match = re.search(r'required', input_tag, re.IGNORECASE)

            # Определяем название поля
            field_name = ""
            if name_match:
                field_name = name_match.group(1)
            elif id_match:
                field_name = id_match.group(1)
            elif placeholder_match:
                field_name = placeholder_match.group(1)

            if field_name:
                field_type = type_match.group(1) if type_match else "text"
                # Пропускаем скрытые и кнопки
                if field_type in ['hidden', 'submit', 'button', 'image']:
                    continue

                is_required = bool(required_match) or '*' in field_name

                fields.append({
                    'type': 'input',
                    'name': field_name,
                    'required': is_required,
                    'input_type': field_type
                })
                print(f"🔍 Found input field: {field_name} (type: {field_type}, required: {is_required})")

        # Ищем select поля
        select_pattern = r'<select[^>]*>.*?</select>'
        select_matches = re.findall(select_pattern, html, re.IGNORECASE | re.DOTALL)

        for select_tag in select_matches:
            name_match = re.search(r'name=["\']([^"\']*)["\']', select_tag, re.IGNORECASE)
            id_match = re.search(r'id=["\']([^"\']*)["\']', select_tag, re.IGNORECASE)
            required_match = re.search(r'required', select_tag, re.IGNORECASE)

            field_name = ""
            if name_match:
                field_name = name_match.group(1)
            elif id_match:
                field_name = id_match.group(1)

            if field_name:
                is_required = bool(required_match) or '*' in field_name

                fields.append({
                    'type': 'select',
                    'name': field_name,
                    'required': is_required
                })
                print(f"🔍 Found select field: {field_name} (required: {is_required})")

        # Ищем label элементы, которые могут содержать названия полей
        label_pattern = r'<label[^>]*>([^<]*)</label>'
        label_matches = re.findall(label_pattern, html, re.IGNORECASE)

        for label_text in label_matches:
            label_text = label_text.strip()
            if label_text and any(keyword in label_text.lower() for keyword in
                                  ["name", "language", "number", "project", "название", "язык", "номер", "проект"]):
                print(f"🔍 Found label: {label_text}")

        print(f"🔍 TOTAL FORM FIELDS FOUND: {len(fields)}")
        return fields

    def _is_user_question(self, text: str) -> bool:
        """Определяет, является ли сообщение пользователя встречным вопросом"""
        if not text:
            return False
        t = text.strip().lower()
        if t.endswith('?'):
            return True
        keywords = ["какой", "какие", "что", "зачем", "почему", "как", "можно выбрать", "какой язык"]
        return any(k in t for k in keywords)

    def _answer_user_question(self, user_question: str, context: Dict[str, Any], current_question_type: str) -> str:
        """Формирует ответ юриста на встречный вопрос пользователя"""
        t = user_question.strip().lower()
        # Если вопрос про язык — подскажем допустимые варианты
        if current_question_type == "document_language" or "язык" in t:
            options = self._extract_language_options(context)
            if options:
                top = ", ".join(options[:10])
                return f"Доступные языки на этой странице: {top}. Пожалуйста, укажите один из них."
            else:
                return "Обычно доступны стандартные языки интерфейса (например, English). Пожалуйста, введите язык, который видите в выпадающем списке."
        # Общий ответ — вежливо попросить конкретизировать
        return "Спасибо за вопрос! Поясните, пожалуйста, чтобы я мог помочь. Если готовы, дайте конкретный ответ на мой вопрос выше."

    def _extract_language_options(self, context: Dict[str, Any]) -> list:
        """Извлекает список доступных языков из HTML страницы, если удается"""
        html = context.get('body_html', '') or ''
        import re
        options = []
        # Вариант 1: обычные <option>…</option>
        for m in re.findall(r'<option[^>]*>([^<]+)</option>', html, flags=re.IGNORECASE):
            val = m.strip()
            if val and len(val) < 50:
                options.append(val)
        # Вариант 2: кастомные выпадающие списки (Vue Select и т.п.)
        for m in re.findall(
                r'\b(English|Russian|Русский|Deutsch|German|Spanish|Español|French|Français|Italian|Portuguese|中文|日本語)\b',
                html, flags=re.IGNORECASE):
            val = m.strip()
            if val and val not in options:
                options.append(val)
        # Чистим дубликаты, сохраняем порядок
        seen = set()
        unique = []
        for v in options:
            k = v.lower()
            if k not in seen:
                seen.add(k)
                unique.append(v)
        return unique

    def _normalize_user_answer(self, answer: str, question_type: str) -> str:
        """Нормализует ответ пользователя в соответствии с требованиями формы"""
        answer = answer.strip()

        # Для языков - переводим на правильный английский формат
        if question_type == "document_language":
            answer_lower = answer.lower()
            language_map = {
                # Русские варианты
                'английский': 'English',
                'англ': 'English',
                'русский': 'Russian',
                'рус': 'Russian',
                'немецкий': 'German',
                'нем': 'German',
                'французский': 'French',
                'франц': 'French',
                'испанский': 'Spanish',
                'исп': 'Spanish',
                # Английские варианты
                'english': 'English',
                'russian': 'Russian',
                'german': 'German',
                'french': 'French',
                'spanish': 'Spanish',
                # Сокращения
                'en': 'English',
                'ru': 'Russian',
                'de': 'German',
                'fr': 'French',
                'es': 'Spanish'
            }

            if answer_lower in language_map:
                normalized = language_map[answer_lower]
                print(f"🔧 LAWYER: Нормализовал язык '{answer}' → '{normalized}'")
                return normalized

        return answer