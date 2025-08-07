import os
import certifi
import httpx
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Импорты из нашего проекта
from config import Config
from agents.main_agent import MainAgent

# Настройка SSL и прокси
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['SSL_CERT_FILE'] = certifi.where()

# Создаем транспорт с прокси
transport = httpx.HTTPTransport(
    proxy=Config.PROXY_URL,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    retries=3
)

# Создаем HTTP-клиент с транспортом
http_client = httpx.Client(transport=transport)

# Подавление логов TensorFlow
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

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

def request_credentials():
    """Запрос учетных данных у пользователя"""
    print("\n" + "="*50)
    print("🔐 Authorization Required")
    print("="*50)
    
    # Используем значения по умолчанию или запрашиваем у пользователя
    email = input(f"Enter your email (default: {Config.DEFAULT_EMAIL}): ").strip()
    if not email:
        email = Config.DEFAULT_EMAIL
    
    password = input(f"Enter your password (default: {Config.DEFAULT_PASSWORD}): ").strip()
    if not password:
        password = Config.DEFAULT_PASSWORD
    
    return {
        'email': email,
        'password': password
    }

def main():
    """Основная функция"""
    print("🤖 AI Document Creator Agent - LangChain Version")
    print("="*60)
    
    try:
        # Запрашиваем учетные данные
        credentials = request_credentials()
        
        # Настраиваем драйвер
        print("🔧 Setting up WebDriver...")
        driver = setup_driver()
        
        # Создаем агента
        print("🧠 Initializing AI Agent...")
        agent = MainAgent(driver, credentials)
        
        # Запускаем рабочий процесс
        print("🚀 Starting workflow...")
        success = agent.run_workflow(Config.BASE_URL)
        
        if success:
            print("\n✅ Workflow completed successfully!")
        else:
            print("\n❌ Workflow failed!")
            
        # Выводим финальную статистику
        status = agent.get_status()
        print(f"\n📊 Final Statistics:")
        print(f"   Total Actions: {status['total_actions']}")
        print(f"   User Responses: {status['total_user_responses']}")
        print(f"   Recent Errors: {status['recent_errors']}")
        
    except KeyboardInterrupt:
        print("\n⏹️  Workflow interrupted by user")
    except Exception as e:
        print(f"\n❌ Critical error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Закрываем драйвер
        try:
            if 'driver' in locals():
                driver.quit()
                print("🔒 WebDriver closed")
        except:
            pass

if __name__ == "__main__":
    main() 