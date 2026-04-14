


import os
import csv
import io
import requests
from flask import Flask, render_template, request, Response, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


# -------------------------- اعداد قاعدة البيانات --------------------------
base_dir = os.path.abspath(os.path.dirname(__file__))

# Render ملاحظة: الرابط سيؤخذ من إعدادات بيئة 
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# اذا لم يكن موجودbase_dir.db ننشئ ملف قاعدة بيانات باسم
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///' + os.path.join(base_dir, 'energy.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)  # ربط قاعدة البيانات بالموقع

# انشاء و جلب رمز للتعامل مع قاعدة البيانات
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") 

# ------- تصميم جدول البيانات (الأعمدة التي سيتم حفظها) 
class EnergyRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # رقم تسلسلي لكل عملية
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # وقت التسجيل
    city = db.Column(db.String(100))            # اسم المنطقة/المدينة
    lat = db.Column(db.Float)                   # خط الطول للمنطقة
    lon = db.Column(db.Float)                   # خط عرض للمنطقة
    ac_status = db.Column(db.String(20))        # حالة المكيف (شغال/مطفأ)

    temp = db.Column(db.Float)                  # درجة الحرارة
    wind_speed = db.Column(db.Float)            # سرعة الرياح
    clouds = db.Column(db.Integer)              # نسبة الغيوم
    solar_radiation = db.Column(db.Float)       # الإشعاع الشمسي المحسوب
    solar_pred_amps = db.Column(db.Float)       # أمبير الطاقة الشمسية المتوقع
    wind_pred_amps = db.Column(db.Float)        # أمبير التوربين المتوقع
    total_pred_amps = db.Column(db.Float)       # المجموع الكلي للأمبير المتوقع

    solar_power_real = db.Column(db.Float)      # الطاقة الواقعية من اللوح الشمسي
    wind_power_real = db.Column(db.Float)       # الطاقة الواقعية من توربين الرياح
    total_power_real = db.Column(db.Float)      # الطاقة الاجمالية الواقعية

# إنشاء الجدول في قاعدة البيانات فور تشغيل الكود
with app.app_context():
    db.create_all()

# -------------------------- متغيرات النظام والذاكرة --------------------------
live_data = {"solar": 0.0, "wind": 0.0, "total": 0.0}

# الاعدادات في الموقع و القيم الافتراضية
system_settings = {
    "solarWatt": 100, "solarVmp": 18, 
    "windWatt": 400, "windCutIn": 3, "windRated": 12,
    "battAh": 100
}


# -------------------------- جلب البيانات من المواقع --------------------------

# انشاء دالة لجلب بيانات الطقس
def get_solar_data(lat=0.0, lon=0.0):

    forecasts = []  # قائمة لحفظ البيانات فيها ليسهل اظافتها لقاعدة البيانات
    ghi_list  = []  # قائمة لحفظ بيانات الاشعاع فيها ليسهل اظافتها لقاعدة البيانات

   # ------- openweathermap جلب بيانات الطقس بخطوط الطول و العرض من موقع

    # openweathermap لموقع API جلب مفتاح 
    WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY')
    url_w = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ar"
    
    try:
        response_w = requests.get(url_w, timeout=10)  # جلب البيانات
        data_w = response_w.json()                    # json تحويل البيانات لقاقمة
        
        if data_w.get("cod") == "200":

            # ------- استخراج بيانات الطقس
            city_name = data_w['city']['name']  # اسم المنطقة

            """ كل 8 قراءات تمثل يوماً كاملاً
            نأخذ قراءة اليوم (0)، غداً (8)، وبعد غد (16)
            إذا كانت قراءة [0] هي الساعة 9 صباحاً، فإن قراءة [1] ستكون 12 ظهراً.
            لذا يمكنك تعديل الأرقام لتناسب وقت ذروة الإنتاج الشمسي """
            for i in [0, 8, 16, 24, 30]:
                forecast = data_w['list'][i]  # اول قائمة

                # اظافة البيانات الجديدة للقائمة
                forecasts.append({
                    "city": city_name,
                    "temp": forecast['main']['temp'],     # درجة الحرارة
                    "cloud": forecast['clouds']['all'],   # نسبة الغيوم
                    "w_speed": forecast['wind']['speed']  # سرعة الرياح
                })
        else:
            return "APIخطأ في جلب البيانات، تأكد من اسم المنطقة أو مفتاح الـ"


        # ------- جلب قيمة الاشعاع الشمسي من موقع ناسا

        today = datetime.now()  # الحصول على تاريخ اليوم

        # لتجنب عدم وجود بيانات في ناسا نرجوع سنة واحدة للخلف بتاريخ البداية
        start_date_obj = today - timedelta(days=365)
        start_date = start_date_obj.strftime('%Y%m%d')  # تاريخ البداية مع التنسيق لتفهمه ناسا

        # تحديد تاريخ النهاية (بعد 4 أيام من تاريخ العام الماضي)
        end_date = (start_date_obj + timedelta(days=4)).strftime('%Y%m%d')

        # جلب بيانات الاشعاع الشمسي من ناسا
        # ناسا تعطي اقصى اشعاع ممكن في الوقت الحالي عند الضروف المثالية
        # الرابط الرسمي والمستقر لناسا
        url_GHI = (f"https://power.larc.nasa.gov/api/temporal/daily/point"
                   f"?parameters=ALLSKY_SFC_SW_DWN"  # هذا هو بارامتر الإشعاع الشمسي
                   f"&community=RE&longitude={lon}&latitude={lat}"
                   f"&start={start_date}&end={end_date}&format=JSON")
        
        response_GHI = requests.get(url_GHI, timeout=10)  # جلب البيانات

        # ------- استخراج قيمة الاشعاع الشمسي
        if response_GHI.status_code == 200:
            ghi_data = response_GHI.json()['properties']['parameter']['ALLSKY_SFC_SW_DWN']

            # اظافة البيانات الجديدة للقائمة
            for day, value in ghi_data.items():
                ghi_list.append({"day": day, "value": value})

        # ترتيب قائمة ناسا حسب التاريخ لضمان التوافق مع الأيام
        ghi_list = sorted(ghi_list, key=lambda x: x['day'])
        
        return forecasts, ghi_list
    
    except Exception as e:
        print(f"Error fetching data: {e}")
        return f"{response_GHI.status_code} :خطأ في الاتصال بالسيرفر"


# -------------------------- معادلات احتساب الطاقة المتوقعة --------------------------

def mathenatical_equations(ghi_value, cloud, temp, wind_speed):
    
    # --- حساب أمبير الشمس المتوقع 
    I_solar_max = float(system_settings['solarWatt']) / float(system_settings['solarVmp'])

    cloud_factor = cloud / 100.0
    adjusted_ghi = ghi_value * (1 - (cloud_factor * 0.8))
    f_temp = 0.2 if temp >= 40 else 1.0
    solar_power = round((adjusted_ghi / 5.0) * I_solar_max * f_temp, 3)

    # --- (Wind Power Curve) حساب أمبير التوربين المتوقع 
    I_wind_max = float(system_settings['windWatt']) / 12  # دائماً 12 فولت المناسب لبطارية مشروعنا
    v_cut_in, v_rated = float(system_settings['windCutIn']), float(system_settings['windRated'])
    
    # :منطق التوربين
    if wind_speed < v_cut_in: w_eff = 0    # الرياح أضعف من تحريك التوربين
    elif wind_speed >= v_rated: w_eff = 1  # التوربين في أقصى طاقته
    # معادلة تقريبية للكفاءة بين سرعة البدء والسرعة القصوى
    else: w_eff = (wind_speed - v_cut_in) / (v_rated - v_cut_in)
    
    # --- إجمالي الطاقة 
    wind_power = round(I_wind_max * w_eff, 3)
    total_power = round(solar_power + wind_power, 3)

    # --- زمن الشحن
    # (السعة / الأمبير الكلي) * 1.2 معامل الفقد
    batt_charge = round((float(system_settings['battAh']) / total_power) * 1.2, 2) if total_power > 0 else 0

    
    return [{"soler_power": solar_power, "dir_power": wind_power, "total_power": total_power, "battrey_charge": batt_charge}]


# -------------------------- (Routes) المسارات --------------------------

@app.route('/', methods=['GET', 'POST'])
def index():
    global live_data
    results = None

    sensor_display = {
            "amp1": 0.0,
            "amp2": 0.0,
            "amp3": 0.0
        }
    
    # --- الزر الأول: محاكي الحساسات (تحديث الذاكرة فقط) ---
    if request.method == 'POST':
        if 'simulate_sensor' in request.form:
            live_data["solar"] = float(request.form.get('solar_manual', 0))
            live_data["wind"] = float(request.form.get('wind_manual', 0))
            live_data["total"] = live_data["solar"] + live_data["wind"]

            # الرجوع للصفحة لتتحدث
            return redirect(url_for('index'))

        # --- الزر الثاني: تحليل الطقس (الحفظ الفعلي) ---
        elif 'get_weather' in request.form:
            lat, lon = request.form.get('lat'), request.form.get('lon')
            ac_on = 'ac_status' in request.form
            
      
            try:
                # سحب الأرقام من الحقول المخفية 
                real_solar = float(request.form.get('current_solar_real', 0))
                real_wind = float(request.form.get('current_wind_real', 0))
                real_total = float(request.form.get('current_total_real', 0))
            except ValueError:
                # في حال فشل التحويل نستخدم القيم من الذاكرة مباشرة
                real_solar = live_data["solar"]
                real_wind = live_data["wind"]
                real_total = live_data["total"]

            data_list = get_solar_data(lat, lon)

            if data_list:
                all_days_power = []
                
                current_now = datetime.now()  # نأخذ تاريخ اليوم
                
                for i in range(len(data_list[0])):
                    w, g = data_list[0][i], data_list[1][i]

                    # i ابدأ من اليوم وزد فقط بمقدار 
                    display_date = current_now + timedelta(days=i)

                    # نستخدم التاريخ "الحديث" للعرض فقط في الجدول
                    g['formatted_day'] = display_date.strftime('%d/%m/%Y')

                    calc = mathenatical_equations(g['value'], w['cloud'], w['temp'], w['w_speed'])[0]
                    all_days_power.append(calc)
                
                # حفظ السجل
                new_rec = EnergyRecord(
                    city=data_list[0][0]['city'], 
                    lat=float(lat), 
                    lon=float(lon),
                    ac_status="ON" if ac_on else "OFF", 
                    temp=data_list[0][0]['temp'],
                    clouds=data_list[0][0]['cloud'], 
                    wind_speed=data_list[0][0]['w_speed'],
                    solar_radiation=float(data_list[1][0]['value']),
                    solar_pred_amps=float(all_days_power[0]['soler_power']),
                    wind_pred_amps=float(all_days_power[0]['dir_power']),
                    total_pred_amps=float(all_days_power[0]['total_power']),
                    solar_power_real=float(real_solar),
                    wind_power_real=float(real_wind),
                    total_power_real=float(real_total)
                )

                # الحفظ النهائي
                db.session.add(new_rec)
                db.session.commit()
                
                results = {
                    "city": data_list[0][0]['city'], 
                    "days": data_list,             # هذه هي القائمة التي يبحث عنها الـ HTML
                    "power_list": all_days_power,  # القائمة التي تحتوي حسابات الـ 5 أيام
                    "ac_status": "شغال" if ac_on else "مطفأ",

                    "lat": str(round(float(lat),3)),
                    "lon": str(round(float(lon),3))
                }
            else:
                results = "فشل جلب بيانات الطقس."
        
        # تجهيز العرض للمربعات السوداء
        sensor_display = {
            "amp1": float(live_data["solar"]),
            "amp2": float(live_data["wind"]),
            "amp3": float(live_data["total"])
        }
    
    return render_template('index.html', results=results, sensor_data=sensor_display)


@app.route('/history')
def history():

    if request.args.get('password') != ADMIN_PASSWORD: return "Unauthorized", 403
    records = EnergyRecord.query.order_by(EnergyRecord.timestamp.desc()).all()
    return render_template('history.html', records=records)


@app.route('/download')
def download_csv():

    if request.args.get('password') != ADMIN_PASSWORD: return "Unauthorized", 403

    records = EnergyRecord.query.all()
    output = io.StringIO()

    # نكتب علامة الـ BOM لكي يفهم الإكسيل الحروف العربية فوراً
    output.write('\ufeff')

    writer = csv.writer(output)
    writer.writerow([
        'ID', 'city', 'lat', 'lon', 'ac_status', 'temp', 'wind_speed', 'clouds',
        'solar_radiation', 'solar_pred_amps', 'wind_pred_amps', 'total_pred_amps',
        'solar_power_real', 'wind_power_real', 'total_power_real'])
    for r in records: writer.writerow([
        str(r.id), str(r.city), str(r.lat) ,str(r.lon), str(r.ac_status), str(r.temp), 
        str(r.wind_speed), str(r.clouds), str(r.solar_radiation), str(r.solar_pred_amps),
        str(r.wind_pred_amps), str(r.total_pred_amps), str(r.solar_power_real),
        str(r.wind_power_real), str(r.total_power_real) ])

    output.seek(0)

    return Response(
        output.getvalue(), 
        mimetype="text/csv", 
        headers={"Content-disposition": "attachment; filename=energy_data.csv"})


# ESP8266 / ESP32 استقبال بيانات الحساسات من 
@app.route('/update_sensors', methods=['POST'])
def update_sensors():
    global live_data  # لنتمكن من تعديل المتغير العام

    # JSON استلام البيانات والتأكد أنها 
    data = request.get_json()
    if data:
        # (db.session.add بدون) نحدث القيم في الذاكرة فقط 
        live_data["solar"] = float(data.get('ldr1', 0))
        live_data["wind"] = float(data.get('ldr2', 0))
        live_data["total"] = float(live_data["solar"] + live_data["wind"])

        # هذان السطران هما بمثابة "رسالة تأكيد" أو "إيصال استلام" يرسلها السيرفر (البايثون) إلى
        # ليخبرها بأن المهمة تمت بنجاح ESP32الـ
        return {"status": "success"}, 200
    return {"status": "no_data"}, 400


# مسار تحديث البيانات بشكل مباشر
@app.route('/get_live_data')
def get_live_data():
    return jsonify({k: "{:.2f}".format(v/100000) for k, v in live_data.items()})


@app.route('/update_settings', methods=['POST'])
def update_settings():
    global system_settings
    data = request.get_json()

    if data:
        for k in data: system_settings[k] = data[k] if data[k] != "" else 0
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 400


if __name__ == '__main__':
    """ PORT يعطي تطبيقك بورت معين عبر متغير بيئة اسمه Render
    إذا لم يجد هذا المتغير (كما في جهازك)، سيستخدم 5000 كافتراضي
    القيمة الاحتياطية اذا كنت تشغل الكود على لابتوبك :5000
    (Render حيث لا يوجد نظام مثل موقع) سيستخدم البورت 5000 تلقائياً
    """
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)  # 0.0.0.0 تعني "استقبل من أي جهاز في الشبكة"



