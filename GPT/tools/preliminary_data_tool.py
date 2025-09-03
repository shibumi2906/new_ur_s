# === 1) СОЗДАТЬ ФАЙЛ: tools/preliminary_data_tool.py ===
from typing import Dict, Any
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class PreliminaryDataTool:
    """Тул для страницы PRELIMINARY_DATA: чтение значений, верификация и мягкая автопочинка."""

    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger

    # ---------- Вспомогательные чтения ----------
    def _read_values(self) -> Dict[str, str]:
        wait = WebDriverWait(self.driver, 15)
        cur: Dict[str, str] = {}

        # document_name
        name_candidates = [
            (By.CSS_SELECTOR, "input[placeholder*='Document name']"),
            (By.CSS_SELECTOR, "input[name*='document']"),
            (By.CSS_SELECTOR, "input[name*='name']"),
            (By.CSS_SELECTOR, "input[placeholder*='name']"),
            (By.CSS_SELECTOR, "input[type='text']"),
        ]
        for by, sel in name_candidates:
            try:
                el = wait.until(EC.presence_of_element_located((by, sel)))
                val = (el.get_attribute('value') or '').strip()
                if val:
                    cur['document_name'] = val
                    break
            except TimeoutException:
                continue

        # document_language
        lang_candidates = [
            (By.CSS_SELECTOR, ".vs__selected"),
            (By.CSS_SELECTOR, "[role='combobox'] .vs__selected"),
            (By.XPATH, "//div[contains(@class,'vs__selected')][1]"),
            (By.XPATH, "//select[1]/option[@selected]"),
        ]
        for by, sel in lang_candidates:
            try:
                el = wait.until(EC.presence_of_element_located((by, sel)))
                txt = (el.text or el.get_attribute('textContent') or '').strip()
                if txt:
                    cur['document_language'] = txt
                    break
            except TimeoutException:
                continue

        return cur

    # ---------- Явные действия (по желанию) ----------
    def fill_document_name(self, value: str) -> bool:
        try:
            el = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='Document name'], input[name*='document'], input[name*='name'], input[placeholder*='name'], input[type='text']"))
            )
            self.driver.execute_script(
                "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true})); arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                el, value
            )
            return True
        except Exception:
            return False

    def select_language(self, value: str) -> bool:
        try:
            try:
                dd = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".vs__dropdown-toggle, [role='combobox'], .g-select-search__wrapper, select, .dropdown-toggle"))
                )
                self.driver.execute_script("arguments[0].click();", dd)
                time.sleep(0.5)
            except Exception:
                pass
            options_xpath = [
                f"//li[@role='option' and contains(normalize-space(.), '{value}')]",
                f"//option[contains(normalize-space(.), '{value}')]",
                f"//*[@role='option' and contains(normalize-space(.), '{value}')]",
                f"//li[contains(normalize-space(.), '{value}')]",
            ]
            for xp in options_xpath:
                try:
                    op = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH, xp)))
                    self.driver.execute_script("arguments[0].click();", op)
                    return True
                except TimeoutException:
                    continue
        except Exception:
            pass
        return False

    # ---------- Верификация и «мягкая» починка ----------
    def verify(self, expected: Dict[str, str]) -> bool:
        cur = self._read_values()
        unmet = {}
        for k, v in (expected or {}).items():
            if not v:
                continue
            cv = (cur.get(k) or '').strip()
            ok = (v.lower() in cv.lower()) if k == 'document_language' else (cv == v)
            if not ok:
                unmet[k] = v
        if not unmet:
            if self.logger: self.logger.info("PRELIMINARY_DATA verified ✅")
            return True
        if self.logger: self.logger.warning(f"PRELIMINARY_DATA not verified, unmet={list(unmet.keys())}")
        return False

    def quick_fix(self, expected: Dict[str, str]) -> bool:
        fixed = False
        for k, v in (expected or {}).items():
            if not v:
                continue
            if k == 'document_name':
                fixed |= self.fill_document_name(v)
            elif k == 'document_language':
                fixed |= self.select_language(v)
        if fixed and self.logger: self.logger.info("Quick fix attempted ✅")
        return fixed

    def verify_and_fix(self,
                       context: Any,
                       expected: Dict[str, str],
                       error_fix_tool: Any,
                       selenium_tool: Any,
                       credentials: Dict[str, str],
                       original_code: str,
                       original_prompt: str,
                       max_attempts: int = 2) -> bool:
        attempts = 0
        while attempts <= max_attempts:
            attempts += 1
            if self.verify(expected):
                return True

            if self.quick_fix(expected):
                time.sleep(0.8)
                if self.verify(expected):
                    return True

            # В ход идёт ErrorFixTool
            soft_error = f"SoftValidationFailure: prelim fields not set: {list((expected or {}).keys())}"
            if self.logger: self.logger.warning(soft_error)
            fix = error_fix_tool._run(
                original_code=original_code,
                error_message=soft_error,
                context=context.dict(),
                initial_prompt=original_prompt
            )
            if fix.get('success') and fix.get('corrected_code'):
                ctx = context.dict()
                ctx['credentials'] = credentials
                ctx['user_data'] = expected
                exec_ok = selenium_tool._run(fix['corrected_code'], ctx)
                if exec_ok.get('success'):
                    time.sleep(0.8)
                    if self.verify(expected):
                        return True
                else:
                    if self.logger: self.logger.error(f"Corrected code failed: {exec_ok.get('error')}")
                    return False
            else:
                if self.logger: self.logger.error(f"ErrorFixTool failed: {fix.get('error')}")
                return False
        return False


# === 2) ПРАВКИ В main_agent.py ===
# 2.1 ДОБАВИТЬ ИМПОРТ (примерно вверху файла, рядом с другими tools)
# 2 строки до:
# from ..tools.page_context_tool import PageContextTool
# from .lawyer_agent import LawyerAgent
# ВСТАВИТЬ:
# from ..tools.preliminary_data_tool import PreliminaryDataTool
# 2 строки после:
# from ..tools.error_fix_tool import ErrorFixTool
# from ..logger import get_logger

# 2.2 __init__: инициализация тула (рядом с другими инструментами)
# 2 строки до:
#         self.selenium_tool = SeleniumTool(driver)
#         self.page_context_tool = PageContextTool()
# ВСТАВИТЬ:
#         self.prelim_tool = PreliminaryDataTool(driver, logger=self.logger)
# 2 строки после:
#         self.lawyer_agent = LawyerAgent(driver=driver, prompt_generator=self.prompt_generator)
#         self.error_fix_tool = ErrorFixTool()

# 2.3 _handle_ai_logic: после успешного immediate_fill
# 2 строки до:
#                 if success:
#                     print(f"✅ Field {field_name} filled successfully")
# ВСТАВИТЬ:
#                     if current_state == PageState.PRELIMINARY_DATA:
#                         expected = {field_name: field_value}
#                         ok = self.prelim_tool.verify_and_fix(
#                             context,
#                             expected,
#                             error_fix_tool=self.error_fix_tool,
#                             selenium_tool=self.selenium_tool,
#                             credentials=self.credentials,
#                             original_code=selenium_code,
#                             original_prompt=f"Immediate fill: {field_name}"
#                         )
#                         if not ok:
#                             self.logger.error(f"PreliminaryData verify_and_fix failed for {expected}")
#                             return False
# 2 строки после:
#                     return True  # Продолжаем цикл для следующего поля
#                 else:

# 2.4 _handle_ai_logic: после пакетного заполнения формы
# 2 строки до:
#                 if not success:
#                     self.logger.error("Failed to fill form after retries")
#                     return False
# ВСТАВИТЬ:
#                 if current_state == PageState.PRELIMINARY_DATA:
#                     expected = self._extract_user_data_from_responses()
#                     ok = self.prelim_tool.verify_and_fix(
#                         context,
#                         expected,
#                         error_fix_tool=self.error_fix_tool,
#                         selenium_tool=self.selenium_tool,
#                         credentials=self.credentials,
#                         original_code=form_filling_code,
#                         original_prompt=form_filling_prompt
#                     )
#                     if not ok:
#                         self.logger.error("PreliminaryData verify_and_fix failed after form filling")
#                         return False

# === 3) (необязательно) Экспорт в __init__.py пакета tools ===
# Добавить строку: from .preliminary_data_tool import PreliminaryDataTool

# === 4) Запуск ===
# python -m GPT.gui_agent
