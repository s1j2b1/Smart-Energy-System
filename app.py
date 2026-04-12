

import os   # للتعامل مع ملفات النظام
import csv  # xl لانشاء و تحميل ملفات 
import io   # للتعامل مع تدفق البيانات في الذاكرة
import requests  # و جلب بيانات الطقسOpenWeatherMap لارسال الطلبات لموقع 
from flask import Flask, render_template, request, Response  # مكتبات بناء الموقع
from flask_sqlalchemy import SQLAlchemy  # مكتبة ادارة قاعدة البيانات

# لتسجيل الوقت و التاريخ لكل عملية (اتعامل مع التاريخ)
from datetime import datetime, timedelta

from flask import jsonify  # نستخدمة لمسار تحديث البيانات
from flask import redirect, url_for  # نستخدمه للتوجه لصفحة معينة عن طريق دوال المسارات

from dotenv import load_dotenv  # بشكل امن API لقرائة مفاتيح
load_dotenv()


# دالة لاظهار الكتابة العربية بشكل صحيح
def arab_txt(text):
    import arabic_reshaper
    from bidi.algorithm import get_display
    reshaped = arabic_reshaper.reshape(text) # يرتب الحروف داخل الكلمة (shaping)  
    bidi_text = get_display(reshaped)        # يعدّل الاتجاه للعرض في بيئة LTR
    return bidi_text
print(arab_txt('اعوذ بالله من الشيطان الرجيم\n'))


app= Flask(__name__)  # Flask انشاء موقع

# -------------------------- اعداد قاعدة البيانات --------------------------

base_dir = os.path.abspath(os.path.dirname(__file__))  # تحديد مسار المجلد الحالي
# اذا لم يكن موجودbase_dir.db ننشئ ملف قاعدة بيانات باسم
app.config['SQLALCHEMY_DATABASE_URI']= os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(base_dir, 'base_dir.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # إغلاق ميزة إضافية لتوفير موارد السيرفر
db= SQLAlchemy(app)  # ربط قاعدة البيانات بالموقع

# انشاء و جلب رمز للتعامل مع قاعدة البيانات
ADMIN_PASSWORD= os.environ.get("ADMIN_PASSWORD")

# ------- تصميم جدول البيانات (الأعمدة التي سيتم حفظها) 
class EnergyRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # رقم تسلسلي لكل عملية
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # وقت التسجيل
    city = db.Column(db.String(100))           # اسم المنطقة/المدينة
    lat = db.Column(db.Float)                  # خط الطول للمنطقة
    lon = db.Column(db.Float)                  # خط عرض للمنطقة
    ac_status = db.Column(db.String(20))       # حالة المكيف (شغال/مطفأ)

    temp = db.Column(db.Float)                 # درجة الحرارة
    wind_speed = db.Column(db.Float)           # سرعة الرياح
    clouds = db.Column(db.Integer)             # نسبة الغيوم
    solar_radiation = db.Column(db.Float)      # الإشعاع الشمسي المحسوب
    solar_pred_amps = db.Column(db.Float)      # أمبير الطاقة الشمسية المتوقع
    wind_pred_amps = db.Column(db.Float)       # أمبير التوربين المتوقع
    total_pred_amps = db.Column(db.Float)      # المجموع الكلي للأمبير المتوقع


    solar_power_real = db.Column(db.Float)     # الطاقة الواقعية من اللوح الشمسي
    wind_power_real = db.Column(db.Float)      # الطاقة الواقعية من توربين الرياح
    total_power_real = db.Column(db.Float)     # الطاقة الاجمالية الواقعية

# إنشاء الجدول في قاعدة البيانات فور تشغيل الكود
with app.app_context():
    db.create_all()


# -------------------------- جلب البيانات من المواقع --------------------------

# انشاء دالة لجلب بيانات الطقس
def get_solar_data(lat=0.0, lon=0.0):
    
    forecasts = []  # قائمة لحفظ البيانات فيها ليسهل اظافتها لقاعدة البيانات
    ghi_list  = []  # قائمة لحفظ بيانات الاشعاع فيها ليسهل اظافتها لقاعدة البيانات

   # ------- openweathermap جلب بيانات الطقس بخطوط الطول و العرض من موقع
    
    # openweathermap لموقع API جلب مفتاح 
    WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY')
    url_w = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ar" 

    response_w = requests.get(url_w)  # جلب البيانات
    data_w = response_w.json()        # json تحويل البيانات لقاقمة


    # ------- استخراج بيانات الطقس
    city_name = data_w['city']['name']      # اسم المنطقة
    
    if data_w.get("cod") == "200":

        """ كل 8 قراءات تمثل يوماً كاملاً
         نأخذ قراءة اليوم (0)، غداً (8)، وبعد غد (16)
         إذا كانت قراءة [0] هي الساعة 9 صباحاً، فإن قراءة [1] ستكون 12 ظهراً.
         لذا يمكنك تعديل الأرقام لتناسب وقت ذروة الإنتاج الشمسي """
        for i in [0, 8, 16, 24, 30]:
            forecast = data_w['list'][i]            # اول قائمة
            temp = forecast['main']['temp']         # درجة الحرارة
            cloud = forecast['clouds']['all']       # نسبة الغيوم
            wind_speed = forecast['wind']['speed']  # سرعة الرياح

            # اظافة البيانات الجديدة للقائمة
            forecasts.append({
                "city": city_name,
                "temp": temp,
                "cloud": cloud,
                "w_speed": wind_speed
            })
        # print("forecasts:\n", forecasts)

    else:
        print(arab_txt("APIخطأ في جلب البيانات، تأكد من اسم المنطقة أو مفتاح الـ"))


    # ------- جلب قيمة الاشعاع الشمسي من موقع ناسا

    # الحصول على تاريخ اليوم
    today = datetime.now()

    # لتجنب عدم وجود بيانات في ناسا نرجوع سنة واحدة للخلف بتاريخ البداية
    # نستخدم replace لتغيير السنة فقط مع الحفاظ على نفس اليوم والشهر
    try:
        start_date_obj = today.replace(year=today.year - 1)
    except ValueError:
        # هذا السطر للتعامل مع حالة نادرة (إذا كان اليوم 29 فبراير وسنة مضت لم تكن كبيسة)
        start_date_obj = today.replace(year=today.year - 1, day=today.day - 1)

    start_date = start_date_obj.strftime('%Y%m%d')  # تاريخ البداية مع التنسيق لتفهمه ناسا

    # تحديد تاريخ النهاية (بعد 4 أيام من تاريخ العام الماضي)
    end_date_obj = start_date_obj + timedelta(days=4)
    end_date = end_date_obj.strftime('%Y%m%d')

    # جلب بيانات الاشعاع الشمسي من ناسا
    # ناسا تعطي اقصى اشعاع ممكن في الوقت الحالي عند الضروف المثالية
    # الرابط الرسمي والمستقر لناسا
    url_GHI = (f"https://power.larc.nasa.gov/api/temporal/daily/point"
           f"?parameters=ALLSKY_SFC_SW_DWN" # هذا هو بارامتر الإشعاع الشمسي
           f"&community=RE"
           f"&longitude={lon}"
           f"&latitude={lat}"
           f"&start={start_date}"
           f"&end={end_date}"
           f"&format=JSON")

    response_GHI= requests.get(url_GHI)  # جلب البيانات
    data_GHI = response_GHI.json()       # json تحويل البيانات لقاقمة

    
    # ------- استخراج قيمة الاشعاع الشمسي
    if response_GHI.status_code == 200:
        # (kW-hr/m^2/day تأتي بوحدة) استخراج القيمة 
        ghi_value = data_GHI['properties']['parameter']['ALLSKY_SFC_SW_DWN']

        for day, value in ghi_value.items():
            # print(f"التاريخ: {day} | الإشعاع: {value}")

            # اظافة البيانات الجديدة للقائمة
            ghi_list.append({
                "day": day ,
                "value": value
            })


    else:
        return f"{response_GHI.status_code} :خطأ في الاتصال بالسيرفر"

    print(arab_txt(f"توقعات الطقس لمنطقة: {city_name}"))
    print(arab_txt(f"{ghi_list[1]['value']} kWh/m² :{ghi_list[1]['day']} نسبة الاشعاع الشمسي تاريخ"))
    print(arab_txt(f"نسبة الغيوم: {cloud}%"))  
    print(arab_txt(f"{temp}°C :درجة الحرارة"))
    print(arab_txt(f"{wind_speed} m/s :سرعة الرياح"))
    print()


    return forecasts, ghi_list



# -------------------------- معادلات احتساب الطاقة المتوقعة --------------------------
# -------------------------- معادلات احتساب الطاقة المتوقعة --------------------------

def mathenatical_equations(ghi_value, cloud, temp, wind_speed):
    global system_settings  # للوصول للقيم التي حفظها المستخدم
    
    forecasts = []

    # --- أ- حساب أمبير الشمس المتوقع ---
    # تحويل الواط والجهد إلى "أمبير أقصى" نظري
    I_solar_max = float(system_settings['solarWatt']) / float(system_settings['solarVmp'])
    
    # معامل السحب والحرارة (كما هي في كودك السابق)
    cloud_factor = cloud / 100.0
    reduction_impact = 0.8 
    adjusted_ghi = ghi_value * (1 - (cloud_factor * reduction_impact))
    f_cloud = round(adjusted_ghi, 3) 
    f_temp = 0.2 if temp >= 40 else 1.0

    # المعادلة: (الإشعاع الحالي / 1.0) * الأمبير الأقصى
    # ملاحظة: ناسا تعطي الإشعاع كـ kWh/m2/day، المتوسط الساعي القريب للذروة هو تقسيم القيمة على 1 (تبسيط)
    solar_power = (f_cloud / 5.0) * I_solar_max * f_temp # تقسيم على 5 لتقدير الساعة الواحدة من معدل اليوم
    solar_power = round(solar_power, 3)


    # --- ب- حساب أمبير التوربين المتوقع (Wind Power Curve) ---
    I_wind_max = float(system_settings['windWatt']) / 12  # دائماً 12 فولت كما طلبت
    v_cut_in = float(system_settings['windCutIn'])
    v_rated = float(system_settings['windRated'])
    
    # منطق التوربين:
    if wind_speed < v_cut_in:
        wind_efficiency = 0  # الرياح أضعف من تحريك التوربين
    elif wind_speed >= v_rated:
        wind_efficiency = 1  # التوربين في أقصى طاقته
    else:
        # معادلة تقريبية للكفاءة بين سرعة البدء والسرعة القصوى
        wind_efficiency = (wind_speed - v_cut_in) / (v_rated - v_cut_in)

    # تأثير المكيف (كما في منطقك السابق)
    Ac = 'ac_status' in request.form
    if Ac:
        # إذا المكيف شغال، نضيف قوة دفع ثابتة أو نعدل الكفاءة
        wind_efficiency = max(wind_efficiency, 0.5) # المكيف يضمن حد أدنى 50% كفاءة

    wind_power = I_wind_max * wind_efficiency
    wind_power = round(wind_power, 3)


    # --- ج- إجمالي الطاقة وزمن الشحن ---
    total_power = solar_power + wind_power
    total_power = round(total_power, 3)

    # سعة البطارية من الإعدادات
    batt_ah = float(system_settings['battAh'])
    
    # منع القسمة على صفر
    if total_power > 0:
        # (السعة / الأمبير الكلي) * 1.2 معامل الفقد
        battrey_charge = (batt_ah / total_power) * 1.2
        battrey_charge = round(battrey_charge, 2)
    else:
        battrey_charge = 0

    forecasts.append({
        "f_cloud": f_cloud,
        "soler_power": solar_power,
        "dir_power": wind_power,
        "total_power": total_power,
        "battrey_charge": battrey_charge
    })

    return forecasts

# -------------------------- المسارات --------------------------
# سنحدث هذا المتغير فقط ESPمتغير خارج الدوال ليمسك آخر قيم وصلت، وعندما ترسل الـ
live_data = {
    "solar": 0.0,
    "wind": 0.0,
    "total": 0.0
}

@app.route('/', methods=['GET', 'POST'])
def index():
    global live_data
    results = None

    # --- الزر الأول: محاكي الحساسات (تحديث الذاكرة فقط) ---
    if request.method == 'POST' and 'simulate_sensor' in request.form:
        s_val = request.form.get('solar_manual', 0)
        w_val = request.form.get('wind_manual', 0)
        
        live_data["solar"] = float(s_val)
        live_data["wind"] = float(w_val)
        live_data["total"] = float(s_val) + float(w_val)
        
        # الرجوع للصفحة لتتحدث
        return redirect(url_for('index'))
    
    # --- الزر الثاني: تحليل الطقس (الحفظ الفعلي) ---
    elif request.method == 'POST' and 'get_weather' in request.form:
        lat = request.form.get('lat')
        lon = request.form.get('lon')
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
            for i in range(len(data_list[0])):
                w_day = data_list[0][i]
                g_day = data_list[1][i]

                # تحويل النص '20260307' إلى كائن تاريخ ثم تنسيقه
                raw_date = str(g_day['day']) # نضمن أنه نص
                date_obj = datetime.strptime(raw_date, '%Y%m%d')
                
                # اختر التنسيق الذي يعجبك:
                # '%A, %d, %B' تعني: "اليوم بالاسم، رقم اليوم، اسم الشهر"
                g_day['formatted_day'] = date_obj.strftime('%d/%m/%Y') 


                day_calc = mathenatical_equations(g_day['value'], w_day['cloud'], w_day['temp'], w_day['w_speed'])[0]
                all_days_power.append(day_calc)

            today_w = data_list[0][0]
            today_ghi = data_list[1][0]
            power_data = all_days_power[0]

            # إنشاء السجل "الكامل" الذي يجمع الطقس والبيانات الواقعية
            new_record = EnergyRecord(
                city=today_w.get('city', 'Unknown'),
                lat=float(lat),
                lon=float(lon),
                ac_status="NO" if ac_on else "OFF",
                temp=today_w['temp'],
                clouds=today_w['cloud'],
                wind_speed=today_w['w_speed'],
                solar_radiation=float(today_ghi['value']),
                solar_pred_amps=float(power_data['soler_power']),
                wind_pred_amps=float(power_data['dir_power']),
                total_pred_amps=float(power_data['total_power']),
                solar_power_real=(real_solar), # البيانات من المربعات السوداء
                wind_power_real=(real_wind),
                total_power_real=(real_total)
            )
            
            # الحفظ النهائي
            db.session.add(new_record)
            db.session.commit()
            results = {
                "city": today_w.get('city', 'Unknown'),
                "days": data_list, # هذه هي القائمة التي يبحث عنها الـ HTML
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

    return render_template('index_t.html', results=results, sensor_data=sensor_display)


@app.route('/history')
def history():
    pwd = request.args.get('password')
    if pwd != ADMIN_PASSWORD: return "خطأ في كلمة المرور"
    records = EnergyRecord.query.order_by(EnergyRecord.timestamp.desc()).all()
    return render_template('history.html', records=records)


@app.route('/download')
def download_csv():
    
    pwd = request.args.get('password')
    if pwd != ADMIN_PASSWORD: return "عذرا البيانات للمصرح لهم فقط", 403
    
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

    # لضمان وصول البصمة (getvalue) هنا: نرسل محتوى النص بالكامل 
    return Response(
        output.getvalue(), 
        mimetype="text/csv", 
        headers={"Content-disposition": "attachment; filename=data.csv"})


# ESP8266 / ESP32 استقبال بيانات الحساسات من 
@app.route('/update_sensors', methods=['POST'])
def update_sensors():
    
    global live_data # لنتمكن من تعديل المتغير العام

    # JSON استلام البيانات والتأكد أنها 
    data = request.get_json()
    if data:
        # (db.session.add بدون) نحدث القيم في الذاكرة فقط 
        live_data["solar"] = float(data.get('ldr1', 0))
        live_data["wind"]  = float(data.get('ldr2', 0))
        live_data["total"] = float(data.get('ldr3', 0))

        # هذان السطران هما بمثابة "رسالة تأكيد" أو "إيصال استلام" يرسلها السيرفر (البايثون) إلى
        # ليخبرها بأن المهمة تمت بنجاح ESP32الـ
        return {"status": "updated_in_memory"}, 200
    return {"status": "success"}, 200



# مسار تحديث البيانات بشكل مباشر
@app.route('/get_live_data')
def get_live_data():
    global live_data

    # نرسل القيم الموجودة في الذاكرة حالياً
    return jsonify({
        # live_data["solar"]
        "solar": "{:.2f}".format(float(live_data["solar"])), 
        "wind": "{:.2f}".format(float(live_data["wind"])),
        "total": "{:.2f}".format(float(live_data["total"]))
    })



system_settings = {
    "solarWatt": 100, "solarVmp": 18, 
    "windWatt": 400, "windCutIn": 3, "windRated": 12,
    "battAh": 100
}

@app.route('/update_settings', methods=['POST'])
def update_settings():
    global system_settings
    data = request.get_json()
    
    # تحديث القيم مع التأكد أنها أرقام
    for key in data:
        if data[key] == "": data[key] = 0 # إذا ترك الخانة فارغة
        system_settings[key] = data[key]
    
    print(f"تم تحديث الإعدادات: {system_settings}")
    return jsonify({"status": "success"})



if __name__ == '__main__':
    # app.run(debug=True)
    
    """ PORT يعطي تطبيقك بورت معين عبر متغير بيئة اسمه Render
    إذا لم يجد هذا المتغير (كما في جهازك)، سيستخدم 5000 كافتراضي
    القيمة الاحتياطية اذا كنت تشغل الكود على لابتوبك :5000
    (Render حيث لا يوجد نظام مثل موقع) سيستخدم البورت 5000 تلقائياً
    """
    port = int(os.environ.get('PORT', 5000))  
    
    # تشغيل التطبيق
    app.run(host='0.0.0.0', port=port)  # 0.0.0.0 تعني "استقبل من أي جهاز في الشبكة"







