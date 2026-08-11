
import os
import subprocess
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import argparse
import json
import io
import sys
import uuid
from datetime import datetime
import traceback

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8')

def load_paths(env_file):
    load_dotenv(dotenv_path=env_file)
    paths = {
        "newman_path": os.getenv("NEWMAN_PATH"),
        "collection_path": os.getenv("COLLECTION_PATH"),
        "environment_path": os.getenv("ENVIRONMENT_PATH")
    }
    print("Loaded paths:", paths)
    return paths

def run_postman_collection(collection_path, environment_path):
    """Запускает Postman Collection, возвращает результат и список зафейлившихся тестов."""

    if collection_path is None:
        print("Ошибка: collection_path is None")
        return False, "Ошибка: collection_path is None", [], 1, 0, 0, ""

    collection_name = os.path.basename(collection_path)
    newman_output = ""
    failed_tests = []
    return_code = 0
    test_result = 1
    total_tests = 0
    successful_tests = 0

    try:
        newman_path = os.getenv('NEWMAN_PATH')
        if not newman_path or not os.path.exists(newman_path):
            message = f"Ошибка: Переменная NEWMAN_PATH не определена или указывает на несуществующий файл: {newman_path}. Прогон {collection_name} прерван."
            print(message)
            send_email(f"Ошибка прогона {collection_name}", message)
            return False, message, failed_tests, 1, 0, 0, ""

        # Указываем путь к отчету
        report_path = os.path.join("путь\\к\\директории\\с\\проектом\\python_project\\py", "report.json") #Замените на действительный путь до \\phyton_project\\py. Обратите внимание, что слеши двойные
        
        # --- БЛОК АВТОМАТИЧЕСКОГО СОЗДАНИЯ ПАПОК (ДОБАВЛЕНО) ---
        report_dir = os.path.dirname(report_path)                      ### НОВАЯ СТРОКА
        if report_dir and not os.path.exists(report_dir):              ### НОВАЯ СТРОКА
            os.makedirs(report_dir, exist_ok=True)                     ### НОВАЯ СТРОКА
            print(f"Создана директория: {report_dir}")                 ### НОВАЯ СТРОКА
        # ------------------------------------------------------

        allure_results_dir = "allure-results"
        os.makedirs(allure_results_dir, exist_ok=True)

        command = [
            newman_path,
            "run",
            collection_path,
            "-e",
            environment_path,
            "-r",
            "json,allure",
            "--reporter-json-export",
            report_path,
            "--reporter-allure-export",
            allure_results_dir,
        ]
        print(f"Current working directory: {os.getcwd()}")
        print(f"Running command: {' '.join(command)}")

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        process.wait()
        stdout = process.stdout.read()
        stderr = process.stderr.read()
        return_code = process.returncode

        newman_output = f"Вывод Newman:\n{stdout}\nОшибки Newman:\n{stderr}"

        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)

            # Получаем общее количество тестов
            if "run" in report_data and "stats" in report_data["run"] and "items" in report_data["run"]["stats"]:
                total_tests = report_data["run"]["stats"]["items"]["total"]

            if "run" in report_data and "failures" in report_data["run"]:
                failed_tests_count = len(report_data["run"]["failures"])  # Считаем количество зафейленных тестов
            else:
                failed_tests_count = 0

            successful_tests = max(0, total_tests - failed_tests_count) # количество успешных тестов

            if "run" in report_data and "failures" in report_data["run"]:
                for failure in report_data["run"]["failures"]:
                    test_name = failure["source"]["name"]
                    error_message = failure["error"]["message"]

                    expected_code = None
                    actual_code = None

                    if "Получен неожиданный код ответа:" in error_message:
                        try:
                            actual_code = int(error_message.split("Получен неожиданный код ответа:")[1].strip())
                            if "Код ответа " in test_name:
                                expected_code = int(test_name.split("Код ответа ")[1].strip())
                        except:
                            pass

                    if expected_code is not None and actual_code is not None:
                        error_details = f"- ожидаемый код ответа {expected_code}, полученный код ответа {actual_code}"
                    else:
                        error_details = f"- {error_message}"

                    failed_tests.append(f"{test_name} {error_details}")
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Ошибка обработки JSON-отчета: {e} \n Полный вывод newman:\n{newman_output}")
            failed_tests.append(f"Ошибка обработки JSON отчета: {e}")
            test_result = 1
        except KeyError as e:
            print(f"Ошибка в JSON отчете: Отсутствует ключ - {e}. Полный вывод newman:\n{newman_output}")
            failed_tests.append(f"Ошибка в JSON отчете: Отсутствует ключ - {e}")
            test_result = 1

        if failed_tests:
            test_result = 1
        else:
            test_result = 0

        return True, newman_output, failed_tests, test_result, total_tests, successful_tests, collection_name

    except FileNotFoundError as e:
        message = f"Ошибка: файл не найден - {e}"
        print(message)
        send_email(f"Ошибка прогона {collection_name}", message)
        return False, message, [], 1, 0, 0, ""
    except Exception as e:
        message = f"Произошла непредвиденная ошибка: {e}  \n {traceback.format_exc()}"
        print(message)
        send_email(f"Ошибка прогона {collection_name}", message)
        return False, message, [], 1, 0, 0, ""

def send_email(subject, body, allure_report_url=None, failed_tests=None, total_tests=0, successful_tests=0, collection_name=""):
    """Отправляет электронное письмо со ссылкой на Allure-отчет."""
    sender_email = os.getenv('EMAIL_SENDER')
    sender_password = os.getenv('EMAIL_PASSWORD')
    receiver_email = os.getenv('EMAIL_RECIPIENT')
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = 587

    msg = MIMEMultipart('alternative')
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    # Формируем HTML-код для заголовка
    html_header = f"""
    <html>
      <head>
          <meta charset="UTF-8">
      </head>
      <body>
        <p>Прогон коллекции {collection_name} <span style="color: red;">{'завершился с ошибкой' if failed_tests else 'завершился успешно'}</span></p>
    """

    # Формируем текстовую версию письма
    text = f"Прогон коллекции {collection_name} {'завершился с ошибкой' if failed_tests else 'завершился успешно'}\n"
    text += f"Всего тестов: {total_tests}\n"
    text += f"Успешных тестов: {successful_tests}\n"
    if failed_tests:
        text += "\nНеудачные тесты:\n" + "\n".join(failed_tests)
    if allure_report_url:
        text += f"\n\nAllure Report: {allure_report_url}"

    # Формируем HTML-код для остальной части письма
    html_body = f"""
        <p>Всего тестов: {total_tests}</p>
        <p>Успешных тестов: {successful_tests}</p>
    """
    if failed_tests:
        html_body += f'<p><b>Проваленные тесты:</b></p><ul>'
        for test in failed_tests:
            html_body += f'<li>{test}</li>'
        html_body += '</ul>'

    if allure_report_url:
        html_body += f'<p><a href="{allure_report_url}">Allure Report</a></p>'

    html_footer = """
      </body>
    </html>
    """

    part1 = MIMEText(text, 'plain', 'utf-8')
    part2 = MIMEText(html_header + html_body + html_footer, 'html', 'utf-8')

    msg.attach(part1)
    msg.attach(part2)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("Письмо успешно отправлено!")
    except Exception as e:
        print(f"Ошибка при отправке письма: {e}")
        
def load_email_config():
    dotenv_path = r"путь\к\директории\с\проектом\.env.email"   #Замените на действительный путь к файлу .env.email, указанный в кавычках
    load_dotenv(dotenv_path=dotenv_path)
    config = {
        "sender_email": os.getenv("EMAIL_SENDER"),
        "sender_password": os.getenv("EMAIL_PASSWORD"),
        "receiver_email": os.getenv("EMAIL_RECIPIENT"),
        "smtp_server": os.getenv("SMTP_SERVER"),
        "smtp_port": 587
    }
    print("Email config:", config)
    return config

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Запуск Postman Collection.")
    parser.add_argument("--env", type=str, default=".env.paths", help="Путь к файлу .env с настройками путей.")
    args = parser.parse_args()

    paths = load_paths(args.env)
    try:
        email_config = load_email_config()
    except Exception as e:
        print(f"Ошибка при загрузке настроек email: {e}")
        email_config = {}

    collection_path = paths["collection_path"]
    environment_path = paths["environment_path"]

    print("Collection Path:", collection_path)
    print("Environment Path:", environment_path)

    success, newman_output, failed_tests, test_result, total_tests, successful_tests, collection_name = run_postman_collection(collection_path, environment_path)

   # Определяем allure_report_url здесь, чтобы она всегда была определена
allure_report_url = os.getenv("JENKINS_URL") + "job/" + os.getenv("JOB_NAME") + "/" + os.getenv("BUILD_NUMBER") + "/allure/" if os.getenv("JENKINS_URL") and os.getenv("JOB_NAME") and os.getenv("BUILD_NUMBER") else None

report = f"Прогон коллекции {collection_name} {'завершился успешно' if test_result == 0 else 'завершился с ошибкой'}\n"
report += f"\nВсего пройдено тестов: {total_tests}\n"
report += f"Успешных тестов: {successful_tests}\n"
if failed_tests:
    #report += "\nПроваленные тесты:\n" + "\n".join(failed_tests) # Убираем это из plain text
    pass # Ничего не добавляем в plain text, так как HTML версия письма покажет все корректно.

send_email(
    subject=f"Прогон коллекции {collection_name}",
    allure_report_url=allure_report_url,
    failed_tests=failed_tests,
    total_tests=total_tests,
    successful_tests=successful_tests,
    collection_name=collection_name,
    body = f"Прогон коллекции {collection_name} {'завершился успешно' if test_result == 0 else 'завершился с ошибкой'}"
)


sys.exit(test_result)
