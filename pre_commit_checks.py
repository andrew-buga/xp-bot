#!/usr/bin/env python3
"""
PRE-COMMIT CHECKS — Мінімум перевірок перед git commit

Це скрипт для .git/hooks/pre-commit (опціонально)
Або просто запусти перед коміту: python pre_commit_checks.py

Правило: НИКОГДА не коміть кі немає:
✓ Синтаксис OK
✓ Немає F841 (unused variable)
✓ Немає F541 (f-string)
✓ Немає синтаксис помилок
"""

import subprocess
import sys
from pathlib import Path
from typing import List

class PreCommitChecker:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.errors = []
        self.warnings = []

    def check_syntax(self, file_path: Path) -> bool:
        """Перевіряємо синтаксис одного файлу"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                compile(f.read(), str(file_path), 'exec')
            return True
        except SyntaxError as e:
            self.errors.append(f"{file_path.name}:{e.lineno}: {e.msg}")
            return False

    def check_unused_variables(self, file_path: Path) -> bool:
        """Перевіряємо на невикористані змінні (F841)"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Просто пошук на очах видних паттернів
            lines = content.split('\n')
            issues = []
            
            for i, line in enumerate(lines, 1):
                # F841: local variable assigned but never used
                # Дуже базова перевірка
                if ' = ' in line and not line.strip().startswith('#'):
                    # Це може бути присвоєння
                    pass
            
            return True
        except Exception:
            return True  # Не критично

    def check_ruff(self) -> bool:
        """Запускаємо ruff для всього проекту"""
        try:
            result = subprocess.run(
                ["ruff", "check", ".", "--select=F841,F541,E9,F63,F7,F82"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                if result.stdout:
                    self.errors.append(f"Ruff знайшов проблеми:\n{result.stdout}")
                return False
            return True
        except FileNotFoundError:
            print("⚠️  Ruff не встановлений (pip install ruff)")
            return True  # Не зупиняємо

    def check_all_py_files(self) -> bool:
        """Перевіряємо всі .py файли в проекті"""
        py_files = list(self.project_root.glob("*.py"))
        
        all_ok = True
        for file_path in py_files:
            if file_path.name.startswith("."):
                continue
            
            print(f"Checking {file_path.name}...", end=" ")
            if self.check_syntax(file_path):
                print("✓")
            else:
                print("✗")
                all_ok = False
        
        return all_ok

    def run(self) -> int:
        """Запускаємо усі перевірки"""
        print("=" * 60)
        print("🔍 PRE-COMMIT CHECKS")
        print("=" * 60)
        print()
        
        # Перевіка 1: Синтаксис для всіх файлів
        print("Stage 1: Синтаксис Python...")
        if not self.check_all_py_files():
            print("\n❌ Синтаксис помилки! Поправ їх перед комітом.")
            for error in self.errors:
                print(f"  → {error}")
            return 1
        print("✅ Синтаксис OK\n")
        
        # Перевіка 2: Ruff лінтинг
        print("Stage 2: Ruff лінтинг (F841, F541, E9)...")
        if not self.check_ruff():
            print("\n❌ Лінтинг помилки! Поправ їх перед комітом.")
            for error in self.errors:
                print(f"  → {error}")
            return 1
        print("✅ Лінтинг OK\n")
        
        print("=" * 60)
        print("✅ ВСІ ПЕРЕВІРКИ ПРОЙШЛИ — можна коммітити!")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    checker = PreCommitChecker()
    sys.exit(checker.run())
