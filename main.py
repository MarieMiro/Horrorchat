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

client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

user_states = {}  # user_id -> {"scene": ..., "step": ..., "line_index": ...}
user_locks = {}

def get_user_state(user_id):
    if user_id not in user_locks:
        user_locks[user_id] = threading.Lock()
    return user_states.setdefault(user_id, {
        "scene": "ep1_intro",
        "step": 0,
        "line_index": 0
    })

def collect_context(scene, step_index):
    context = []
    for i in range(step_index):
        step = scene["steps"][i]
        for line in step.get("characters", []):
            context.append(f'{line["name"]}: {line["line"]}')
    return "\n".join(context)

def gpt_reply(scene, step_index, user_input):
    step = scene["steps"][step_index]
    characters = step.get("characters", [])
    character_names = [c["name"] for c in characters]
    context_text = collect_context(scene, step_index)

    prompt = f"""
Ты — один из следующих персонажей: {', '.join(character_names)}.
Алекс — главная героиня. Пользователь играет за неё и пишет от её имени.

Контекст истории:
{context_text}

Ответь очень коротко и естественно от имени одного из этих персонажей. Не описывай действия. Не добавляй ничего лишнего. Не отвечай от имени Алекс. Формат:
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

def send_remaining_lines(user_id, chat_id):
    state = get_user_state(user_id)
    scene = story[state["scene"]]
    step_index = state["step"]
    line_index = state["line_index"]

    if step_index >= len(scene["steps"]):
        return

    step = scene["steps"][step_index]

    if "text" in step and line_index == 0:
        bot.send_message(chat_id=chat_id, text=step["text"])
        time.sleep(7)

    characters = step.get("characters", [])
    while line_index < len(characters):
        line = characters[line_index]
        bot.send_message(chat_id=chat_id, text=f'{line["name"]}: {line["line"]}')
        line_index += 1
        state["line_index"] = line_index
        time.sleep(7)

    # Переход к следующему шагу
    state["step"] += 1
    state["line_index"] = 0

def continue_story(user_id, chat_id):
    if user_id not in user_locks:
        user_locks[user_id] = threading.Lock()
    def run():
        with user_locks[user_id]:
            send_remaining_lines(user_id, chat_id)
    threading.Thread(target=run).start()

def start(update, context):
    user_id = update.message.chat_id
    user_states[user_id] = {"scene": "ep1_intro", "step": 0, "line_index": 0}
    continue_story(user_id=user_id, chat_id=update.message.chat_id)

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

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
