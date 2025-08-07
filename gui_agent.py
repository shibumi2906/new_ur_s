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
from agents.main_agent import MainAgent
from config import Config

class AgentGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Document Creator Agent - MVP")
        self.root.geometry("800x600")
        
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
        main_frame.rowconfigure(2, weight=1)
        
        # Заголовок
        title_label = ttk.Label(main_frame, text="🤖 AI Document Creator Agent", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Фрейм для учетных данных
        cred_frame = ttk.LabelFrame(main_frame, text="Учетные данные", padding="10")
        cred_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Email
        ttk.Label(cred_frame, text="Email:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        email_entry = ttk.Entry(cred_frame, textvariable=self.email_var, width=40)
        email_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        
        # Password
        ttk.Label(cred_frame, text="Пароль:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))
        password_entry = ttk.Entry(cred_frame, textvariable=self.password_var, width=40, show="*")
        password_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(0, 10), pady=(10, 0))
        
        # Кнопки управления
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))
        
        self.start_button = ttk.Button(button_frame, text="🚀 Запустить агента", 
                                      command=self.start_agent)
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = ttk.Button(button_frame, text="⏹️ Остановить", 
                                     command=self.stop_agent, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT)
        
        # Область логов
        log_frame = ttk.LabelFrame(main_frame, text="Лог работы агента", padding="10")
        log_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Статус
        self.status_var = tk.StringVar(value="Готов к запуску")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, 
                                font=("Arial", 10, "bold"))
        status_label.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        
    def setup_agent(self):
        """Настройка агента"""
        self.agent = None
        self.driver = None
        self.agent_thread = None
        self.is_running = False
        
    def log_message(self, message):
        """Добавляет сообщение в лог"""
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
        self.status_var.set("Запуск агента...")
        
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
        self.status_var.set("Остановка агента...")
        
        if self.agent:
            self.agent.is_running = False
            
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
                
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
                success = self.agent.run_workflow(Config.BASE_URL)
                
                if success:
                    self.message_queue.put("✅ Document creation completed successfully!")
                else:
                    self.message_queue.put("⚠️ Document creation failed, but agent continues running...")
                    
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
            self.status_var.set("Агент завершил работу")

def main():
    """Главная функция"""
    root = tk.Tk()
    app = AgentGUI(root)
    
    # Обработчик закрытия окна
    def on_closing():
        if app.is_running:
            if messagebox.askokcancel("Выход", "Агент все еще работает. Остановить и выйти?"):
                app.stop_agent()
                root.destroy()
        else:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main() 