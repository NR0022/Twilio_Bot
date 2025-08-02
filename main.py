import telebot
import threading

from telebot import types
from twilio.rest import Client
from flask import Flask, request
import re
import datetime

bot = telebot.TeleBot("8346024115:AAEwWO4W0BDLxn66JcePSOIBUOJMBIyRe9I")

GROUP_ID = -1001234567890  # <- আপনার গ্রুপ আইডি
user_data = {}
twilio_clients = {}
app = Flask(__name__)

def show_main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📞 Buy Number"),
        types.KeyboardButton("🔍 Search Number"),
        types.KeyboardButton("👁 View SMS"),
        types.KeyboardButton("🚪 Logout"),
        types.KeyboardButton("🆘 Help"),
    )
    bot.send_message(chat_id, "Main Menu:", reply_markup=markup)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔑 Login"))
    bot.send_message(message.chat.id, "👋 Twilio Bot এ স্বাগতম!\nLogin করতে 🔑 Login চাপুন।", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text == "🔑 Login")
def ask_credentials(message):
    bot.send_message(message.chat.id, "🧾 SID ও TOKEN দিন:\nযেমন:\n`ACxxxx... xxxx...`", parse_mode='Markdown')

@bot.message_handler(func=lambda m: len(m.text.split()) == 2 and m.text.startswith("AC"))
def handle_login(message):
    sid, token = message.text.split()
    try:
        client = Client(sid, token)
        client.api.accounts(sid).fetch()
        user_data[message.chat.id] = {"sid": sid, "token": token, "number": None}
        twilio_clients[message.chat.id] = client
        bot.send_message(message.chat.id, "✅ Login Successful!")
        show_main_menu(message.chat.id)
    except:
        bot.send_message(message.chat.id, "❌ ভুল SID বা TOKEN!")

@bot.message_handler(func=lambda msg: msg.text == "📞 Buy Number")
def ask_area_code(message):
    bot.send_message(message.chat.id, "🔢 আপনার পছন্দের Area Code লিখুন (Canada Code Only):")

@bot.message_handler(func=lambda msg: msg.text.isdigit() and len(msg.text) == 3)
def search_number(message):
    area = message.text
    try:
        client = twilio_clients[message.chat.id]
        numbers = client.available_phone_numbers('CA').local.list(area_code=area, limit=15)
        if not numbers:
            bot.send_message(message.chat.id, "❌ কোনো নাম্বার পাওয়া যায়নি।")
            return

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for num in numbers:
            markup.add(types.KeyboardButton(num.phone_number))
        bot.send_message(message.chat.id, "📋 নাম্বার বেছে নিন:", reply_markup=markup)
        user_data[message.chat.id]["available"] = [n.phone_number for n in numbers]
    except:
        bot.send_message(message.chat.id, "❌ নাম্বার খুঁজতে সমস্যা হচ্ছে।")

@bot.message_handler(func=lambda msg: msg.text.startswith("+1"))
def handle_selected_number(message):
    number = message.text.strip()
    user_data[message.chat.id]["pending_number"] = number
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("✅ Confirm Buy"))
    bot.send_message(message.chat.id, f"📱 বেছে নিয়েছেন: {number}", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text == "✅ Confirm Buy")
def confirm_buy(message):
    data = user_data.get(message.chat.id)
    if not data or "pending_number" not in data:
        bot.send_message(message.chat.id, "❌ কোনো নাম্বার নির্বাচিত নেই।")
        return
    client = twilio_clients[message.chat.id]
    number = data["pending_number"]

    if data.get("number_sid"):
        try:
            client.incoming_phone_numbers(data["number_sid"]).delete()
        except:
            pass

    try:
        new_num = client.incoming_phone_numbers.create(
            phone_number=number,
            sms_url="https://mkiu76fgv.pythonanywhere.com/sms"
        )
        data["number"] = number
        data["number_sid"] = new_num.sid
        bot.send_message(message.chat.id, f"✅ কেনা হয়েছে: {number}")
        show_main_menu(message.chat.id)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ নাম্বার কেনা যায়নি:\n{e}")

@bot.message_handler(func=lambda msg: msg.text == "👁 View SMS")
def view_sms(message):
    data = user_data.get(message.chat.id)
    if not data or not data.get("number"):
        bot.send_message(message.chat.id, "❌ কোনো কেনা নাম্বার নেই।")
        return
    bot.send_message(message.chat.id, f"📲 SMS Forward হবে\nNumber: {data['number']}")

@bot.message_handler(func=lambda msg: msg.text == "🆘 Help")
def help_text(message):
    bot.send_message(message.chat.id,
        "ℹ️ Help:\n"
        "🔑 Login: Twilio SID & Token দিন\n"
        "📞 Buy Number: Area Code দিন (Canada)\n"
        "👁 View SMS: আপনার SMS দেখতে পারবেন\n"
        "🚪 Logout: সেশন ক্লিয়ার করুন\n"
        "📩 SMS: গ্রুপে ও বটেই ফরওয়ার্ড হবে")

@bot.message_handler(func=lambda msg: msg.text == "🚪 Logout")
def logout(message):
    user_data.pop(message.chat.id, None)
    twilio_clients.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "✅ Logout Successful", reply_markup=types.ReplyKeyboardRemove())

# ----------------------- Flask Webhook -----------------------

@app.route("/sms", methods=["POST"])
def sms_webhook():
    from_num = request.form.get("From")
    body = request.form.get("Body", "")
    time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    otp_match = re.search(r"\b\d{3}[- ]?\d{3}\b", body)
    otp = otp_match.group().replace("-", "") if otp_match else "N/A"

    msg = (
        f"🕰️ Time: {time}\n"
        f"📞 Number: {from_num}\n"
        f"🌍 Country: 🇨🇦\n"
        f"🔑 Your Main OTP: {otp}\n"
        f"🍏 Service: twilio\n"
        f"📬 Full Message:\n{body}\n\n"
        f"👑 Powered by: Nirob"
    )

    try:
        bot.send_message(GROUP_ID, msg)
        for uid, data in user_data.items():
            if data.get("number") == from_num:
                bot.send_message(uid, msg)
    except:
        pass

    return '', 200

# ------------------------ Bot Start (Only when testing locally) ------------------------

# DO NOT USE IN PYTHONANYWHERE
# if __name__ == "__main__":
#     bot.infinity_polling()
#     app.run(host="0.0.0.0", port=5000)


def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=5000)

