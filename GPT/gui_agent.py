#!/usr/bin/env python3
"""
GUI версия AI Document Creator Agent для MVP
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import sys
import os

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from .agents.main_agent import MainAgent
from config import Config

class AgentGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Document Creator Agent - MVP")
        self.root.geometry("900x700")
        
        # Настройка стилей
        style = ttk.Style()
        style.configure("Large.TButton", font=("Arial", 14, "bold"), padding=15)
        style.configure("ExtraLarge.TButton", font=("Arial", 16, "bold"), padding=20)
        
        # Очередь для сообщений от агента
        self.message_queue = queue.Queue()
        
        # Переменные для учетных данных
        self.email_var = tk.StringVar(value=Config.DEFAULT_EMAIL)
        self.password_var = tk.StringVar(value=Config.DEFAULT_PASSWORD)
        
        self.setup_ui()
        self.setup_agent()
        
    def setup_ui(self):
        """Настройка пользовательского интерфейса"""
        
        # Главный фрейм
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Конфигурация сетки
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(3, weight=1)  # Логи должны расширяться
        
        # Заголовок
        title_label = ttk.Label(main_frame, text="🤖 AI Document Creator Agent", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Фрейм для учетных данных
        cred_frame = ttk.LabelFrame(main_frame, text="Credentials", padding="10")
        cred_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Email
        ttk.Label(cred_frame, text="Email:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        email_entry = ttk.Entry(cred_frame, textvariable=self.email_var, width=40)
        email_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        
        # Password
        ttk.Label(cred_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))
        password_entry = ttk.Entry(cred_frame, textvariable=self.password_var, width=40, show="*")
        password_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(0, 10), pady=(10, 0))
        
        # Кнопки управления
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(10, 20))
        
        self.start_button = ttk.Button(button_frame, text="🚀 Start Agent",
                                      command=self.start_agent, style="ExtraLarge.TButton")
        self.start_button.pack(side=tk.LEFT, padx=(0, 20))
        
        self.stop_button = ttk.Button(button_frame, text="⏹️ Stop",
                                     command=self.stop_agent, state=tk.DISABLED, style="ExtraLarge.TButton")
        self.stop_button.pack(side=tk.LEFT)
        
        # Область логов
        log_frame = ttk.LabelFrame(main_frame, text="Agent Log", padding="10")
        log_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Область для диалога с юристом
        dialog_frame = ttk.LabelFrame(main_frame, text="Lawyer Dialog", padding="10")
        dialog_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        dialog_frame.columnconfigure(0, weight=1)
        dialog_frame.rowconfigure(0, weight=1)
        
        # Область диалога
        self.dialog_text = scrolledtext.ScrolledText(dialog_frame, height=8, width=80)
        self.dialog_text.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # Фрейм для ввода ответа
        input_frame = ttk.Frame(dialog_frame)
        input_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E))
        input_frame.columnconfigure(0, weight=1)
        
        # Поле для ввода ответа
        self.answer_var = tk.StringVar()
        self.answer_entry = ttk.Entry(input_frame, textvariable=self.answer_var, state=tk.DISABLED)
        self.answer_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 10))
        
        # Кнопка отправки
        self.send_button = ttk.Button(input_frame, text="Send", command=self.send_answer, state=tk.DISABLED)
        self.send_button.grid(row=0, column=1)
        
        # Очередь для ответов
        self.answer_queue = queue.Queue()
        self.current_question = None
        
        # Переменные для диалога
        self.dialog_active = False
        self.lawyer_context = {}  # Контекст для юриста (поля формы, шаблоны и т.д.)
        
        # Привязываем Enter к отправке ответа
        self.answer_entry.bind('<Return>', lambda e: self.send_answer())
        
        # Статус
        self.status_var = tk.StringVar(value="Ready to start")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, 
                                font=("Arial", 10, "bold"))
        status_label.grid(row=5, column=0, columnspan=2, pady=(10, 0))
        
        # Отладочная информация - показываем что кнопки созданы
        print("GUI Setup Complete - Buttons should be visible")
        print(f"Start button: {self.start_button}")
        print(f"Stop button: {self.stop_button}")
        
        # Принудительно обновляем GUI
        self.root.update()
        self.root.deiconify()  # Убеждаемся что окно видимо
        
    def setup_agent(self):
        """Настройка агента"""
        self.agent = None
        self.driver = None
        self.is_running = False
        self.current_question = None
        self.answer_queue = queue.Queue()
    
    def ask_question(self, question: str) -> str:
        """Показывает вопрос пользователю и ждет ответа"""
        self.current_question = question
        
        # Добавляем вопрос в диалог
        self.dialog_text.insert(tk.END, f"🤖 Lawyer: {question}\n")
        self.dialog_text.see(tk.END)
        
        # Активируем поле ввода
        self.answer_entry.config(state=tk.NORMAL)
        self.send_button.config(state=tk.NORMAL)
        self.answer_entry.focus()
        
        # Ждем ответа от пользователя
        try:
            answer = self.answer_queue.get(timeout=300)  # 5 минут таймаут
            return answer
        except queue.Empty:
            return ""
        finally:
            # Очищаем поле ввода
            self.answer_var.set("")
            self.answer_entry.config(state=tk.DISABLED)
            self.send_button.config(state=tk.DISABLED)
            self.current_question = None
    
    def send_answer(self):
        """Sends the user's answer"""
        answer = self.answer_var.get().strip()
        if answer and self.current_question:
            # Добавляем ответ в диалог
            self.dialog_text.insert(tk.END, f"💬 You: {answer}\n")
            self.dialog_text.see(tk.END)
            
            # Отправляем ответ в очередь
            self.answer_queue.put(answer)
            
                        # Очищаем поле ввода
            self.answer_var.set("")
    
    def start_lawyer_dialog(self, context: dict = None):
        """Starts a dialog with the lawyer"""
        self.dialog_active = True
        if context:
            self.lawyer_context = context
        
        # Очищаем диалог
        self.dialog_text.delete(1.0, tk.END)
        self.dialog_text.insert(tk.END, "🤖 Lawyer is ready to help you create a document.\n")
        self.dialog_text.see(tk.END)
        
        # Активируем поле ввода
        self.answer_entry.config(state=tk.NORMAL)
        self.send_button.config(state=tk.NORMAL)
        self.answer_entry.focus()
    
    def end_lawyer_dialog(self):
        """Ends the dialog with the lawyer"""
        self.dialog_active = False
        self.answer_entry.config(state=tk.DISABLED)
        self.send_button.config(state=tk.DISABLED)
        self.dialog_text.insert(tk.END, "🤖 Dialog finished.\n")
        self.dialog_text.see(tk.END)
    
    def lawyer_say(self, message: str):
        """Юрист говорит что-то пользователю"""
        self.dialog_text.insert(tk.END, f"🤖 Lawyer: {message}\n")
        self.dialog_text.see(tk.END)
    
    def log_message(self, message):
        """Добавляет сообщение в лог (без фильтрации)"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def start_agent(self):
        """Запускает агента в отдельном потоке"""
        if self.is_running:
            return
            
        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_var.set("Starting agent...")
        
        # Очищаем лог
        self.log_text.delete(1.0, tk.END)
        
        # Запускаем агента в отдельном потоке
        self.agent_thread = threading.Thread(target=self.run_agent_worker)
        self.agent_thread.daemon = True
        self.agent_thread.start()
        
        # Запускаем обработчик сообщений
        self.root.after(100, self.check_message_queue)
        
    def stop_agent(self):
        """Останавливает агента"""
        self.is_running = False
        self.status_var.set("Stopping agent...")
        
        if self.agent:
            self.agent.is_running = False
            
        driver = getattr(self, "driver", None)
        if driver:
            try:
                driver.quit()
            except Exception as e:
                print(f"Driver quit error: {e}")
        self.driver = None

                
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_var.set("Агент остановлен")
        
    def run_agent_worker(self):
        """Рабочая функция агента в отдельном потоке"""
        try:
            # Настройка WebDriver
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Инициализация драйвера
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Учетные данные
            credentials = {
                'email': self.email_var.get(),
                'password': self.password_var.get()
            }
            
            # Создание агента
            self.agent = MainAgent(self.driver, credentials)
            
            # Устанавливаем callback для взаимодействия с GUI
            self.agent.set_gui_callback(self.ask_question)
            
            # Переопределяем print для перенаправления в GUI
            original_print = print
            def gui_print(*args, **kwargs):
                message = " ".join(str(arg) for arg in args)
                self.message_queue.put(message)
                original_print(*args, **kwargs)
            
            # Временно заменяем print
            import builtins
            builtins.print = gui_print
            
            try:
                # Запуск рабочего процесса
                self.message_queue.put("🚀 Starting AI Document Creator Agent...")
                
                # Вызываем run_workflow с URL
                success = self.agent.run_workflow(Config.BASE_URL)
                
                if success:
                    self.message_queue.put("✅ Document creation completed successfully!")
                else:
                    self.message_queue.put("❌ Document creation failed")
                    
            except Exception as e:
                self.message_queue.put(f"❌ Workflow error: {str(e)}")
                self.message_queue.put("🔄 Agent will continue running for manual intervention...")
                
            finally:
                # Восстанавливаем оригинальный print
                builtins.print = original_print
                
        except Exception as e:
            self.message_queue.put(f"❌ Critical error: {str(e)}")
            self.message_queue.put("🔄 Agent will continue running for manual intervention...")
            # НЕ останавливаем агент при ошибках
            
    def check_message_queue(self):
        """Проверяет очередь сообщений от агента"""
        try:
            while True:
                message = self.message_queue.get_nowait()
                self.log_message(message)
        except queue.Empty:
            pass
            
        if self.is_running:
            self.root.after(100, self.check_message_queue)
        else:
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_var.set("Agent finished")

def main():
    """Главная функция"""
    root = tk.Tk()
    app = AgentGUI(root)
    
    # Обработчик закрытия окна
    def on_closing():
        if app.is_running:
            if messagebox.askokcancel("Exit", "The agent is still running. Stop and exit?"):
                app.stop_agent()
                root.destroy()
        else:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main() 