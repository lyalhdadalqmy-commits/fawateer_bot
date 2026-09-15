import json
import os
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== الاعدادات - يقرأ من Railway ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
# لو ما ضفتهم في Railway حط قيم افتراضية عشان ما يطفى
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "777000000")
SUBSCRIPTION_PRICE = os.environ.get("SUBSCRIPTION_PRICE", "20,000")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "جمال")

DATA_FILE = "restaurants.json"

# ========== تحميل البيانات ==========
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ========== الاوامر ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID:
        return
    await update.message.reply_text("بوت التحكم شغال ✅\n/add /stop /start_res /devices /alert /log")

async def add_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID:
        return
    try:
        owner_id = context.args[0]
        name = context.args[1]
        days = int(context.args[2]) if len(context.args) > 2 else 30

        data = load_data()
        expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

        data[name] = {
            "owner_id": owner_id,
            "expiry": expiry,
            "active": True,
            "devices": 1,
            "invoices_today": 0,
            "total_today": 0
        }
        save_data(data)

        config = {
            "restaurant_name": name,
            "owner_id": owner_id,
            "bot_token": BOT_TOKEN,
            "admin_phone": ADMIN_PHONE
        }

        with open(f"config_{name}.json", 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # نرسل لك انت تنبيه - لو ADMIN_PHONE رقم تليجرام
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"✅ تم اضافة مطعم جديد\n\n"
                     f"الاسم: {name}\n"
                     f"رقم المالك: {owner_id}\n"
                     f"مدة الاشتراك: {days} يوم\n"
                     f"قيمة الاشتراك: {SUBSCRIPTION_PRICE} ريال\n"
                     f"تاريخ الانتهاء: {expiry}"
            )
        except:
            pass

        # نرسل لصاحب المطعم
        await context.bot.send_message(
            chat_id=owner_id,
            text=f"🎉 مرحباً بك في ( جمال اتميشن ) 🎉\n\n"
                 f"تم تفعيل اشتراك مطعم: {name}\n"
                 f"مدة الاشتراك: {days} يوم\n"
                 f"قيمة الاشتراك الشهري: {SUBSCRIPTION_PRICE} ريال\n\n"
                 f"💳 طرق الدفع:\n"
                 f"1. حوالة عبر جوالي\n"
                 f"2. حوالة عبر الكريمي\n"
                 f"3. حوالة صافية\n\n"
                 f"الاسم: {ADMIN_NAME}\n"
                 f"الرقم: {ADMIN_PHONE}\n\n"
                 f"📄 من الآن ستصلك كل فواتير المطعم هنا تلقائياً\n"
                 f"📊 + تقرير يومي وشهري بالمجموع\n\n"
                 f"لاي استفسار تواصل معنا على نفس الرقم"
        )

        await update.message.reply_document(
            document=open(f"config_{name}.json", 'rb'),
            caption=f"تم اضافة {name} ✅\nالانتهاء: {expiry}\n\nركب الملف مع save_invoices.exe"
        )

    except Exception as e:
        await update.message.reply_text(f"خطأ: {e}\nالاستخدام: /add 967771234567 الشامي 30")

async def stop_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID:
        return
    name = context.args[0]
    data = load_data()
    if name in data:
        data[name]["active"] = False
        save_data(data)
        await update.message.reply_text(f"تم ايقاف {name} ❌")
    else:
        await update.message.reply_text("المطعم غير موجود")

async def start_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID:
        return
    name = context.args[0]
    data = load_data()
    if name in data:
        data[name]["active"] = True
        save_data(data)
        await update.message.reply_text(f"تم تشغيل {name} ✅")
    else:
        await update.message.reply_text("المطعم غير موجود")

async def devices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID:
        return
    name = context.args[0]
    count = int(context.args[1]) if len(context.args) > 1 else 1
    data = load_data()
    if name not in data:
        await update.message.reply_text("المطعم غير موجود")
        return

    config = {
        "restaurant_name": name,
        "owner_id": data[name]["owner_id"],
        "bot_token": BOT_TOKEN,
        "admin_phone": ADMIN_PHONE
    }

    for i in range(count):
        filename = f"config_{name}_جهاز{i+1}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        await update.message.reply_document(document=open(filename, 'rb'))

    await update.message.reply_text(f"تم توليد {count} ملف تركيب لـ {name} ✅")

async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID:
        return
    data = load_data()
    msg = "⚠️ مطاعم قرب ينتهي اشتراكها:\n\n"
    found = False
    for name, info in data.items():
        expiry = datetime.strptime(info["expiry"], "%Y-%m-%d")
        days_left = (expiry - datetime.now()).days
        if 0 <= days_left <= 3:
            found = True
            msg += f"{name} - باقي {days_left} ايام\n/stop {name}\n\n"

    if not found:
        msg = "كل المطاعم اشتراكها تمام ✅"
    await update.message.reply_text(msg)

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= ADMIN_ID:
        return
    name = context.args[0]
    data = load_data()
    if name in data:
        info = data[name]
        status = "شغال ✅" if info["active"] else "واقف ❌"
        await update.message.reply_text(
            f"📊 {name}\n"
            f"الحالة: {status}\n"
            f"الانتهاء: {info['expiry']}\n"
            f"فواتير اليوم: {info['invoices_today']}\n"
            f"مجموع اليوم: {info['total_today']} ريال"
        )
    else:
        await update.message.reply_text("المطعم غير موجود")

# ========== التشغيل ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_restaurant))
    app.add_handler(CommandHandler("stop", stop_restaurant))
    app.add_handler(CommandHandler("start_res", start_restaurant)) # غيرنا الاسم عشان ما يتعارض
    app.add_handler(CommandHandler("devices", devices))
    app.add_handler(CommandHandler("alert", alert))
    app.add_handler(CommandHandler("log", log))

    print("بوت التحكم شغال...")
    app.run_polling()

if __name__ == '__main__':
    main()
