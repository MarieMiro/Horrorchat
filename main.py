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

# Инициализация клиентов
client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# Хранилище состояний пользователей
user_states = {}  # user_id -> {"scene": "ep1_intro", "step": 0}

def get_user_state(user_id):
    return user_states.setdefault(user_id, {"scene": "ep1_intro", "step": 0})

def gpt_reply(step_characters, user_input):
    character_names = [c["name"] for c in step_characters]
    prompt = f"""
Ты один из следующих персонажей: {', '.join(character_names)}. Алекс — главная героиня, пользователь играет за неё и пишет от её имени.

Ответь очень коротко и естественно, как в реальной переписке. Отвечай только от одного из доступных персонажей (не от Алекс). Пример:

Имя: фраза

Не описывай действия. Не добавляй ничего лишнего. Только короткая реплика в живом стиле.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.7,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка GPT: {str(e)}"

def send_step_messages(user_id, chat_id):
    user_state = get_user_state(user_id)
    scene = story[user_state["scene"]]
    steps = scene["steps"]
    step_index = user_state["step"]

    if step_index >= len(steps):
        return  # конец сцены

    step = steps[step_index]
    characters = step.get("characters", [])
    text = step.get("text", "")

    if text:
        bot.send_message(chat_id=chat_id, text=text)
        time.sleep(10)

    for line in characters:
        time.sleep(10)
        bot.send_message(chat_id=chat_id, text=f'{line["name"]}: {line["line"]}')

    user_state["step"] += 1

def continue_story(chat_id, user_id):
    threading.Thread(target=send_step_messages, args=(user_id, chat_id)).start()

def start(update, context):
    user_id = update.message.chat_id
    user_states[user_id] = {"scene": "ep1_intro", "step": 0}
    intro_text = story["ep1_intro"]["steps"][0]["text"]
    update.message.reply_text(intro_text)
    continue_story(update.message.chat_id, user_id)

def handle_message(update, context):
    user_id = update.message.chat_id
    user_input = update.message.text.strip()
    user_state = get_user_state(user_id)
    scene = story[user_state["scene"]]
    steps = scene["steps"]

    if user_state["step"] < len(steps):
        step = steps[user_state["step"]]
        characters = step.get("characters", [])
        reply = gpt_reply(characters, user_input)
        update.message.reply_text(reply)

    continue_story(update.message.chat_id, user_id)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
