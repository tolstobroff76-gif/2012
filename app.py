import os
import requests
from flask import Flask, request, jsonify
from threading import Lock

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4.1-mini"

# Краткая история диалога для каждой сессии Алисы
dialog_history = {}
history_lock = Lock()

SYSTEM_PROMPT = """
Ты ChatGPT, голосовой помощник в Яндекс Алисе.
Отвечай на русском языке, дружелюбно, понятно и по существу.
Не используй Markdown, таблицы и сложное форматирование:
твой ответ будет озвучен голосом.
Если вопрос требует актуальной информации из интернета,
честно сообщи, если не можешь проверить её прямо сейчас.
Старайся отвечать кратко, но содержательно.
"""


def ask_chatgpt(user_text, session_id):
    if not OPENAI_API_KEY:
        return "Сервис пока не настроен. Не найден ключ OpenAI API."

    with history_lock:
        history = dialog_history.get(session_id, []).copy()

    conversation = ""
    for item in history[-6:]:
        conversation += f"{item['role']}: {item['text']}\n"

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"История предыдущего разговора:\n{conversation}\n"
        f"Новое сообщение пользователя: {user_text}"
    )

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": OPENAI_MODEL,
                "input": prompt,
                "max_output_tokens": 250
            },
            timeout=(2, 12)
        )

        response.raise_for_status()
        data = response.json()

        answer = data.get("output_text", "").strip()

        if not answer:
            for item in data.get("output", []):
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        answer += part.get("text", "")

        answer = answer.strip()

        if not answer:
            return "Не получилось сформировать ответ. Попробуй повторить вопрос."

        # Сохраняем последние реплики для продолжения разговора
        with history_lock:
            history = dialog_history.get(session_id, [])
            history.extend([
                {"role": "Пользователь", "text": user_text},
                {"role": "ChatGPT", "text": answer}
            ])
            dialog_history[session_id] = history[-12:]

        # Ограничение длины ответа для голосового интерфейса
        return answer[:1000]

    except requests.exceptions.Timeout:
        return "Ответ задерживается. Попробуй задать вопрос ещё раз."

    except requests.exceptions.RequestException:
        return "Не удалось связаться с ChatGPT. Попробуй немного позже."

    except Exception:
        return "Произошла ошибка при обработке запроса."


@app.route("/", methods=["GET"])
def home():
    return "ChatGPT Alice webhook is running!"


@app.route("/", methods=["POST"])
def alice_webhook():
    try:
        data = request.get_json(force=True)

        session = data.get("session", {})
        session_id = session.get("session_id", "default")

        user_text = data.get("request", {}).get(
            "command", ""
        ).strip()

        if not user_text:
            answer = "Привет! Я ChatGPT. Что хочешь узнать?"
        else:
            answer = ask_chatgpt(user_text, session_id)

        return jsonify({
            "version": "1.0",
            "response": {
                "text": answer,
                "end_session": False
            }
        })

    except Exception:
        return jsonify({
            "version": "1.0",
            "response": {
                "text": "Произошла ошибка. Попробуй повторить запрос.",
                "end_session": False
            }
        })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
