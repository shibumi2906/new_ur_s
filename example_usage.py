#!/usr/bin/env python3
"""
Пример использования AI Document Creator Agent

Этот файл демонстрирует, как использовать агента для автоматизации
создания документов на сайте https://app.conneto.com/
"""

import os
import sys
import time

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Config
from agents.main_agent import MainAgent
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def setup_driver():
    """Настройка Selenium WebDriver"""
    options = webdriver.ChromeOptions()
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # Добавляем опции для стабильности
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

def example_basic_usage():
    """Пример базового использования агента"""
    print("🚀 Пример базового использования AI Document Creator Agent")
    print("="*60)
    
    try:
        # Настройка драйвера
        print("🔧 Setting up WebDriver...")
        driver = setup_driver()
        
        # Учетные данные (можно изменить)
        credentials = {
            'email': Config.DEFAULT_EMAIL,
            'password': Config.DEFAULT_PASSWORD
        }
        
        # Создание агента
        print("🧠 Creating AI Agent...")
        agent = MainAgent(driver, credentials)
        
        # Запуск рабочего процесса
        print("🚀 Starting workflow...")
        start_time = time.time()
        
        success = agent.run_workflow(Config.BASE_URL)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Результаты
        if success:
            print(f"\n✅ Workflow completed successfully in {duration:.2f} seconds!")
        else:
            print(f"\n❌ Workflow failed after {duration:.2f} seconds")
        
        # Статистика
        status = agent.get_status()
        print(f"\n📊 Final Statistics:")
        print(f"   Duration: {duration:.2f} seconds")
        print(f"   Total Actions: {status['total_actions']}")
        print(f"   User Responses: {status['total_user_responses']}")
        print(f"   Recent Errors: {status['recent_errors']}")
        print(f"   Final State: {status['current_state']}")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Закрытие драйвера
        try:
            if 'driver' in locals():
                driver.quit()
                print("🔒 WebDriver closed")
        except:
            pass

def example_with_custom_credentials():
    """Пример использования с пользовательскими учетными данными"""
    print("\n🔐 Пример с пользовательскими учетными данными")
    print("="*60)
    
    # Запрос учетных данных у пользователя
    email = input("Enter your email: ").strip()
    password = input("Enter your password: ").strip()
    
    if not email or not password:
        print("❌ Email and password are required")
        return
    
    try:
        # Настройка драйвера
        driver = setup_driver()
        
        # Пользовательские учетные данные
        credentials = {
            'email': email,
            'password': password
        }
        
        # Создание агента
        agent = MainAgent(driver, credentials)
        
        # Запуск рабочего процесса
        success = agent.run_workflow(Config.BASE_URL)
        
        if success:
            print("✅ Document creation completed!")
        else:
            print("❌ Document creation failed!")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    finally:
        try:
            if 'driver' in locals():
                driver.quit()
        except:
            pass

def example_monitoring():
    """Пример с мониторингом процесса"""
    print("\n📊 Пример с мониторингом процесса")
    print("="*60)
    
    try:
        driver = setup_driver()
        credentials = {
            'email': Config.DEFAULT_EMAIL,
            'password': Config.DEFAULT_PASSWORD
        }
        
        agent = MainAgent(driver, credentials)
        
        # Запуск в отдельном потоке для мониторинга
        import threading
        
        def run_agent():
            return agent.run_workflow(Config.BASE_URL)
        
        def monitor_agent():
            while agent.is_running:
                status = agent.get_status()
                print(f"\r🔄 Status: {status['current_state']} | "
                      f"Actions: {status['total_actions']} | "
                      f"Responses: {status['total_user_responses']} | "
                      f"Errors: {status['recent_errors']}", end="")
                time.sleep(2)
        
        # Запуск мониторинга
        monitor_thread = threading.Thread(target=monitor_agent)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Запуск агента
        success = run_agent()
        
        print(f"\n\n{'✅ Success' if success else '❌ Failed'}")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
    finally:
        try:
            if 'driver' in locals():
                driver.quit()
        except:
            pass

def main():
    """Основная функция с выбором примера"""
    print("🤖 AI Document Creator Agent - Examples")
    print("="*50)
    
    print("Выберите пример:")
    print("1. Базовое использование")
    print("2. С пользовательскими учетными данными")
    print("3. С мониторингом процесса")
    print("4. Все примеры")
    
    choice = input("\nВведите номер (1-4): ").strip()
    
    if choice == "1":
        example_basic_usage()
    elif choice == "2":
        example_with_custom_credentials()
    elif choice == "3":
        example_monitoring()
    elif choice == "4":
        example_basic_usage()
        example_with_custom_credentials()
        example_monitoring()
    else:
        print("❌ Неверный выбор")

if __name__ == "__main__":
    main() 