import os
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
import openai
from story import story

load_dotenv()

# Ключи из .env или Render Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Flask и Telegram setup
bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot, None, use_context=True)

# Состояния пользователей
user_states = {}

def get_scene(user_id):
    return user_states.get(user_id, "ep1_intro")

def gpt_reply(characters, goals, scene_text, user_input):
    goals_text = "\n".join([f"{char}: {goal}" for char, goal in goals.items()])
    system_prompt = f"""
Ты — один из персонажей интерактивной хоррор-истории. Алекс — главная героиня. Пользователь управляет её действиями.

Сцена: {scene_text}

Вот цели персонажей:
{goals_text}

Ты должен ответить от имени одного из персонажей, в формате:
Имя: сообщение
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.8,
            max_tokens=200
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        print("GPT ERROR:", e)
        return f"Ошибка GPT: {str(e)}"
        
def start(update, context):
    user_id = update.message.chat_id
    user_states[user_id] = "ep1_intro"
    scene = story["ep1_intro"]
    update.message.reply_text(scene["text"])

def handle_message(update, context):
    user_id = update.message.chat_id
    user_input = update.message.text.strip()
    scene_id = get_scene(user_id)
    scene = story.get(scene_id)

    if not scene:
        update.message.reply_text("Произошла ошибка.")
        return

    characters = scene.get("characters", [])
    goals = scene.get("goals", {})

    # DEBUG: выведем данные пользователю
    update.message.reply_text(f"[DEBUG] Сцена: {scene_id}")
    update.message.reply_text(f"[DEBUG] Персонажи: {characters}")
    update.message.reply_text(f"[DEBUG] Цели: {list(goals.keys())}")

    reply = gpt_reply(characters, goals, scene["text"], user_input)
    update.message.reply_text(reply)

# Обработчики команд
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# Webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

# Локальный запуск (если не на Render)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
