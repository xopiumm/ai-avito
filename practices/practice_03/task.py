import json
import os
from typing import List

"""
ПРАКТИКА 3: УПРАВЛЕНИЕ КОДИНГ-АГЕНТАМИ (CURSOR AI)
Курс: AI-инструменты в жизни инженера (ИТМО)

ИНСТРУКЦИЯ:
В этой практике мы учимся управлять AI-агентом через:
1. Контекст (@file, @codebase, фильтрация)
2. Правила (.cursorrules)
3. Multi-chat workflow (1 чат = 1 задача)
"""

STUDENT_INFO = {
    "full_name": "Дима Милана",
    "group_number": "M3305",
}

# =================================================================================================
# 1. ЖУРНАЛ УПРАВЛЕНИЯ КОНТЕКСТОМ
# =================================================================================================

class ContextLog:
    def __init__(self, task: str, context_used: str, prompt: str, result: str, analysis: str):
        self.task = task                # Какая задача? (напр. "Creating Pydantic model")
        self.context_used = context_used # Какой контекст? (@models.py, @codebase, filtered venv)
        self.prompt = prompt            # Ваш промпт
        self.result = result            # Что сгенерировал AI?
        self.analysis = analysis        # Анализ: помог ли контекст? Что изменилось?

CONTEXT_LOGS: List[ContextLog] = [
    # TODO: Заполните минимум 3 записи
    # Пример:
    # ContextLog(
    #     task="Creating Pydantic model",
    #     context_used="@models.py",
    #     prompt="@models.py Создай Pydantic v2 модель Subscription с полями city и email",
    #     result="Generated model with EmailStr validator",
    #     analysis="@file помог AI понять, куда писать код. Без @models.py создал бы в chat."
    # )
]

# =================================================================================================
# 2. ЖУРНАЛ ПРИМЕНЕНИЯ ПРАВИЛ (.cursorrules)
# =================================================================================================

class RuleLog:
    def __init__(self, rule_type: str, rule: str, task: str, applied: bool, result: str, analysis: str):
        self.rule_type = rule_type      # manual / auto-attached / always-included
        self.rule = rule                # Какое правило? (напр. "Use Pydantic v2 validators")
        self.task = task                # В какой задаче применялось?
        self.applied = applied          # Применилось ли автоматически? (True/False)
        self.result = result            # Что получилось?
        self.analysis = analysis        # Анализ эффективности правила

RULES_LOGS: List[RuleLog] = [
    # TODO: Заполните минимум 3 записи
    # Пример:
    # RuleLog(
    #     rule_type="auto-attached",
    #     rule="Use Pydantic v2 validators",
    #     task="Creating POST /subscribe endpoint",
    #     applied=True,
    #     result="AI automatically used field_validator instead of @validator",
    #     analysis="Auto-attached отлично работает для стандартных задач."
    # )
]

# =================================================================================================
# 3. ЖУРНАЛ MULTI-CHAT WORKFLOW
# =================================================================================================

class MultiChatLog:
    def __init__(self, chat_number: int, task: str, reason: str, result: str, context_size: str, analysis: str):
        self.chat_number = chat_number  # Номер чата (1, 2, 3...)
        self.task = task                # Какая задача?
        self.reason = reason            # Почему выбран отдельный чат?
        self.result = result            # Результат
        self.context_size = context_size # Размер контекста (Small/Medium/Large)
        self.analysis = analysis        # Помогла ли изоляция задачи?

MULTICHAT_LOGS: List[MultiChatLog] = [
    # TODO: Заполните минимум 3 записи (по количеству чатов в Задании 3)
    # Пример:
    # MultiChatLog(
    #     chat_number=1,
    #     task="DELETE /subscribe/{email}",
    #     reason="Isolated task: adding new endpoint without mixing validation context",
    #     result="Successfully created DELETE endpoint with 404 handling",
    #     context_size="Small (only @main.py, @models.py)",
    #     analysis="Separate chat prevented AI from suggesting unrelated changes."
    # )
]

# =================================================================================================
# 4. ЧЕК-ЛИСТ РЕАЛИЗАЦИИ
# =================================================================================================

IMPLEMENTATION_CHECKLIST = {
    "models_created": False,            # models.py с Subscription моделью
    "cursorrules_created": False,       # .cursorrules с минимум 5 правилами
    "health_endpoint": False,           # GET /health работает
    "post_subscribe": False,            # POST /subscribe работает
    "get_subscriptions": False,         # GET /subscriptions работает
    "delete_subscribe": False,          # DELETE /subscribe/{email} работает
    "response_models": False,           # Pydantic response models созданы
    "swagger_tested": False,            # Протестировано через Swagger UI
}

# =================================================================================================
# 5. РЕФЛЕКСИЯ
# =================================================================================================

REFLECTION = {
    "context_management": """
    TODO: Какие техники управления контекстом (@file, @codebase, фильтрация) были самыми полезными?
    Приведите пример, когда правильный контекст значительно улучшил результат.
    """,

    "rules_effectiveness": """
    TODO: Как .cursorrules повлияли на consistency кода?
    Сравните результаты с и без правил.
    """,

    "multichat_benefits": """
    TODO: Помог ли multi-chat workflow избежать смешения контекста?
    Приведите пример ситуации, когда отдельный чат был критичен.
    """,

    "auto_run_opinion": """
    TODO: В каких ситуациях вы бы использовали auto-run режим?
    Какие риски видите?
    """,

    "agents_md_preparation": """
    TODO: Какие правила и контекст вы хотите зафиксировать в Agents.md для Практики 4?
    """
}

# =================================================================================================
# ЭКСПОРТ
# =================================================================================================

def export_report():
    report = f"# Отчет по Практике 3: {STUDENT_INFO['full_name']}\n\n"

    report += "## 1. Журнал управления контекстом\n\n"
    for log in CONTEXT_LOGS:
        report += f"### Задача: {log.task}\n"
        report += f"**Контекст:** {log.context_used}\n"
        report += f"**Промпт:** {log.prompt}\n"
        report += f"**Результат:** {log.result}\n"
        report += f"**Анализ:** {log.analysis}\n"
        report += "---\n"

    report += "\n## 2. Журнал применения правил\n\n"
    for log in RULES_LOGS:
        report += f"### Правило: {log.rule} ({log.rule_type})\n"
        report += f"**Задача:** {log.task}\n"
        report += f"**Применено автоматически:** {'✅ Да' if log.applied else '❌ Нет'}\n"
        report += f"**Результат:** {log.result}\n"
        report += f"**Анализ:** {log.analysis}\n"
        report += "---\n"

    report += "\n## 3. Журнал Multi-Chat Workflow\n\n"
    for log in MULTICHAT_LOGS:
        report += f"### Chat {log.chat_number}: {log.task}\n"
        report += f"**Причина изоляции:** {log.reason}\n"
        report += f"**Результат:** {log.result}\n"
        report += f"**Размер контекста:** {log.context_size}\n"
        report += f"**Анализ:** {log.analysis}\n"
        report += "---\n"

    report += "\n## 4. Статус реализации\n\n"
    for item, status in IMPLEMENTATION_CHECKLIST.items():
        icon = "✅" if status else "❌"
        report += f"- {icon} {item}\n"

    report += "\n## 5. Рефлексия\n\n"
    report += f"**Управление контекстом:** {REFLECTION['context_management']}\n\n"
    report += f"**Эффективность правил:** {REFLECTION['rules_effectiveness']}\n\n"
    report += f"**Преимущества multi-chat:** {REFLECTION['multichat_benefits']}\n\n"
    report += f"**Мнение об auto-run:** {REFLECTION['auto_run_opinion']}\n\n"
    report += f"**Подготовка к Agents.md:** {REFLECTION['agents_md_preparation']}\n"

    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/report_p3.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ Отчет успешно сгенерирован: artifacts/report_p3.md")

if __name__ == "__main__":
    export_report()
