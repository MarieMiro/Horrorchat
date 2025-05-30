import os
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

# Инициализация OpenAI-клиента
client = OpenAI(api_key=OPENAI_API_KEY)

# Инициализация Flask и Telegram
app = Flask(__name__)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# Состояния пользователей: user_id → {"scene": ..., "step": ...}
user_states = {}

def get_user_state(user_id):
    return user_states.get(user_id, {"scene": "ep1_intro", "step": 0})

def update_user_step(user_id):
    state = get_user_state(user_id)
    state["step"] += 1
    user_states[user_id] = state

# GPT-ответ от персонажей
def gpt_reply(characters, goals, scene_text, user_input):
    goals_text = "\n".join([f"{char}: {goal}" for char, goal in goals.items()])
    system_prompt = f"""
Ты — один из персонажей интерактивной хоррор-истории. Алекс — главная героиня, пользователь играет за неё и пишет от её имени.

Ты должен отвечать от имени других персонажей, как в живом мессенджере. Отвечай очень коротко и естественно, как в реальной переписке. Не описывай действия. Просто пиши, что бы мог сказать этот персонаж.

Контекст сцены:
{scene_text}

Цели персонажей:
{goals_text}

Ответь в формате 2–3 коротких реплик от других персонажей. Каждая реплика должна начинаться с имени говорящего, например:
Имя: фраза

Не добавляй описаний, действий или комментариев. Только реплики в формате диалога. Не отвечай от лица Алекс.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.8,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("GPT ERROR:", e)
        return f"Ошибка GPT: {str(e)}"

# Команда /start
def start(update, context):
    user_id = update.message.chat_id
    user_states[user_id] = {"scene": "ep1_intro", "step": 0}
    scene = story["ep1_intro"]
    intro_text = scene["steps"][0].get("text", "Начинаем...")
    update.message.reply_text(intro_text)

# Обработка сообщений
def handle_message(update, context):
    user_id = update.message.chat_id
    user_input = update.message.text.strip()

    state = get_user_state(user_id)
    scene_id = state["scene"]
    step_index = state["step"]
    scene = story.get(scene_id)

    if not scene or step_index >= len(scene["steps"]):
        update.message.reply_text("История завершена или произошла ошибка.")
        return

    step = scene["steps"][step_index]
    scene_text = step.get("text", "")
    characters = step.get("characters", [])
    goals = scene.get("goals", {})

    reply = gpt_reply(characters, goals, scene_text, user_input)

    # Отправляем каждую строку отдельно (имитация диалога)
    for line in reply.split('\n'):
        line = line.strip()
        if line:
            update.message.reply_text(line)

    # Переход к следующему шагу
    update_user_step(user_id)

# Webhook Telegram
@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

# Обработчики команд
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# Запуск на Render
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

