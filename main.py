import os
from telegram.ext import Updater, CommandHandler

BOT_TOKEN = os.environ.get("BOT_TOKEN")

def start(update, context):
    update.message.reply_text("البوت شغال يا جمال 🚀")

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    
    print("Bot is running...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
