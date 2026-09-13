import telebot, json, os, zipfile, time, threading, shutil, sqlite3, re
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, timedelta
from flask import Flask, request
import fitz # PyMuPDF

TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID'))
ADMIN_BOT_TOKEN = os.environ.get('ADMIN_BOT_TOKEN')

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

DB_FILE = 'fawateery.db'
BACKUP_FOLDER = 'backups'
OWNER_NAME = 'جمال عبد الناصر ناصر طالب'
OWNER_PHONE = '772765410'
PRICE_PER_DEVICE = 20000

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS restaurants (
        code TEXT PRIMARY KEY, name TEXT NOT NULL, owner_id TEXT, owner_phone TEXT,
        devices_count INTEGER DEFAULT 1, status TEXT DEFAULT 'inactive', expiry TEXT,
        created TEXT, notified_5days INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS devices (
        device_code TEXT PRIMARY KEY, parent_code TEXT, name TEXT, bot_token TEXT,
        owner_id TEXT, owner_phone TEXT, status TEXT DEFAULT 'inactive', expiry TEXT,
        last_heartbeat TEXT, FOREIGN KEY(parent_code) REFERENCES restaurants(code))''')
    c.execute('''CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_code TEXT, device_code TEXT, invoice_number TEXT,
        amount REAL, invoice_date TEXT, file_path TEXT,
        FOREIGN KEY(parent_code) REFERENCES restaurants(code))''')
    conn.commit()
    conn.close()

def backup_db():
    if not os.path.exists(BACKUP_FOLDER): os.mkdir(BACKUP_FOLDER)
    if os.path.exists(DB_FILE):
        backup_name = f'{BACKUP_FOLDER}/fawateery_{datetime.now().strftime("%Y%m%d_%H%M")}.db'
        shutil.copy(DB_FILE, backup_name)

def extract_invoice_amount(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc: text += page.get_text()
        doc.close()
        patterns = [
            r'الإجمالي[:\s]*([0-9,]+\.?[0-9]*)',
            r'المجموع[:\s]*([0-9,]+\.?[0-9]*)',
            r'الإجمالى[:\s]*([0-9,]+\.?[0-9]*)',
            r'Total[:\s]*([0-9,]+\.?[0-9]*)',
            r'Amount[:\s]*([0-9,]+\.?[0-9]*)',
            r'المبلغ[:\s]*([0-9,]+\.?[0-9]*)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                return float(amount_str)
        return 0.0
    except: return 0.0

def save_invoice(parent_code, device_code, pdf_path):
    amount = extract_invoice_amount(pdf_path)
    if amount == 0: return 0
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    invoice_num = os.path.basename(pdf_path)
    c.execute('''INSERT INTO invoices (parent_code, device_code, invoice_number, amount, invoice_date, file_path)
                 VALUES (?,?,?,?,?,?)''', (parent_code, device_code, invoice_num, amount, now, pdf_path))
    conn.commit()
    conn.close()
    return amount

def get_daily_total(parent_code, date_str):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''SELECT SUM(amount) FROM invoices WHERE parent_code=? AND DATE(invoice_date)=?''', (parent_code, date_str))
    total = c.fetchone()[0]
    conn.close()
    return total if total else 0.0

def get_monthly_total(parent_code, year_month):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''SELECT SUM(amount) FROM invoices WHERE parent_code=? AND strftime('%Y-%m', invoice_date)=?''', (parent_code, year_month))
    total = c.fetchone()[0]
    conn.close()
    return total if total else 0.0

def send_daily_reports():
    today = datetime.now().strftime('%Y-%m-%d')
    restaurants = get_all_restaurants()
    for code, rest in restaurants.items():
        if rest['status'] == 'active':
            total = get_daily_total(code, today)
            if total > 0:
                msg = f'''📊 *التقرير اليومي* 📊\n\nمطعم: {rest['name']}\nالتاريخ: {today}\nالمبيعات: {total:,.2f} ريال\n\n✅ تم الإرسال تلقائياً الساعة 12:00'''
                try: bot.send_message(int(rest['owner_id']), msg, parse_mode='Markdown')
                except: pass
                try: bot.send_message(ADMIN_ID, f"📊 {rest['name']}: {total:,.2f} ريال", parse_mode='Markdown')
                except: pass

def send_monthly_reports():
    last_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
    restaurants = get_all_restaurants()
    for code, rest in restaurants.items():
        if rest['status'] == 'active':
            total = get_monthly_total(code, last_month)
            if total > 0:
                msg = f'''📊 *التقرير الشهري* 📊\n\nمطعم: {rest['name']}\nالشهر: {last_month}\nإجمالي المبيعات: {total:,.2f} ريال\n\n✅ تم الإرسال تلقائياً'''
                try: bot.send_message(int(rest['owner_id']), msg, parse_mode='Markdown')
                except: pass
                try: bot.send_message(ADMIN_ID, f"📊 {rest['name']} - {last_month}: {total:,.2f} ريال", parse_mode='Markdown')
                except: pass

def get_restaurant(code):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('SELECT * FROM restaurants WHERE code=?', (code,))
    row = c.fetchone()
    conn.close()
    if row: return {'code': row[0], 'name': row[1], 'owner_id': row[2], 'owner_phone': row[3], 'devices_count': row[4], 'status': row[5], 'expiry': row[6], 'created': row[7], 'notified_5days': row[8]}
    return None

def get_all_restaurants():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('SELECT * FROM restaurants')
    rows = c.fetchall()
    conn.close()
    result = {}
    for row in rows: result[row[0]] = {'code': row[0], 'name': row[1], 'owner_id': row[2], 'owner_phone': row[3], 'devices_count': row[4], 'status': row[5], 'expiry': row[6], 'created': row[7], 'notified_5days': row[8]}
    return result

def save_restaurant(data):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO restaurants VALUES (?,?,?,?,?,?,?,?,?)''', (data['code'], data['name'], data['owner_id'], data['owner_phone'], data['devices_count'], data['status'], data['expiry'], data['created'], data.get('notified_5days', 0)))
    conn.commit()
    conn.close()
    backup_db()

def save_device(data):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO devices VALUES (?,?,?,?,?,?,?,?,?)''', (data['device_code'], data['parent_code'], data['name'], data['bot_token'], data['owner_id'], data['owner_phone'], data['status'], data['expiry'], data.get('last_heartbeat', '')))
    conn.commit()
    conn.close()

def update_heartbeat(parent_code, device_name):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''UPDATE devices SET last_heartbeat=? WHERE parent_code=? AND name LIKE?''', (now, parent_code, f'%{device_name}%'))
    conn.commit()
    conn.close()

def is_active(code):
    rest = get_restaurant(code)
    if not rest: return False
    try:
        expiry = datetime.strptime(rest['expiry'], '%Y-%m-%d')
        return rest['status'] == 'active' and datetime.now() < expiry
    except: return False

def check_expiry_notifications():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('SELECT * FROM restaurants WHERE status="active"')
    rows = c.fetchall()
    for row in rows:
        code = row[0]
        try:
            expiry = datetime.strptime(row[6], '%Y-%m-%d')
            days_left = (expiry - datetime.now()).days
            if days_left == 5 and row[8] == 0:
                devices = row[4]
                total = PRICE_PER_DEVICE * devices
                msg = f'''⚠️ *تنبيه انتهاء اشتراك* ⚠️\n\nمطعم: {row[1]}\nالكود: `{code}`\nالأجهزة: {devices}\nمتبقي: 5 أيام\nينتهي: {row[6]}\n\n💰 التجديد: {total:,} ريال\n📱 {row[3]}\n\n🔴 *القرار بيدك - لن يتوقف تلقائياً*'''
                bot.send_message(ADMIN_ID, msg, parse_mode='Markdown')
                c.execute('UPDATE restaurants SET notified_5days=1 WHERE code=?', (code,))
                conn.commit()
        except Exception as e: print(f"Error: {e}")
    conn.close()

def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton('➕ مطعم جديد'), KeyboardButton('🖥️ جهاز جديد'))
    markup.row(KeyboardButton('💰 تفعيل'), KeyboardButton('⛔ إيقاف'))
    markup.row(KeyboardButton('📋 كل المطاعم'), KeyboardButton('⚠️ قربت تنتهي'))
    markup.row(KeyboardButton('🖥️ حالة الأجهزة'), KeyboardButton('📊 الأرباح'))
    markup.row(KeyboardButton('📈 تقرير اليوم'), KeyboardButton('📅 تقرير الشهر'))
    return markup

@bot.message_handler(commands=['start', 'heartbeat'])
def start(message):
    if message.text.startswith('/heartbeat'):
        try:
            _, code, device = message.text.split('|')
            update_heartbeat(code, device)
            return
        except: return
    if message.from_user.id!= ADMIN_ID:
        text = f'''🔥 *نظام فواتيري V7.3 SQLite* 🔥\n\nاشتراك: {PRICE_PER_DEVICE:,} ريال/جهاز/شهر\n\n✅ تقارير يومية/شهرية تلقائية\n✅ لحظي عبر تلغرام\n✅ صفر مجهود على الكاشير\n\n👨‍💼 {OWNER_NAME}\n📞 {OWNER_PHONE}'''
        bot.send_message(message.chat.id, text, parse_mode='Markdown')
        return
    check_expiry_notifications()
    restaurants = get_all_restaurants()
    active_devices = sum(r['devices_count'] for r in restaurants.values() if r['status'] == 'active')
    text = f'''أهلاً يا جمال 👋\n*لوحة تحكم V7.3 SQLite*\n\n💰 السعر: {PRICE_PER_DEVICE:,} ريال/جهاز\n🖥️ أجهزة شغالة: {active_devices}\n⚡ SQLite + تقارير تلقائية\n🔒 إيقاف يدوي فقط'''
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == '📈 تقرير اليوم')
def today_report(message):
    if message.from_user.id!= ADMIN_ID: return
    today = datetime.now().strftime('%Y-%m-%d')
    restaurants = get_all_restaurants()
    text = f'📈 *تقرير اليوم {today}*\n\n'
    grand_total = 0
    for code, rest in restaurants.items():
        if rest['status'] == 'active':
            total = get_daily_total(code, today)
            if total > 0:
                text += f'*{rest["name"]}*: {total:,.2f} ريال\n'
                grand_total += total
    text += f'\n💰 *الإجمالي*: {grand_total:,.2f} ريال'
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '📅 تقرير الشهر')
def month_report(message):
    if message.from_user.id!= ADMIN_ID: return
    month = datetime.now().strftime('%Y-%m')
    restaurants = get_all_restaurants()
    text = f'📅 *تقرير شهر {month}*\n\n'
    grand_total = 0
    for code, rest in restaurants.items():
        if rest['status'] == 'active':
            total = get_monthly_total(code, month)
            if total > 0:
                text += f'*{rest["name"]}*: {total:,.2f} ريال\n'
                grand_total += total
    text += f'\n💰 *الإجمالي*: {grand_total:,.2f} ريال'
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '➕ مطعم جديد')
def new_restaurant_step1(message):
    if message.from_user.id!= ADMIN_ID: return
    text = f"""🔧 *إضافة مطعم جديد* 🔧\n\nأرسل: اسم | أيدي المالك | جوال | عدد الأجهزة\n\nمثال:\nمطعم السلام|1234567890|772123456|3\n\n💰 {PRICE_PER_DEVICE:,} ريال/جهاز/شهر"""
    msg = bot.send_message(message.chat.id, text, parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_new_restaurant)

def process_new_restaurant(message):
    try:
        name, owner_id, owner_phone, devices = message.text.split('|')
        devices = int(devices)
        base_code = name.replace(' ', '_').upper()[:8]
        data = {'code': base_code, 'name': name.strip(), 'owner_id': owner_id.strip(), 'owner_phone': owner_phone.strip(), 'devices_count': devices, 'status': 'inactive', 'expiry': '2020-01-01', 'created': datetime.now().strftime('%Y-%m-%d'), 'notified_5days': 0}
        save_restaurant(data)
        bot.send_message(message.chat.id, f'✅ تم إضافة {name}\nالكود: `{base_code}`\nالأجهزة: {devices}\n\nاستخدم "🖥️ جهاز جديد" الآن', parse_mode='Markdown')
    except Exception as e: bot.send_message(message.chat.id, f'❌ خطأ: {str(e)}')

@bot.message_handler(func=lambda m: m.text == '🖥️ جهاز جديد')
def add_device_step1(message):
    if message.from_user.id!= ADMIN_ID: return
    msg = bot.send_message(message.chat.id, 'أرسل: كود المطعم | رقم الجهاز | توكن البوت\nمثال: SALAM|1|123456:AAAbcd')
    bot.register_next_step_handler(msg, process_add_device)

def process_add_device(message):
    try:
        code, device_num, bot_token = message.text.split('|')
        parent = get_restaurant(code)
        if not parent:
            bot.send_message(message.chat.id, '❌ كود المطعم غير موجود')
            return
        device_code = f"{code}_D{device_num}"
        device_data = {'device_code': device_code, 'parent_code': code, 'name': f"{parent['name']} - جهاز {device_num}", 'bot_token': bot_token.strip(), 'owner_id': parent['owner_id'], 'owner_phone': parent['owner_phone'], 'status': 'inactive', 'expiry': '2020-01-01', 'last_heartbeat': ''}
        save_device(device_data)
        bat_content = f'''@echo off
setlocal enabledelayedexpansion
title Fawateery-{device_code}
set "TGID={parent['owner_id']}"
set "TOKEN={bot_token.strip()}"
set "RESTNAME={parent['name']}"
set "DEVICENAME=جهاز {device_num}"
set "WATCHFOLDER=\\\\SERVER\\Fawatery\\{device_code}"
set "OFFLINEFOLDER=C:\\Fawatery_Offline\\{device_code}"
set "LOGFILE=C:\\Fawatery_Offline\\hunter_log.txt"
if not exist "%OFFLINEFOLDER%" mkdir "%OFFLINEFOLDER%"
if not exist "%WATCHFOLDER%\\sent" mkdir "%WATCHFOLDER%\\sent" 2>nul
echo ✅ %RESTNAME% - %DEVICENAME% ^| صياد النت شغال...
echo [%date% %time%] بدء التشغيل >> "%LOGFILE%"
:main_loop
curl -s "https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage?chat_id={ADMIN_ID}&text=/heartbeat|{code}|%COMPUTERNAME%" >nul
ping -n 1 8.8.8.8 >nul 2>&1
if!errorlevel! neq 0 (
    echo [%date% %time%] لا يوجد نت - انتظار 10 ثواني >> "%LOGFILE%"
    timeout /t 10 /nobreak >nul
    goto main_loop
)
for %%f in ("%OFFLINEFOLDER%\\*.pdf") do (
    call :send_telegram "%%f" "🔔 فاتورة مؤجلة - %DEVICENAME%"
    if!errorlevel! equ 0 (
        del "%%f"
        echo [%date% %time%] أُرسلت: %%~nxf >> "%LOGFILE%"
    ) else ( goto wait_cycle )
)
for %%f in ("%WATCHFOLDER%\\*.pdf") do (
    if not exist "%WATCHFOLDER%\\sent\\%%~nxf" (
        call :send_telegram "%%f" "🔔 فاتورة جديدة - %DEVICENAME%"
        if!errorlevel! equ 0 ( move "%%f" "%WATCHFOLDER%\\sent\\" >nul ) else (
            move "%%f" "%OFFLINEFOLDER%\\" >nul
            echo [%date% %time%] حُفظت أوفلاين: %%~nxf >> "%LOGFILE%"
        )
    )
)
:wait_cycle
timeout /t 3 /nobreak >nul
goto main_loop
:send_telegram
set "FILE=%~1"
set "CAPTION=%~2"
curl -s -m 10 -X POST "https://api.telegram.org/bot%TOKEN%/sendDocument" -F chat_id=%TGID% -F document=@"%FILE%" -F caption="%CAPTION% | %RESTNAME% ^\n\n📱 للدعم: {OWNER_NAME} - {OWNER_PHONE}" >nul 2>&1
exit /b!errorlevel!
'''
        instructions = f'''تعليمات V7.3 SQLite - {device_data['name']}\nالسعر: {PRICE_PER_DEVICE:,} ريال/جهاز/شهر\n\n🎯 صفر مجهود على الكاشير ✅\n\nالتركيب:\n1. السيرفر: C:\\Fawatery\\{device_code} + مشاركة Everyone\n2. الكاشير: طابعة PDF → \\\\SERVER\\Fawatery\\{device_code}\n3. شغل start.bat في السيرفر + Startup\n\n⚡ النت شغال: لحظي 1-3 ثواني\n📦 النت مقطوع: يحفظ أوفلاين ويرسل لاحقاً\n🔒 SQLite + تقارير تلقائية\n\nللدعم: {OWNER_NAME} - {OWNER_PHONE}\n'''
        filename = f'{device_code}_V7_SQLITE.zip'
        with zipfile.ZipFile(filename, 'w') as z:
            z.writestr('start.bat', bat_content)
            z.writestr('تعليمات.txt', instructions)
        with open(filename, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f'✅ {device_data["name"]}\n💰 {PRICE_PER_DEVICE:,} ريال/شهر\n⚡ SQLite + تقارير')
        os.remove(filename)
    except Exception as e: bot.send_message(message.chat.id, f'❌ خطأ: {str(e)}')

@bot.message_handler(func=lambda m: m.text == '💰 تفعيل')
def activate_step1(message):
    if message.from_user.id!= ADMIN_ID: return
    msg = bot.send_message(message.chat.id, 'أرسل: كود المطعم | عدد الشهور\nمثال: SALAM|3')
    bot.register_next_step_handler(msg, process_activate)

def process_activate(message):
    try:
        code, months = message.text.split('|')
        months = int(months)
        rest = get_restaurant(code)
        if not rest:
            bot.send_message(message.chat.id, '❌ الكود غير موجود')
            return
        current_expiry = datetime.strptime(rest['expiry'], '%Y-%m-%d')
        start_date = datetime.now() if datetime.now() > current_expiry else current_expiry
        new_expiry = start_date + timedelta(days=months*30)
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute('UPDATE restaurants SET status="active", expiry=?, notified_5days=0 WHERE code=?', (new_expiry.strftime('%Y-%m-%d'), code))
        c.execute('UPDATE devices SET status="active", expiry=? WHERE parent_code=?', (new_expiry.strftime('%Y-%m-%d'), code))
        conn.commit()
        conn.close()
        backup_db()
        devices = rest['devices_count']
        total = PRICE_PER_DEVICE * devices * months
        msg = f'''🎉 *تم التفعيل* 🎉\n\nمطعم: {rest["name"]}\nالأجهزة: {devices}\nالمدة: {months} شهر\nالمبلغ: {total:,} ريال\nينتهي: {new_expiry.strftime('%Y-%m-%d')}\n\n✅ كل الأجهزة شغالة'''
        bot.send_message(message.chat.id, msg, parse_mode='Markdown')
        try: bot.send_message(int(rest['owner_id']), msg, parse_mode='Markdown')
        except: pass
    except: bot.send_message(message.chat.id, '❌ خطأ. الصيغة: SALAM|3')

@bot.message_handler(func=lambda m: m.text == '⛔ إيقاف')
def stop_step1(message):
    if message.from_user.id!= ADMIN_ID: return
    msg = bot.send_message(message.chat.id, 'أرسل كود المطعم للإيقاف')
    bot.register_next_step_handler(msg, process_stop)

def process_stop(message):
    code = message.text.strip()
    rest = get_restaurant(code)
    if rest:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute('UPDATE restaurants SET status="inactive" WHERE code=?', (code,))
        c.execute('UPDATE devices SET status="inactive" WHERE parent_code=?', (code,))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f'⛔ تم إيقاف {rest["name"]} وكل أجهزته')
    else: bot.send_message(message.chat.id, '❌ الكود غير موجود')

@bot.message_handler(func=lambda m: m.text == '⚠️ قربت تنتهي')
def expiring_soon(message):
    if message.from_user.id!= ADMIN_ID: return
    restaurants = get_all_restaurants()
    text = '⚠️ *تنتهي خلال 7 أيام:*\n\n'
    found = False
    for code, info in restaurants.items():
        if info['status'] == 'active':
            expiry = datetime.strptime(info['expiry'], '%Y-%m-%d')
            days_left = (expiry - datetime.now()).days
            if 0 < days_left <= 7:
                devices = info['devices_count']
                total = PRICE_PER_DEVICE * devices
                text += f'🔴 *{info["name"]}*\n'
                text += f' الكود: `{code}` | متبقي: {days_left} أيام\n'
                text += f' الأجهزة: {devices} = {total:,} ريال\n'
                text += f' جوال: {info["owner_phone"]}\n\n'
                found = True
    if not found: text = '✅ كل الاشتراكات تمام'
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '🖥️ حالة الأجهزة')
def devices_status(message):
    if message.from_user.id!= ADMIN_ID: return
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''SELECT r.name, d.name, d.last_heartbeat FROM restaurants r JOIN devices d ON r.code = d.parent_code WHERE r.status="active"''')
    rows = c.fetchall()
    conn.close()
    text = '🖥️ *حالة أجهزة المطاعم*\n\n'
    current_rest = ''
    for rest_name, dev_name, last_seen in rows:
        if rest_name!= current_rest:
            text += f'*{rest_name}*\n'
            current_rest = rest_name
        if last_seen:
            try:
                last_time = datetime.strptime(last_seen, '%Y-%m-%d %H:%M:%S')
                diff = (datetime.now() - last_time).total_seconds() / 60
                status = '🟢 شغال' if diff < 10 else '🔴 طافي'
                text += f'{status} | {dev_name} | {last_seen}\n'
            except: text += f'⚠️ | {dev_name} | خطأ\n'
        else: text += f'❌ | {dev_name} | لم يتصل\n'
        text += '\n'
    if not rows: text = '❌ لا يوجد أجهزة شغالة'
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '📋 كل المطاعم')
def list_restaurants(message):
    if message.from_user.id!= ADMIN_ID: return
    restaurants = get_all_restaurants()
    if not restaurants:
        bot.send_message(message.chat.id, 'لا يوجد مطاعم')
        return
    text = f'📋 *كل المطاعم:*\n💰 {PRICE_PER_DEVICE:,} ريال/جهاز\n\n'
    for code, info in restaurants.items():
        status = '🟢 شغال' if is_active(code) else '🔴 متوقف'
        devices = info['devices_count']
        text += f'{status} `{code}` | {info["name"]}\n'
        text += f' 📱 {info["owner_phone"]} | 🖥️ {devices} | 📅 {info["expiry"]}\n\n'
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '📊 الأرباح')
def profit_report(message):
    if message.from_user.id!= ADMIN_ID: return
    restaurants = get_all_restaurants()
    active_devices = sum(r['devices_count'] for r in restaurants.values() if r['status'] == 'active')
    monthly = active_devices * PRICE_PER_DEVICE
    text = f'''📊 *الأرباح V7.3 SQLite* 📊\n\n🖥️ أجهزة شغالة: {active_devices}\n💰 شهري: {monthly:,} ريال\n💰 سنوي: {monthly*12:,} ريال\n\n📱 {OWNER_NAME}'''
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

def scheduler():
    last_day = None
    last_hour = None
    while True:
        time.sleep(60)
        try:
            check_expiry_notifications()
            now = datetime.now()
            if now.hour == 0 and now.minute == 0 and last_hour!= 0:
                send_daily_reports()
                if now.day == 1 and last_day!= now.day:
                    send_monthly_reports()
                    last_day = now.day
            last_hour = now.hour
        except Exception as e: print(f"Scheduler error: {e}")

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    if update.message and update.message.document:
        if update.message.document.file_name.endswith('.pdf'):
            file_info = bot.get_file(update.message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            save_path = f"invoice_{update.message.from_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            with open(save_path, 'wb') as f: f.write(downloaded_file)
            rest = None
            for r in get_all_restaurants().values():
                if r['owner_id'] == str(update.message.from_user.id):
                    rest = r
                    break
            if rest:
                amount = save_invoice(rest['code'], 'manual', save_path)
                if amount > 0:
                    bot.send_message(update.message.chat.id, f'✅ تم حفظ الفاتورة\nالمبلغ: {amount:,.2f} ريال')
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=os.environ.get('RENDER_EXTERNAL_URL') + '/' + TOKEN)
    return "Bot is running!", 200

if __name__ == "__main__":
    init_db()
    threading.Thread(target=scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))