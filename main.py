import os
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
import openai
from story import story

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot, None, use_context=True)

user_states = {}

def get_scene(user_id):
    return user_states.get(user_id, "ep1_intro")
def gpt_reply(characters, goals, scene_text, user_input):
    characters_list = ", ".join(characters)
    goals_text = "\n".join([f"{char}: {goal}" for char, goal in goals.items()])

    prompt = f"""
Ты — один из персонажей интерактивной хоррор-истории. Алекс — главная героиня, пользователь управляет её действиями.

Сцена: "{scene_text}"
Пользователь (Алекс) пишет: "{user_input}"

Цели:
{goals_text}

Ответь от имени одного из персонажей в формате:
Имя: сообщение
"""

    try:
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=prompt,
            max_tokens=200,
            temperature=0.8
        )
        return response.choices[0].text.strip()
    except Exception as e:
        print("GPT ERROR:", e)
        return "Ошибка GPT"



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
        update.message.reply_text(f"[DEBUG] scene: {scene_id}")
update.message.reply_text(f"[DEBUG] characters: {characters}")
update.message.reply_text(f"[DEBUG] goals: {goals}")


        return

    characters = scene.get("characters", [])
    goals = scene.get("goals", {})
    reply = gpt_reply(characters, goals, scene["text"], user_input)
    update.message.reply_text(reply)

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
