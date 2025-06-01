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

# Состояния пользователей
user_states = {}  # user_id -> {"scene": "ep1_intro", "step": 0}
user_locks = {}  # user_id -> threading.Lock


def get_user_state(user_id):
    user_locks.setdefault(user_id, threading.Lock())
    return user_states.setdefault(user_id, {"scene": "ep1_intro", "step": 0})

def collect_context(scene, current_step):
    context_lines = []
    for i in range(current_step):
        step = scene["steps"][i]
        for line in step.get("characters", []):
            context_lines.append(f'{line["name"]}: {line["line"]}')
    return "\n".join(context_lines)

def gpt_reply(scene, current_step, user_input):
    step = scene["steps"][current_step]
    step_characters = step.get("characters", [])
    character_names = [c["name"] for c in step_characters]
    context_text = collect_context(scene, current_step)

    prompt = f"""
Ты — один из следующих персонажей: {', '.join(character_names)}.
Персонажей интерактивной хоррор-истории. Алекс — главная героиня, пользователь играет за неё и пишет от её имени.
Ты должен отвечать от имени других персонажей, как в живом мессенджере. Отвечай очень коротко и естественно, как в реальной переписке. Не описывай действия. Просто пиши, что бы мог сказать этот персонаж.

Контекст истории:
{context_text}

Не добавляй описаний, действий или комментариев. Только реплики в формате диалога. Не отвечай от лица Алекс. Пример:
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
    user_state = get_user_state(user_id)
    scene = story[user_state["scene"]]
    step_index = user_state["step"]

    if step_index >= len(scene["steps"]):
        return

    step = scene["steps"][step_index]

    if "text" in step:
        bot.send_message(chat_id=chat_id, text=step["text"])
        time.sleep(10)

    for line in step.get("characters", []):
        bot.send_message(chat_id=chat_id, text=f'{line["name"]}: {line["line"]}')
        time.sleep(10)

    user_state["step"] += 1  # <- обязательно увеличивать только здесь
    
def continue_story(chat_id, user_id):
    def run():
        with user_locks[user_id]:
            send_step_messages(user_id, chat_id)
    threading.Thread(target=run).start()

def start(update, context):
    user_id = update.message.chat_id
    user_states[user_id] = {"scene": "ep1_intro", "step": 0}
    continue_story(update.message.chat_id, user_id)

def handle_message(update, context):
    user_id = update.message.chat_id
    user_input = update.message.text.strip()
    user_state = get_user_state(user_id)
    scene = story[user_state["scene"]]
    step_index = user_state["step"]

    if step_index < len(scene["steps"]):
        reply = gpt_reply(scene, step_index, user_input)
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
