import asyncio
import json
import os
import logging
import random
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from flask import Flask
import threading

# ================= LOG =================
logging.basicConfig(
    format='[%(levelname)5s/%(asctime)s] %(name)s: %(message)s',
    level=logging.INFO
)

# ================= ENV =================
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")

if not API_ID or not API_HASH or not SESSION_STRING:
    raise RuntimeError("ENV belum lengkap")

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# ================= DATA =================
DATA_FILE = 'bot_data.json'

def load_data():
    default = {
        "caption": "",
        "groups": [],
        "is_active": False,
        "media_message_id": None,
        "media_chat_id": None,
        "buttons": [],
        "forward_link": None
    }

    if not os.path.exists(DATA_FILE):
        return default

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

            if 'grup' in data:
                data['groups'] = data.pop('grup')
            if 'aktif' in data:
                data['is_active'] = data.pop('aktif')
            if 'media_id' in data:
                data['media_message_id'] = data.pop('media_id')

            for k in default:
                if k not in data:
                    data[k] = default[k]

            return data
    except:
        return default

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

bot_data = load_data()

# ================= STATE =================
broadcast_task = None
lock = asyncio.Lock()

# ================= FLASK =================
app = Flask(__name__)

@app.route('/')
def index():
    return "OK"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

threading.Thread(target=run_flask, daemon=True).start()

# ================= UTIL =================
def build_buttons():
    return [[Button.url(b['text'], b['url'])] for b in bot_data['buttons']] or None

def clean_group(g):
    g = g.strip().lower()
    g = g.replace("https://t.me/", "").replace("http://t.me/", "")
    if "/" in g:
        g = g.split("/")[0]
    if not g.startswith("@"):
        g = "@" + g
    return g

def parse_link(link):
    link = link.replace("https://t.me/", "").replace("http://t.me/", "")
    chat, msg_id = link.split("/")
    return chat, int(msg_id)

# ================= SEND =================
async def send_custom(group):
    try:
        buttons = build_buttons()

        msg = await client.get_messages(
            bot_data.get('media_chat_id', "me"),
            ids=bot_data['media_message_id']
        )

        if msg:
            await client.send_file(
                group,
                msg.media,
                caption=msg.message or "",
                formatting_entities=msg.entities,
                buttons=buttons
            )

        await client.send_message("me", f"✅ {group}")

    except Exception as e:
        await client.send_message("me", f"❌ {group}\n{e}")

# ================= LOOP =================
async def broadcast_loop():
    global broadcast_task

    async with lock:
        while bot_data['is_active']:

            for g in list(set(bot_data['groups'])):
                if not bot_data['is_active']:
                    break

                await send_custom(g)
                await asyncio.sleep(random.randint(150, 210))

            await asyncio.sleep(1800)

    broadcast_task = None

# ================= COMMAND =================

# 🔥 FIX: HAPUS outgoing=True + TAMBAH LOG

@client.on(events.NewMessage(pattern=r'^/on$'))
async def start(event):
    print("COMMAND:", event.raw_text)

    global broadcast_task

    if bot_data['is_active']:
        return await event.reply("Sudah ON")

    bot_data['is_active'] = True
    save_data(bot_data)

    if not broadcast_task or broadcast_task.done():
        broadcast_task = asyncio.create_task(broadcast_loop())

    await event.reply("ON")

@client.on(events.NewMessage(pattern=r'^/off$'))
async def stop(event):
    print("COMMAND:", event.raw_text)

    bot_data['is_active'] = False
    save_data(bot_data)
    await event.reply("OFF")

@client.on(events.NewMessage(pattern=r'^/status$'))
async def status(event):
    print("COMMAND:", event.raw_text)

    await event.reply(
        f"Status: {'ON' if bot_data['is_active'] else 'OFF'}\n"
        f"Grup: {len(bot_data['groups'])}"
    )

@client.on(events.NewMessage(pattern=r'^/addgroup'))
async def addgroup(event):
    print("COMMAND:", event.raw_text)

    lines = event.raw_text.split('\n')[1:]
    added = []

    for g in lines:
        g = clean_group(g)
        if g not in bot_data['groups']:
            bot_data['groups'].append(g)
            added.append(g)

    save_data(bot_data)

    await event.reply("Ditambahkan:\n" + "\n".join(added))

@client.on(events.NewMessage(pattern=r'^/setmedia$'))
async def setmedia(event):
    print("COMMAND:", event.raw_text)

    if not event.is_reply:
        return await event.reply("Reply media")

    msg = await event.get_reply_message()

    bot_data['media_message_id'] = msg.id
    bot_data['media_chat_id'] = msg.chat_id

    save_data(bot_data)
    await event.reply("Media OK")

# ================= RUN =================
async def main():
    global broadcast_task

    await client.start()
    logging.info("Bot Connected")

    if bot_data.get('is_active'):
        broadcast_task = asyncio.create_task(broadcast_loop())

    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
