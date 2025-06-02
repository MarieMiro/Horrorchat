import os
import time
import threading
import json
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

# Инициализация клиентов
client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)


# Состояния пользователей
user_states = {}   # user_id -> {"scene": ..., "step": ...}
user_locks = {}    # user_id -> threading.Lock

def get_user_state(user_id):
    if user_id not in user_locks:
        user_locks[user_id] = threading.Lock()
    return user_states.setdefault(user_id, {"scene": "ep1_intro", "step": 0})

def collect_context(scene, current_step):
    context_lines = []
    for i in range(current_step):
        step = scene["steps"][i]
        for line in step.get("characters", []):
            context_lines.append(f'{line["name"]}: {line["line"]}')
    return "\n".join(context_lines)

def gpt_reply(scene, step_index, user_input):
    step = scene["steps"][step_index]
    characters = step.get("characters", [])
    character_names = [c["name"] for c in characters]
    context = collect_context(scene, step_index)

    prompt = f"""
Ты — один из следующих персонажей: {', '.join(character_names)}.
Алекс — главная героиня, пользователь играет за неё и пишет от её имени.
Ответь очень коротко и естественно, как в реальной переписке. Отвечай только от одного из доступных персонажей (не от Алекс)

Контекст истории:
{context}

Ответь очень коротко и естественно от имени одного из этих персонажей. Не описывай действия. Не добавляй ничего лишнего. Только короткая реплика в живом стиле.Не описывай действия, не отвечай от имени Алекс.

Пример:
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
    steps = scene["steps"]
    step_index = state["step"]

    if step_index >= len(steps):
        return  # Сценарий завершён

    step = steps[step_index]

    if "text" in step:
        bot.send_message(chat_id=chat_id, text=step["text"])
        time.sleep(10)

    for character in step.get("characters", []):
        bot.send_message(chat_id=chat_id, text=f'{character["name"]}: {character["line"]}')
        time.sleep(10)

    state["step"] += 1

def continue_story(chat_id, user_id):
    def run():
        if user_id not in user_locks:
            user_locks[user_id] = threading.Lock()  # ⬅️ гарантируем наличие замка

        with user_locks[user_id]:
            send_step_messages(user_id, chat_id)

    threading.Thread(target=run).start()

def start(update, context):
    user_id = update.message.chat_id
    user_states[user_id] = {"scene": "ep1_intro", "step": 0}
   continue_story(chat_id=update.message.chat_id, user_id=user_id)

def handle_message(update, context):
    user_id = update.message.chat_id
    user_input = update.message.text.strip()
    state = get_user_state(user_id)
    scene = story[state["scene"]]
    step_index = state["step"]

    if step_index < len(scene["steps"]):
        reply = gpt_reply(scene, step_index, user_input)
   update.message.reply_text(reply)

   continue_story(user_id=user_id, chat_id=update.message.chat_id)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

# Регистрация хендлеров
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# Запуск Flask-сервера
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
