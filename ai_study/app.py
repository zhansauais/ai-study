from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import re 
import json
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("ОШИБКА: не найден GEMINI_API_KEY в файле .env")
else:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)


app = Flask(__name__)

GEMINI_MODEL = "gemini-3.5-flash"


def ask_gemini(prompt):
    """Отправляет запрос в Gemini и возвращает ответ на русском языке."""

    if not GEMINI_API_KEY:
        return "Ошибка: API-ключ Gemini не найден. Проверь файл .env."

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"""
Ты — ИИ-помощник учебной платформы AI Study.

Правила:
- Отвечай на русском языке.
- Пиши грамотно и понятно.
- Объясняй сложные темы простыми словами.
- Не используй китайские и японские символы.
- Если вопрос связан с учёбой, давай подробные и полезные объяснения.

Запрос пользователя:
{prompt}
"""
        )

        answer = response.text or "ИИ не вернул текстовый ответ."

        # Удаляем китайские и японские символы
        answer = re.sub(
            r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]',
            '',
            answer
        )

        return answer.strip()

    except Exception as e:
        print(f"Ошибка Gemini: {e}")
        return "Не удалось получить ответ от Gemini. Попробуй ещё раз."



app.secret_key = "ai-study-secret-key"


# =========================
# ПОДКЛЮЧЕНИЕ К БАЗЕ
# =========================

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn
# =========================
# AI-ПРИОРИТЕТ ЗАДАЧИ
# =========================

def calculate_priority(task):


    # Выполненная задача не требует дальнейшего планирования
    if task["completed"] == 1:
        return 0

    priority = 0

    # Чем ближе дедлайн, тем выше приоритет
    if task["deadline"]:
        try:
            deadline = date.fromisoformat(task["deadline"])
            days_left = (deadline - date.today()).days

            if days_left < 0:
                priority += 100
            elif days_left == 0:
                priority += 90
            elif days_left == 1:
                priority += 80
            elif days_left <= 3:
                priority += 60
            elif days_left <= 7:
                priority += 40
            else:
                priority += 20

        except ValueError:
            priority += 10

    # Задача без дедлайна получает небольшой базовый приоритет
    else:
        priority += 10

    return priority
def get_priority_reason(task):

    if task["completed"] == 1:
        return "Задача уже выполнена."

    if not task["deadline"]:
        return "У задачи нет дедлайна, поэтому она имеет базовый приоритет."

    try:
        deadline = date.fromisoformat(task["deadline"])
        days_left = (deadline - date.today()).days

        if days_left < 0:
            return "Дедлайн уже прошёл. Задачу рекомендуется выполнить как можно скорее."

        elif days_left == 0:
            return "Дедлайн сегодня. Задачу рекомендуется выполнить в первую очередь."

        elif days_left == 1:
            return "До дедлайна остался 1 день. Рекомендуется заняться задачей в ближайшее время."

        elif days_left <= 3:
            return f"До дедлайна осталось {days_left} дня. Задача требует повышенного внимания."

        elif days_left <= 7:
            return f"До дедлайна осталось {days_left} дней. Рекомендуется запланировать выполнение заранее."

        else:
            return f"До дедлайна ещё {days_left} дней. Задачу можно выполнять после более срочных."

    except ValueError:
        return "Не удалось определить корректную дату дедлайна."
        def get_ai_plan(tasks):
            plan = []

    for index, task in enumerate(tasks, start=1):
        priority = calculate_priority(task)

        if priority >= 90:
            action = "Выполнить в первую очередь"
        elif priority >= 60:
            action = "Выполнить сегодня"
        elif priority >= 40:
            action = "Запланировать на ближайшие дни"
        else:
            action = "Можно выполнить позже"

        plan.append({
            "number": index,
            "title": task["title"],
            "subject": task["subject"],
            "action": action
        })

    return plan
# =========================
# СОЗДАНИЕ ТАБЛИЦ
# =========================

def init_db():

    conn = get_db()

    # Таблица пользователей
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    # Таблица учебных задач
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT,
            deadline TEXT,
            completed INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# =========================
# ГЛАВНАЯ
# =========================

@app.route("/")
def home():
    return render_template("index.html")


# =========================
# РЕГИСТРАЦИЯ
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        password2 = request.form["password2"]

        if password != password2:
            return """
            <h2>Пароли не совпадают</h2>
            <a href="/register">Вернуться к регистрации</a>
            """

        hashed_password = generate_password_hash(password)

        try:

            conn = get_db()

            conn.execute(
                """
                INSERT INTO users (name, email, password)
                VALUES (?, ?, ?)
                """,
                (name, email, hashed_password)
            )

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            return """
            <h2>Пользователь с таким email уже существует</h2>
            <a href="/login">Перейти ко входу</a>
            """

    return render_template("register.html")


# =========================
# ВХОД
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if user is None:
            return """
            <h2>Пользователь не найден</h2>
            <a href="/login">Попробовать снова</a>
            """

        if not check_password_hash(user["password"], password):
            return """
            <h2>Неверный пароль</h2>
            <a href="/login">Попробовать снова</a>
            """

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session["user_email"] = user["email"]

        return redirect(url_for("dashboard"))

    return render_template("login.html")


# =========================
# ЛИЧНЫЙ КАБИНЕТ
# =========================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    tasks = conn.execute(
        """
        SELECT *
        FROM tasks
        WHERE user_id = ?
        ORDER BY completed ASC, deadline ASC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    total_tasks = len(tasks)

    completed_tasks = sum(
        1 for task in tasks
        if task["completed"] == 1
    )
    deadline_tasks = sum(
    1 for task in tasks
    if task["deadline"]
)

    if total_tasks > 0:
        progress = round(
            completed_tasks / total_tasks * 100
        )
    else:
        progress = 0

    return render_template(
        "dashboard.html",
        name=session["user_name"],
        email=session["user_email"],
        tasks=tasks,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        deadline_tasks=deadline_tasks,
        progress=progress
    )


# =========================
# ДОБАВЛЕНИЕ ЗАДАЧИ
# =========================

@app.route("/add_task", methods=["GET", "POST"])
def add_task():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        title = request.form["title"]
        subject = request.form["subject"]
        description = request.form["description"]
        deadline = request.form["deadline"]

        conn = get_db()

        conn.execute(
            """
            INSERT INTO tasks
            (user_id, title, subject, description, deadline)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                title,
                subject,
                description,
                deadline
            )
        )

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("add_task.html")


# =========================
# ВЫПОЛНЕНИЕ ЗАДАЧИ
# =========================

@app.route("/complete_task/<int:task_id>")
def complete_task(task_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    conn.execute(
        """
        UPDATE tasks
        SET completed = 1
        WHERE id = ? AND user_id = ?
        """,
        (task_id, session["user_id"])
    )

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))
# =========================
# РЕДАКТИРОВАНИЕ ЗАДАЧИ
# =========================

@app.route("/edit_task/<int:task_id>", methods=["GET", "POST"])
def edit_task(task_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    task = conn.execute(
        """
        SELECT *
        FROM tasks
        WHERE id = ? AND user_id = ?
        """,
        (task_id, session["user_id"])
    ).fetchone()

    if task is None:
        conn.close()
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        title = request.form["title"]
        subject = request.form["subject"]
        description = request.form["description"]
        deadline = request.form["deadline"]

        conn.execute(
            """
            UPDATE tasks
            SET title = ?,
                subject = ?,
                description = ?,
                deadline = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                title,
                subject,
                description,
                deadline,
                task_id,
                session["user_id"]
            )
        )

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    conn.close()

    return render_template(
        "edit_task.html",
        name=session["user_name"],
        task=task
    )

# =========================
# УДАЛЕНИЕ ЗАДАЧИ
# =========================

@app.route("/delete_task/<int:task_id>")
def delete_task(task_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    conn.execute(
        """
        DELETE FROM tasks
        WHERE id = ? AND user_id = ?
        """,
        (task_id, session["user_id"])
    )

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))

# =========================
# ДЕДЛАЙНЫ
# =========================
# =========================
# УЧЕБНЫЙ ПЛАН
# =========================

@app.route("/study_plan")
def study_plan():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    tasks = conn.execute(
        """
        SELECT *
        FROM tasks
        WHERE user_id = ?
        ORDER BY completed ASC, deadline ASC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "study_plan.html",
        name=session["user_name"],
        tasks=tasks
    )
# =========================
# AI-ПЛАНИРОВЩИК
# =========================
def get_ai_plan(tasks):
    plan = []

    for index, task in enumerate(tasks, start=1):
        priority = calculate_priority(task)

        if priority >= 90:
            action = "Срочно выполнить"
        elif priority >= 60:
            action = "Выполнить в ближайшее время"
        elif priority >= 40:
            action = "Запланировать"
        else:
            action = "Можно выполнить позже"

        plan.append({
            "number": index,
            "title": task["title"],
            "subject": task["subject"],
            "action": action
        })

    return plan
@app.route("/ai_plan")
def ai_plan():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    tasks = conn.execute(
        """
        SELECT *
        FROM tasks
        WHERE user_id = ?
        AND completed = 0
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    # Рассчитываем приоритет каждой задачи
    tasks = sorted(
        tasks,
        key=calculate_priority,
        reverse=True
    )
    ai_plan = get_ai_plan(tasks)

    return render_template(
        "ai_plan.html",
        name=session["user_name"],
        tasks=tasks,
        ai_plan=ai_plan,
        calculate_priority=calculate_priority,
        get_priority_reason=get_priority_reason
    )

@app.route("/deadlines")
def deadlines():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    tasks = conn.execute(
        """
        SELECT *
        FROM tasks
        WHERE user_id = ?
        AND deadline != ''
        ORDER BY deadline ASC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "deadlines.html",
        name=session["user_name"],
        tasks=tasks
    )
# =========================
# СТАТИСТИКА
# =========================

@app.route("/statistics")
def statistics():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    tasks = conn.execute(
        """
        SELECT *
        FROM tasks
        WHERE user_id = ?
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    total_tasks = len(tasks)

    completed_tasks = sum(
        1 for task in tasks
        if task["completed"] == 1
    )

    remaining_tasks = total_tasks - completed_tasks

    if total_tasks > 0:
        progress = round(
            completed_tasks / total_tasks * 100
        )
    else:
        progress = 0

    return render_template(
        "statistics.html",
        name=session["user_name"],
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        remaining_tasks=remaining_tasks,
        progress=progress
    )
# =========================
# ГЕНЕРАТОР УЧЕБНЫХ ТЕСТОВ
# =========================

@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    if "user_id" not in session:
        return redirect(url_for("login"))

    questions = []
    result = None
    answers = None

    subject = ""
    topic = ""
    count = 10
    error = None

    if request.method == "POST":
        action = request.form.get("action", "generate")

        subject = request.form.get("subject", "").strip()
        topic = request.form.get("topic", "").strip()

        try:
            count = int(request.form.get("count", 10))
        except (TypeError, ValueError):
            count = 10

        if not subject or not topic:
            error = "Укажи предмет и тему."

        elif count < 1 or count > 20:
            error = "Количество вопросов должно быть от 1 до 20."

        else:
            if action == "generate":
                prompt = f"""
Ты создаёшь учебный тест для школьника.

Предмет: {subject}
Тема: {topic}
Количество вопросов: {count}

Создай ровно {count} разных вопросов строго по указанному
предмету и теме.

Каждый вопрос должен иметь ровно 4 варианта ответа
и только один правильный вариант.

Отвечай ТОЛЬКО корректным JSON без Markdown и пояснений,
используя такую структуру:

{{
  "questions": [
    {{
      "question": "Текст вопроса",
      "options": [
        "Вариант 1",
        "Вариант 2",
        "Вариант 3",
        "Вариант 4"
      ],
      "correct": 0
    }}
  ]
}}

Поле correct — индекс правильного ответа: 0, 1, 2 или 3.
Все вопросы должны быть на русском языке.
Не добавляй вопросы по другим предметам.
"""

                try:
                    response = gemini_client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=prompt + """

Дополнительные требования:
- Создавай вопросы разной сложности.
- Включай вопросы на понимание, а не только на запоминание.
- Проверяй, что правильный ответ действительно верный.
- Не повторяй вопросы.
- Не используй китайские и японские символы.
- Верни только JSON без Markdown.

Структура ответа:
{
  "questions": [
    {
      "question": "Текст вопроса",
      "options": [
        "Вариант 1",
        "Вариант 2",
        "Вариант 3",
        "Вариант 4"
      ],
      "correct": 0
    }
  ]
}
"""
                    )

                    generated = json.loads(response.text)
                    raw_questions = generated.get("questions", [])

                    # Проверяем структуру вопросов
                    for q in raw_questions:
                        if not isinstance(q, dict):
                            continue

                        question_text = q.get("question")
                        options = q.get("options")
                        correct = q.get("correct")

                        if (
                            isinstance(question_text, str)
                            and question_text.strip()
                            and isinstance(options, list)
                            and len(options) == 4
                            and all(
                                isinstance(option, str) and option.strip()
                                for option in options
                            )
                            and type(correct) is int
                            and 0 <= correct < 4
                        ):
                            questions.append({
                                "question": question_text.strip(),
                                "options": options,
                                "correct": correct
                            })

                    if len(questions) != count:
                        questions = []
                        error = (
                            "Gemini не смог создать нужное количество "
                            "корректных вопросов. Попробуй ещё раз."
                        )

                except (ValueError, TypeError, KeyError, AttributeError) as e:
                    questions = []
                    error = (
                        "Не удалось обработать ответ Gemini. "
                        "Попробуй ещё раз."
                    )
                    print(f"Ошибка генерации теста: {e}")

                except Exception as e:
                    questions = []
                    error = (
                        "Gemini временно недоступен. "
                        "Попробуй ещё раз через некоторое время."
                    )
                    print(f"Ошибка Gemini: {e}")
                    

                    # Проверяем структуру и варианты ответов
                    for q in raw_questions:
                        if not isinstance(q, dict):
                            continue

                        question_text = q.get("question")
                        options = q.get("options")
                        correct = q.get("correct")

                        if (
                            isinstance(question_text, str)
                            and question_text.strip()
                            and isinstance(options, list)
                            and len(options) == 4
                            and all(
                                isinstance(option, str) and option.strip()
                                for option in options
                            )
                            and type(correct) is int
                            and 0 <= correct < 4
                        ):
                            questions.append({
                                "question": question_text.strip(),
                                "options": options,
                                "correct": correct
                            })

                    if len(questions) != count:
                        questions = []
                        error = (
                            "ИИ не смог создать нужное количество "
                            "корректных вопросов. Попробуй ещё раз."
                        )

                except (requests.exceptions.RequestException,
                        ValueError, KeyError, TypeError) as e:
                    questions = []
                    error = f"Не удалось создать тест. Проверь Ollama. Подробности: {e}"

            elif action == "check":
                try:
                    questions = json.loads(
                        request.form.get("questions_data", "[]")
                    )

                    if (
                        not isinstance(questions, list)
                        or not 1 <= len(questions) <= 20
                        or any(
                            not isinstance(q, dict)
                            or not isinstance(q.get("question"), str)
                            or not isinstance(q.get("options"), list)
                            or len(q["options"]) != 4
                            or type(q.get("correct")) is not int
                            or not 0 <= q["correct"] < 4
                            for q in questions
                        )
                    ):
                        raise ValueError("Некорректные данные теста.")

                    answers = []

                    for i in range(len(questions)):
                        try:
                            answer = int(request.form.get(f"q{i}", -1))
                        except (TypeError, ValueError):
                            answer = -1

                        answers.append(answer)

                    score = sum(
                        1 for i, q in enumerate(questions)
                        if answers[i] == q["correct"]
                    )

                    result = {
                        "score": score,
                        "total": len(questions),
                        "percent": round(score / len(questions) * 100)
                    }

                except (ValueError, TypeError):
                    questions = []
                    error = "Не удалось проверить тест. Создай его заново."

    return render_template(
        "quiz.html",
        questions=questions,
        result=result,
        answers=answers,
        subject=subject,
        topic=topic,
        count=count,
        error=error
    )


# =========================
# ЕЖЕДНЕВНОЕ ОБУЧЕНИЕ
# =========================

@app.route("/daily_learning")
def daily_learning():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    tasks = conn.execute(
        """
        SELECT title, subject, deadline, completed
        FROM tasks
        WHERE user_id = ?
        ORDER BY completed ASC, deadline ASC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    pending_tasks = [
        task for task in tasks
        if task["completed"] == 0
    ]

    completed_tasks = [
        task for task in tasks
        if task["completed"] == 1
    ]

    study_steps = []

    for task in pending_tasks[:5]:
        study_steps.append({
            "subject": task["subject"],
            "title": task["title"],
            "duration": 25
        })

    return render_template(
        "daily_learning.html",
        name=session["user_name"],
        study_steps=study_steps,
        completed_count=len(completed_tasks),
        pending_count=len(pending_tasks)
    )
# =========================
# ВЫХОД
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# =========================
# ЗАПУСК
# =========================
@app.route("/exam_prep", methods=["GET", "POST"])
def exam_prep():
    from datetime import date, datetime

    today = date.today().isoformat()

    subject = ""
    topic = ""
    exam_date = ""
    plan = []
    days_left = 0
    goal_name = ""

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        topic = request.form.get("topic", "").strip()
        exam_date = request.form.get("exam_date", "")
        goal = request.form.get("goal", "exam")
        hours = int(request.form.get("hours", 60))

        goals = {
            "exam": "Подготовка к экзамену",
            "midterm": "Подготовка к рубежному контролю",
            "lab": "Подготовка к лабораторной работе",
            "repeat": "Повторение материала"
        }

        goal_name = goals.get(goal, "Подготовка к экзамену")

        if not subject or not topic or not exam_date:
            return "Заполни все обязательные поля.", 400

        try:
            exam_day = datetime.strptime(
                exam_date, "%Y-%m-%d"
            ).date()

            if exam_day < date.today():
                return "Дата экзамена не может быть в прошлом.", 400

        except ValueError:
            return "Укажи корректную дату экзамена.", 400

        days_left = (exam_day - date.today()).days

        topics = [
            item.strip()
            for item in topic.replace("\n", ",").split(",")
            if item.strip()
        ]

        if not topics:
            topics = [topic]

        study_days = days_left + 1

        for day_number in range(min(study_days, 7)):
            current_topic = topics[day_number % len(topics)]

            if day_number == study_days - 1:
                title = "Финальное повторение"
                description = (
                    f"Повтори основные понятия по предмету "
                    f"{subject}, проверь свои знания и отдохни "
                    f"перед экзаменом."
                )
            else:
                title = f"День {day_number + 1}: {current_topic}"
                description = (
                    f"Изучи тему «{current_topic}» по предмету "
                    f"{subject}. Выдели {hours} минут на теорию "
                    f"и практику. В конце проверь, что ты усвоила."
                )

            plan.append({
                "title": title,
                "description": description
            })

        if days_left > 7:
            plan.append({
                "title": "Продолжение подготовки",
                "description": (
                    f"Продолжай изучать темы по очереди. "
                    f"До экзамена осталось {days_left} дней. "
                    f"Последний день перед экзаменом посвяти "
                    f"общему повторению."
                )
            })

    return render_template(
        "exam_prep.html",
        today=today,
        subject=subject,
        topic=topic,
        exam_date=exam_date,
        plan=plan,
        days_left=days_left,
        goal_name=goal_name
    )
@app.route("/calendar", methods=["GET", "POST"])
def calendar_page():
    import calendar as pycalendar
    from datetime import date, datetime
    from flask import flash, abort

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            subject TEXT DEFAULT '',
            event_date TEXT NOT NULL,
            kind TEXT DEFAULT 'other',
            description TEXT DEFAULT ''
        )
    """)
    conn.commit()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        subject = request.form.get("subject", "").strip()
        event_date = request.form.get("event_date", "").strip()
        kind = request.form.get("kind", "other")
        description = request.form.get("description", "").strip()

        if not title or not event_date:
            conn.close()
            flash("Заполни название и дату события.")
            return redirect(url_for("calendar_page"))

        try:
            datetime.strptime(event_date, "%Y-%m-%d")
        except ValueError:
            conn.close()
            flash("Укажи правильную дату.")
            return redirect(url_for("calendar_page"))

        if kind not in ("exam", "lab", "other"):
            kind = "other"

        conn.execute("""
            INSERT INTO calendar_events
            (user_id, title, subject, event_date, kind, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            title,
            subject,
            event_date,
            kind,
            description
        ))

        conn.commit()
        conn.close()

        flash("Событие успешно добавлено!")
        return redirect(url_for(
            "calendar_page",
            year=int(event_date[:4]),
            month=int(event_date[5:7]),
            day=int(event_date[8:10])
        ))

    today_date = date.today()

    try:
        year = int(request.args.get("year", today_date.year))
        month = int(request.args.get("month", today_date.month))
        selected_day = int(request.args.get("day", today_date.day))

        if not 1 <= month <= 12 or not 1 <= year <= 9999:
            raise ValueError

        _, days_in_month = pycalendar.monthrange(year, month)
        selected_day = min(max(selected_day, 1), days_in_month)

    except (ValueError, TypeError):
        year = today_date.year
        month = today_date.month
        selected_day = today_date.day

    selected_date = date(year, month, selected_day).isoformat()

    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1

    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1

    month_names = [
        "Январь", "Февраль", "Март", "Апрель",
        "Май", "Июнь", "Июль", "Август",
        "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]

    all_events = conn.execute("""
        SELECT *
        FROM calendar_events
        WHERE user_id = ?
          AND event_date >= ?
          AND event_date <= ?
        ORDER BY event_date
    """, (
        session["user_id"],
        f"{year:04d}-{month:02d}-01",
        f"{year:04d}-{month:02d}-{pycalendar.monthrange(year, month)[1]:02d}"
    )).fetchall()

    event_dates = {}

    for event in all_events:
        event_dates.setdefault(event["event_date"], [])
        if event["kind"] not in event_dates[event["event_date"]]:
            event_dates[event["event_date"]].append(event["kind"])

    selected_events_rows = conn.execute("""
        SELECT *
        FROM calendar_events
        WHERE user_id = ? AND event_date = ?
        ORDER BY title
    """, (session["user_id"], selected_date)).fetchall()

    selected_events = []

    for event in selected_events_rows:
        event_dict = dict(event)
        event_dict["days_left"] = (
            date.fromisoformat(event["event_date"]) - today_date
        ).days
        selected_events.append(event_dict)

    conn.close()

    return render_template(
        "calendar.html",
        year=year,
        month=month,
        month_name=month_names[month - 1],
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        today=today_date.isoformat(),
        selected_date=selected_date,
        calendar_weeks=pycalendar.monthcalendar(year, month),
        event_dates=event_dates,
        selected_events=selected_events
    )


@app.route("/calendar/delete/<int:event_id>")
def delete_calendar_event(event_id):
    from flask import flash

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    conn.execute("""
        DELETE FROM calendar_events
        WHERE id = ? AND user_id = ?
    """, (event_id, session["user_id"]))

    conn.commit()
    conn.close()

    flash("Событие удалено.")
    return redirect(url_for("calendar_page"))
@app.route("/ai_assistant", methods=["GET", "POST"])
def ai_assistant():
    if "user_id" not in session:
        return redirect(url_for("login"))

    answer = ""
    question = ""

    if request.method == "POST":
        question = request.form.get("question", "").strip()

        if question:
            prompt = f"""
Ты — ИИ-помощник для студентов.
Отвечай на русском языке.
Объясняй сложные темы простыми словами.
Помогай составлять учебные планы и готовиться к экзаменам.

Вопрос студента: {question}
"""
            answer = ask_gemini(prompt)

    return render_template(
        "ai_assistant.html",
        answer=answer,
        question=question
    )
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
    def test_gemini():
        if not GEMINI_API_KEY:
            print("API-ключ не найден. Проверь файл .env")
        return

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Ответь одним предложением на русском языке: что такое фотосинтез?"
        )
        print("\nОтвет Gemini:")
        print(response.text)

    except Exception as e:
        print("\nОшибка Gemini:", e)