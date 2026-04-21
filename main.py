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
    rows = []
    for b in bot_data['buttons']:
        rows.append([Button.url(b['text'], b['url'])])
    return rows if rows else None

def bold(text):
    if not text:
        return ""
    return f"<b>{text}</b>"

async def send_forward(group):
    try:
        link = bot_data['forward_link']
        parts = link.split('/')
        chat = parts[-2]
        msg_id = int(parts[-1])

        msg = await client.get_messages(chat, ids=msg_id)
        if msg:
            await client.forward_messages(group, msg)

        await client.send_message("me", f"✅ {group}")

    except Exception as e:
        await client.send_message("me", f"❌ {group}\n{e}")

async def send_custom(group):
    try:
        buttons = build_buttons()

        if bot_data['media_message_id']:
            msg = await client.get_messages("me", ids=bot_data['media_message_id'])
            if msg:
                caption = bot_data['caption'] or msg.message or ""
                caption = bold(caption)

                await client.send_file(
                    group,
                    msg.media,
                    caption=caption,
                    buttons=buttons,
                    parse_mode='html'
                )

        elif bot_data['caption']:
            caption = bold(bot_data['caption'])

            await client.send_message(
                group,
                caption,
                buttons=buttons,
                parse_mode='html'
            )

        await client.send_message("me", f"✅ {group}")

    except Exception as e:
        await client.send_message("me", f"❌ {group}\n{e}")

# ================= BROADCAST =================
async def broadcast_loop():
    global broadcast_task

    async with lock:
        while bot_data['is_active']:

            groups = list(set(bot_data['groups']))

            for g in groups:
                if not bot_data['is_active']:
                    break

                if bot_data['forward_link']:
                    await send_forward(g)
                else:
                    await send_custom(g)

                await asyncio.sleep(random.randint(150, 210))

            if bot_data['is_active']:
                await asyncio.sleep(1800)

    broadcast_task = None

# ================= COMMAND =================

@client.on(events.NewMessage(outgoing=True, pattern=r'^/on$'))
async def start(event):
    global broadcast_task

    if bot_data['is_active']:
        return await event.respond("Sudah ON")

    bot_data['is_active'] = True
    save_data(bot_data)

    if not broadcast_task or broadcast_task.done():
        broadcast_task = asyncio.create_task(broadcast_loop())

    await event.respond("ON")

@client.on(events.NewMessage(outgoing=True, pattern=r'^/off$'))
async def stop(event):
    bot_data['is_active'] = False
    save_data(bot_data)
    await event.respond("OFF")

@client.on(events.NewMessage(outgoing=True, pattern=r'^/status$'))
async def status(event):
    await event.respond(
        f"Status: {'ON' if bot_data['is_active'] else 'OFF'}\n"
        f"Grup: {len(bot_data['groups'])}\n"
        f"Mode: {'FORWARD' if bot_data['forward_link'] else 'CUSTOM'}"
    )

@client.on(events.NewMessage(outgoing=True, pattern=r'^/addgroup'))
async def addgroup(event):
    lines = event.raw_text.split('\n')[1:]

    added = []
    for g in lines:
        g = g.strip().lower()
        if g.startswith("@") and g not in bot_data['groups']:
            bot_data['groups'].append(g)
            added.append(g)

    save_data(bot_data)

    if added:
        await event.respond("✅ Ditambahkan:\n" + "\n".join(added))
    else:
        await event.respond("⚠️ Tidak ada grup baru")

@client.on(events.NewMessage(outgoing=True, pattern=r'^/delgroup'))
async def delgroup(event):
    parts = event.raw_text.split()
    if len(parts) < 2:
        return await event.respond("Format salah")

    g = parts[1].lower()

    if g in bot_data['groups']:
        bot_data['groups'].remove(g)

    save_data(bot_data)
    await event.respond("OK")

@client.on(events.NewMessage(outgoing=True, pattern=r'^/listgroup$'))
async def listgroup(event):
    await event.respond("\n".join(bot_data['groups']) or "Kosong")

@client.on(events.NewMessage(outgoing=True, pattern=r'^/setcaption$'))
async def setcaption(event):
    if not event.is_reply:
        return await event.respond("Reply pesan untuk ambil caption")

    msg = await event.get_reply_message()

    bot_data['caption'] = msg.message or ""
    bot_data['forward_link'] = None

    save_data(bot_data)
    await event.respond("Caption OK")

@client.on(events.NewMessage(outgoing=True, pattern=r'^/setmedia$'))
async def setmedia(event):
    if not event.is_reply:
        return await event.respond("Reply media")

    msg = await event.get_reply_message()

    bot_data['media_message_id'] = msg.id
    bot_data['caption'] = msg.message or ""
    bot_data['forward_link'] = None

    save_data(bot_data)
    await event.respond("Media OK")

@client.on(events.NewMessage(outgoing=True, pattern=r'^/setbutton'))
async def setbutton(event):
    raw = event.raw_text.replace("/setbutton", "").strip()
    buttons = []

    try:
        for b in raw.split("||"):
            t, u = b.split("|")
            buttons.append({"text": t.strip(), "url": u.strip()})
    except:
        return await event.respond("Format salah")

    bot_data['buttons'] = buttons
    save_data(bot_data)

    await event.respond("Button OK")

@client.on(events.NewMessage(outgoing=True, pattern=r'^/forward'))
async def forward(event):
    parts = event.raw_text.split()
    if len(parts) < 2:
        return await event.respond("Masukkan link")

    bot_data['forward_link'] = parts[1]
    bot_data['caption'] = ""
    bot_data['media_message_id'] = None
    bot_data['buttons'] = []

    save_data(bot_data)
    await event.respond("Forward ON")

# ================= RUN =================
async def main():
    global broadcast_task

    await client.start()
    logging.info("Bot Connected")

    if bot_data.get('is_active'):
        if not broadcast_task or broadcast_task.done():
            broadcast_task = asyncio.create_task(broadcast_loop())

    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
