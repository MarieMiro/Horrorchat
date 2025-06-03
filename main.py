import os
import time
import threading
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
from openai import OpenAI
from story import story

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Инициализация
client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# Состояния пользователей
user_states = {}  # user_id -> {"scene": ..., "step": ...}
user_locks = {}   # user_id -> threading.Lock


def get_user_state(user_id):
    if user_id not in user_states:
        user_states[user_id] = {"scene": "ep1_intro", "step": 0}
    if user_id not in user_locks:
        user_locks[user_id] = threading.Lock()
    return user_states[user_id]

def collect_context(scene, current_step):
    """Собираем все предыдущие реплики в виде живого чата"""
    history = []
    for i in range(current_step):
        step = scene["steps"][i]
        for line in step.get("characters", []):
            history.append(f'{line["name"]}: {line["line"]}')
    return "\n".join(history)

def gpt_reply(scene, step_index, user_input):
    step = scene["steps"][step_index]
    characters = step.get("characters", [])
    character_names = [c["name"] for c in characters]
    context = collect_context(scene, step_index)

    prompt = f"""
Ты — один из следующих персонажей: {', '.join(character_names)}.
Пользователь играет за героиню Алекс и пишет от её имени. Ты отвечаешь от других персонажей в формате чата.
Контекст истории до этого:
{context}

Ответь от одного из этих персонажей. Не описывай действия. Не пиши от лица Алекс. Только короткие реплики, живо и по-человечески. Пример:
Имя: реплика
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.7,
            max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка GPT: {str(e)}"

def send_step_messages(user_id, chat_id):
    state = get_user_state(user_id)
    scene = story[state["scene"]]
    step_index = state["step"]

    if step_index >= len(scene["steps"]):
        return  # конец сцены

    step = scene["steps"][step_index]
    if "text" in step:
        bot.send_message(chat_id=chat_id, text=step["text"])
        time.sleep(7)

    for character in step.get("characters", []):
        bot.send_message(chat_id=chat_id, text=f'{character["name"]}: {character["line"]}')
        time.sleep(7)

    state["step"] += 1

def continue_story(user_id, chat_id):
    def run():
        lock = user_locks.setdefault(user_id, threading.Lock())
        with lock:
            send_step_messages(user_id, chat_id)
    threading.Thread(target=run).start()

def start(update, context):
    user_id = update.message.chat_id
    user_states[user_id] = {"scene": "ep1_intro", "step": 0}
    user_locks[user_id] = threading.Lock()  # <- добавьте эту строку
    continue_story(user_id, update.message.chat_id)

def handle_message(update, context):
    user_id = update.message.chat_id
    user_input = update.message.text.strip()
    state = get_user_state(user_id)
    scene = story[state["scene"]]
    step_index = state["step"]

    # Ответ пользователю
    if step_index < len(scene["steps"]):
        reply = gpt_reply(scene, step_index, user_input)
        for line in reply.split("\n"):
            update.message.reply_text(line.strip())

    # Продолжение истории
    continue_story(user_id, update.message.chat_id)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

# Роутеры
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
