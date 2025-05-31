import os
import time
import threading
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
from openai import OpenAI
from story import story

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# user_id -> {"scene": ..., "step": ..., "line": ..., "waiting": False}
user_states = {}

def get_user_state(user_id):
    return user_states.setdefault(user_id, {"scene": "ep1_intro", "step": 0, "line": 0, "waiting": False})

def gpt_reply(user_input, characters):
    names = ', '.join([c['name'] for c in characters])
    prompt = f"""
Ты — один из персонажей: {names}.
Пользователь играет за героиню Алекс.

Отвечай только от имени одного из доступных персонажей, коротко и по-человечески.
Не описывай действия, не добавляй ничего лишнего. Только реплика в виде:
Имя: фраза
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

def send_story(user_id, chat_id):
    user_state = get_user_state(user_id)
    scene = story[user_state["scene"]]
    steps = scene["steps"]

    while user_state["step"] < len(steps):
        step = steps[user_state["step"]]
        characters = step.get("characters", [])
        text = step.get("text", "")
        line_index = user_state["line"]

        if text and line_index == 0:
            bot.send_message(chat_id=chat_id, text=text)
            time.sleep(10)

        while line_index < len(characters):
            msg = characters[line_index]
            bot.send_message(chat_id=chat_id, text=f'{msg["name"]}: {msg["line"]}')
            line_index += 1
            user_state["line"] = line_index
            time.sleep(10)

        user_state["step"] += 1
        user_state["line"] = 0

def continue_story(user_id, chat_id):
    if not user_states[user_id]["waiting"]:
        user_states[user_id]["waiting"] = True

        def run():
            send_story(user_id, chat_id)
            user_states[user_id]["waiting"] = False

        threading.Thread(target=run).start()

def start(update, context):
    user_id = update.message.chat_id
    user_states[user_id] = {"scene": "ep1_intro", "step": 0, "line": 0, "waiting": False}
    update.message.reply_text("Вы едете по дороге к базе отдыха. Вдруг слышите какой-то звук от машины и останавливаетесь, вы оказываетесь у странного городка Эвансон.")
    continue_story(user_id, update.message.chat_id)

def handle_message(update, context):
    user_id = update.message.chat_id
    user_input = update.message.text.strip()
    state = get_user_state(user_id)

    current_step = story[state["scene"]]["steps"][state["step"]]
    characters = current_step.get("characters", [])
    reply = gpt_reply(user_input, characters)

    update.message.reply_text(reply)
    continue_story(user_id, update.message.chat_id)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

