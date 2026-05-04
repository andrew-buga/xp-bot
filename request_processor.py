#!/usr/bin/env python3
"""
REQUEST PROCESSOR — Автоматичний оркестратор VALIDATION → TEST → DEPLOY

Використання:
    python request_processor.py validate        # Stage 1: Перевірка синтаксису + лінтинг
    python request_processor.py test            # Stage 2: Запуск тестів
    python request_processor.py deploy          # Stage 3: Деплой
    python request_processor.py check-pre-commit # Усі три стадії разом
"""

import os
import sys
import subprocess
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Tuple, List, Dict, Any

# ANSI colors для терміналу
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

class RequestProcessor:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.validation_passed = False
        self.tests_passed = False
        self.results: Dict[str, Any] = {
            'timestamp': self.timestamp,
            'stages': {}
        }

    def print_header(self, text: str, stage: str = ""):
        """Красивий заголовок"""
        prefix = f"[{stage}]" if stage else "[INFO]"
        print(f"\n{Colors.BOLD}{Colors.BLUE}{prefix} {text}{Colors.END}")

    def print_success(self, text: str):
        """Успіх (зелено)"""
        print(f"{Colors.GREEN}✓ {text}{Colors.END}")

    def print_error(self, text: str):
        """Помилка (червоно)"""
        print(f"{Colors.RED}✗ {text}{Colors.END}")

    def print_warning(self, text: str):
        """Попередження (жовто)"""
        print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

    def print_info(self, text: str):
        """Інформація (блакитно)"""
        print(f"{Colors.BLUE}→ {text}{Colors.END}")

    # ============================================
    # STAGE 1: VALIDATION
    # ============================================

    def validate_syntax(self) -> bool:
        """Перевірка синтаксису Python для всіх файлів"""
        self.print_header("Перевіка синтаксису Python", "VALIDATION")
        
        py_files = list(self.project_root.glob("*.py"))
        errors = []
        
        for file_path in py_files:
            # Пропускаємо тестові файли на цьому етапі
            if file_path.name.startswith("test_") or file_path.name.startswith("check_"):
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    compile(f.read(), str(file_path), 'exec')
                self.print_success(f"{file_path.name}")
            except SyntaxError as e:
                error_msg = f"{file_path.name}: {e.msg} (line {e.lineno})"
                errors.append(error_msg)
                self.print_error(error_msg)
        
        if errors:
            self.results['stages']['syntax'] = {
                'status': 'FAIL',
                'errors': errors,
                'count': len(errors)
            }
            return False
        
        self.results['stages']['syntax'] = {
            'status': 'PASS',
            'files_checked': len(py_files),
        }
        self.print_success(f"Синтаксис OK для {len(py_files)} файлів")
        return True

    def validate_linting(self) -> bool:
        """Запуск ruff для лінтингу"""
        self.print_header("Перевірка лінтингу (Ruff)", "VALIDATION")
        
        try:
            # Перевіряємо, чи встановлений ruff
            result = subprocess.run(
                ["ruff", "check", ".", "--output-format=json"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                try:
                    issues = json.loads(result.stdout)
                    
                    # Групуємо помилки за файлами
                    errors_by_file = {}
                    for issue in issues:
                        file_name = Path(issue.get('filename', 'unknown')).name
                        if file_name not in errors_by_file:
                            errors_by_file[file_name] = []
                        errors_by_file[file_name].append({
                            'code': issue.get('code', 'UNKNOWN'),
                            'message': issue.get('message', ''),
                            'line': issue.get('location', {}).get('row', '?')
                        })
                    
                    if errors_by_file:
                        self.print_warning(f"Знайдено {len(issues)} помилок лінтингу:")
                        for file_name, file_issues in errors_by_file.items():
                            self.print_info(f"{file_name}:")
                            for issue in file_issues:
                                print(f"    {Colors.YELLOW}[{issue['code']}]{Colors.END} "
                                      f"Line {issue['line']}: {issue['message']}")
                        
                        self.results['stages']['linting'] = {
                            'status': 'FAIL',
                            'errors': errors_by_file,
                            'total_issues': len(issues)
                        }
                        return False
                
                except json.JSONDecodeError:
                    # JSON parse error, але це не фатально
                    self.print_warning("Ruff вивід не парсується як JSON, але перевірка пройшла")
            
            self.results['stages']['linting'] = {
                'status': 'PASS',
                'issues': 0
            }
            self.print_success("Лінтинг OK")
            return True
            
        except FileNotFoundError:
            self.print_warning("Ruff не встановлений, пропускаємо лінтинг")
            self.print_info("Встанови: pip install ruff")
            self.results['stages']['linting'] = {
                'status': 'SKIPPED',
                'reason': 'ruff not installed'
            }
            return True  # Не критично

    def validate_critical_files(self) -> bool:
        """Перевіряємо критичні файли"""
        self.print_header("Перевірка критичних файлів", "VALIDATION")
        
        critical_files = [
            'bot.py',
            'database.py',
            'config.py'
        ]
        
        missing = []
        for file_name in critical_files:
            file_path = self.project_root / file_name
            if file_path.exists():
                self.print_success(f"✓ {file_name} існує")
            else:
                missing.append(file_name)
                self.print_error(f"✗ {file_name} не знайдено!")
        
        if missing:
            self.results['stages']['critical_files'] = {
                'status': 'FAIL',
                'missing': missing
            }
            return False
        
        self.results['stages']['critical_files'] = {
            'status': 'PASS',
            'checked': critical_files
        }
        return True

    def stage_validation(self) -> bool:
        """STAGE 1: Запуск усіх перевірок"""
        self.print_header("STAGE 1: VALIDATION", "STAGE1")
        self.print_info("Перевіряємо синтаксис, лінтинг та критичні файли...")
        
        results = [
            self.validate_syntax(),
            self.validate_linting(),
            self.validate_critical_files(),
        ]
        
        self.validation_passed = all(results)
        
        if self.validation_passed:
            self.print_success("✅ VALIDATION PASSED — перейди до тестів")
            return True
        else:
            self.print_error("❌ VALIDATION FAILED — поправ помилки перед тестами!")
            return False

    # ============================================
    # STAGE 2: TESTING
    # ============================================

    def run_tests(self) -> bool:
        """Запуск усіх тестів"""
        self.print_header("Пошук та запуск тестів", "TESTING")
        
        test_files = list(self.project_root.glob("test_*.py"))
        
        if not test_files:
            self.print_warning("Тестові файли не знайдені (test_*.py)")
            self.results['stages']['tests'] = {
                'status': 'SKIPPED',
                'reason': 'No test files found'
            }
            return True  # Не критично
        
        self.print_info(f"Знайдено {len(test_files)} тестових файлів: {', '.join([f.name for f in test_files])}")
        
        all_passed = True
        test_results = {}
        
        for test_file in test_files:
            self.print_info(f"Запускаємо {test_file.name}...")
            
            try:
                result = subprocess.run(
                    [sys.executable, str(test_file)],
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    self.print_success(f"{test_file.name} пройшов")
                    test_results[test_file.name] = {'status': 'PASS'}
                else:
                    self.print_error(f"{test_file.name} провалився!")
                    if result.stderr:
                        print(f"    {result.stderr[:200]}")
                    test_results[test_file.name] = {
                        'status': 'FAIL',
                        'error': result.stderr[:500]
                    }
                    all_passed = False
                    
            except subprocess.TimeoutExpired:
                self.print_error(f"{test_file.name} зайняв занадто довго (timeout)")
                test_results[test_file.name] = {'status': 'TIMEOUT'}
                all_passed = False
            except Exception as e:
                self.print_error(f"Помилка при запуску {test_file.name}: {e}")
                test_results[test_file.name] = {'status': 'ERROR', 'error': str(e)}
                all_passed = False
        
        self.results['stages']['tests'] = {
            'status': 'PASS' if all_passed else 'FAIL',
            'tests_run': len(test_files),
            'results': test_results
        }
        
        return all_passed

    def check_db_integrity(self) -> bool:
        """Запускаємо детальну перевірку БД"""
        self.print_header("Перевірка цілісності БД", "TESTING")
        
        check_script = self.project_root / "detailed_integrity_check.py"
        if not check_script.exists():
            self.print_warning(f"{check_script.name} не знайдено, пропускаємо")
            return True
        
        self.print_info("Запускаємо detailed_integrity_check.py...")
        
        try:
            result = subprocess.run(
                [sys.executable, str(check_script)],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.print_success("БД цілісна ✓")
                self.results['stages']['db_integrity'] = {'status': 'PASS'}
                return True
            else:
                self.print_error("БД має проблеми! Дивись лог:")
                print(result.stdout if result.stdout else result.stderr)
                self.results['stages']['db_integrity'] = {
                    'status': 'FAIL',
                    'output': (result.stdout or result.stderr)[:500]
                }
                return False
                
        except Exception as e:
            self.print_warning(f"Не можу перевірити БД: {e}")
            self.results['stages']['db_integrity'] = {
                'status': 'SKIPPED',
                'reason': str(e)
            }
            return True  # Не зупиняємо деплой

    def stage_testing(self) -> bool:
        """STAGE 2: Запуск тестів"""
        self.print_header("STAGE 2: TESTING", "STAGE2")
        
        if not self.validation_passed:
            self.print_error("❌ Validation не пройшла! Пропускаємо тести")
            return False
        
        self.print_info("Запускаємо тести та перевірки...")
        
        results = [
            self.run_tests(),
            self.check_db_integrity(),
        ]
        
        self.tests_passed = all(results)
        
        if self.tests_passed:
            self.print_success("✅ TESTING PASSED — готово для деплою")
            return True
        else:
            self.print_error("❌ TESTING FAILED — виправ тести перед деплоєм!")
            return False

    # ============================================
    # STAGE 3: DEPLOYMENT
    # ============================================

    def backup_database(self) -> bool:
        """Створюємо резервну копію БД"""
        self.print_header("Резервна копія БД", "DEPLOY")
        
        db_file = self.project_root / "bot_data.db"
        if not db_file.exists():
            self.print_warning("bot_data.db не знайдено")
            self.results['stages']['backup'] = {
                'status': 'SKIPPED',
                'reason': 'No database file'
            }
            return True
        
        backup_dir = self.project_root / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        backup_file = backup_dir / f"bot_data.db.backup.{self.timestamp}"
        
        try:
            shutil.copy2(db_file, backup_file)
            self.print_success(f"Резервна копія: {backup_file.name}")
            self.results['stages']['backup'] = {
                'status': 'SUCCESS',
                'file': str(backup_file)
            }
            return True
        except Exception as e:
            self.print_error(f"Не можу зробити резервну копію: {e}")
            self.results['stages']['backup'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False

    def git_operations(self) -> bool:
        """Git push та commit"""
        self.print_header("Git операції", "DEPLOY")
        
        # Перевіряємо чи є зміни
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True
            )
            
            if result.stdout.strip():
                self.print_warning("Є незакомічені зміни, додаємо всі файли...")
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=str(self.project_root),
                    capture_output=True
                )
                
                # Автоматична повідомлення
                commit_msg = f"🔄 Pipeline deployment — {self.timestamp}"
                result = subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    self.print_success("Commit успішний")
                else:
                    self.print_warning("Нічого для коміту")
            
            # Git push
            self.print_info("Git push...")
            result = subprocess.run(
                ["git", "push"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.print_success("Git push успішний")
                self.results['stages']['git'] = {'status': 'SUCCESS'}
                return True
            else:
                self.print_error(f"Git push помилка: {result.stderr}")
                self.results['stages']['git'] = {
                    'status': 'FAIL',
                    'error': result.stderr
                }
                return False
                
        except Exception as e:
            self.print_error(f"Git операція помилка: {e}")
            self.results['stages']['git'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False

    def restart_service(self) -> bool:
        """Перезавантажимо системд сервіс"""
        self.print_header("Рестарт сервісу", "DEPLOY")
        
        try:
            # Перевіряємо чи працює сервіс
            result = subprocess.run(
                ["systemctl", "status", "xp-bot"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                self.print_warning("Сервіс xp-bot не активний, пропускаємо рестарт")
                self.results['stages']['service_restart'] = {
                    'status': 'SKIPPED',
                    'reason': 'Service not running'
                }
                return True
            
            # Рестартуємо
            self.print_info("systemctl restart xp-bot...")
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "xp-bot"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                self.print_success("Сервіс перезавантажений ✓")
                self.results['stages']['service_restart'] = {'status': 'SUCCESS'}
                return True
            else:
                self.print_error(f"Помилка перезавантаження: {result.stderr}")
                self.results['stages']['service_restart'] = {
                    'status': 'FAIL',
                    'error': result.stderr
                }
                return False
                
        except Exception as e:
            self.print_warning(f"Не можу перезавантажити сервіс (можливо, локальна машина): {e}")
            self.results['stages']['service_restart'] = {
                'status': 'SKIPPED',
                'reason': str(e)
            }
            return True  # Не критично

    def check_service_logs(self) -> bool:
        """Перевіряємо логи сервісу на помилки"""
        self.print_header("Перевірка логів сервісу", "DEPLOY")
        
        try:
            result = subprocess.run(
                ["journalctl", "-u", "xp-bot", "-n", "20", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            logs = result.stdout
            
            # Перевіряємо чи немає критичних помилок
            error_keywords = ["ERROR", "CRITICAL", "Traceback", "Exception"]
            has_errors = any(keyword in logs for keyword in error_keywords)
            
            if has_errors:
                self.print_error("⚠️ Знайдено помилки в логах!")
                print(logs[-1000:])  # Показуємо останні 1000 символів
                self.results['stages']['logs'] = {
                    'status': 'WARNING',
                    'sample': logs[-500:]
                }
                return False
            else:
                self.print_success("Логи в порядку ✓")
                self.results['stages']['logs'] = {'status': 'PASS'}
                return True
                
        except Exception as e:
            self.print_warning(f"Не можу перевірити логи: {e}")
            self.results['stages']['logs'] = {
                'status': 'SKIPPED',
                'reason': str(e)
            }
            return True

    def stage_deployment(self) -> bool:
        """STAGE 3: Деплой"""
        self.print_header("STAGE 3: DEPLOYMENT", "STAGE3")
        
        if not self.validation_passed or not self.tests_passed:
            self.print_error("❌ Validation или Testing не пройшли!")
            self.print_error("❌ DEPLOYMENT ABORTED — виправ помилки!")
            return False
        
        self.print_info("Всі перевірки пройшли, починаємо деплой...")
        
        # Pre-deploy backup
        if not self.backup_database():
            return False
        
        # Git operations
        if not self.git_operations():
            self.print_error("Git операція невдала, скасовуємо деплой!")
            return False
        
        # Service restart
        self.restart_service()
        
        # Check logs
        self.check_service_logs()
        
        self.print_success("✅ DEPLOYMENT COMPLETE — система live!")
        return True

    # ============================================
    # OUTPUT RESULTS
    # ============================================

    def save_results(self):
        """Зберігаємо результати в JSON"""
        results_file = self.project_root / f"deployment_results_{self.timestamp}.json"
        
        try:
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            self.print_info(f"Результати збережені: {results_file.name}")
        except Exception as e:
            self.print_warning(f"Не можу зберегти результати: {e}")

    def print_summary(self):
        """Красивий звіт"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}📋 DEPLOYMENT SUMMARY — {self.timestamp}{Colors.END}")
        print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")
        
        for stage_name, stage_info in self.results['stages'].items():
            status = stage_info.get('status', 'UNKNOWN')
            
            if status == 'PASS' or status == 'SUCCESS':
                color = Colors.GREEN
                symbol = "✅"
            elif status == 'FAIL':
                color = Colors.RED
                symbol = "❌"
            else:
                color = Colors.YELLOW
                symbol = "⚠️"
            
            print(f"{symbol} {stage_name.upper()}: {color}{status}{Colors.END}")
        
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}\n")

    # ============================================
    # MAIN ENTRY POINTS
    # ============================================

    def validate_only(self):
        """python request_processor.py validate"""
        self.stage_validation()
        self.print_summary()
        self.save_results()
        return 0 if self.validation_passed else 1

    def test_only(self):
        """python request_processor.py test"""
        if not self.validation_passed:
            if not self.stage_validation():
                self.print_warning("Validation не пройшла, але продовжуємо тести...")
        
        self.stage_testing()
        self.print_summary()
        self.save_results()
        return 0 if self.tests_passed else 1

    def deploy_only(self):
        """python request_processor.py deploy"""
        if not self.validation_passed:
            if not self.stage_validation():
                self.print_error("Validation не пройшла!")
                return 1
        
        if not self.tests_passed:
            if not self.stage_testing():
                self.print_error("Testing не пройшов!")
                return 1
        
        self.stage_deployment()
        self.print_summary()
        self.save_results()
        return 0

    def check_pre_commit(self):
        """python request_processor.py check-pre-commit"""
        self.print_header("🚀 FULL PIPELINE CHECK", "PRE-COMMIT")
        
        if not self.stage_validation():
            return 1
        
        if not self.stage_testing():
            return 1
        
        self.print_success("✅ Усі перевірки пройшли! Готово для деплою")
        self.print_info("Запусти: python request_processor.py deploy")
        
        self.print_summary()
        self.save_results()
        return 0


def main():
    if len(sys.argv) < 2:
        print(f"""
{Colors.BOLD}REQUEST PROCESSOR — Система обробки запитів{Colors.END}

Використання:
  python request_processor.py validate         # Stage 1: Перевірка синтаксису
  python request_processor.py test             # Stage 2: Запуск тестів
  python request_processor.py deploy           # Stage 3: Деплой
  python request_processor.py check-pre-commit # Усі три стадії разом

Дивись REQUEST_PIPELINE.md для деталей.
        """)
        return 1
    
    command = sys.argv[1]
    processor = RequestProcessor()
    
    if command == "validate":
        return processor.validate_only()
    elif command == "test":
        return processor.test_only()
    elif command == "deploy":
        return processor.deploy_only()
    elif command == "check-pre-commit":
        return processor.check_pre_commit()
    else:
        print(f"{Colors.RED}❌ Невідома команда: {command}{Colors.END}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
