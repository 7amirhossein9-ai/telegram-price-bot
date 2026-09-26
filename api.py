from flask import Flask, jsonify
import requests
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

@app.route("/send")
def send():
    token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")

    message = "🤖 تست ربات با موفقیت انجام شد"

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    requests.post(url, data={
        "chat_id": chat_id,
        "text": message
    })

    return jsonify({"status": "sent"})
