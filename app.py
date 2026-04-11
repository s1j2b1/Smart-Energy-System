


import os
import csv
import io
import requests
from flask import Flask, render_template, request, Response, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from dotenv import load_dotenv

# مكتبات اللغة العربية - نحتاجها لتهيئة النصوص قبل المعالجة
import arabic_reshaper
from bidi.algorithm import get_display

load_dotenv()

app = Flask(__name__)

# -------------------------- دالة النصوص العربية --------------------------
def arab_txt(text):
    reshaped = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped)
    return bidi_text

# -------------------------- اعداد قاعدة البيانات --------------------------
base_dir = os.path.abspath(os.path.dirname(__file__))

# Render ملاحظة: الرابط سيؤخذ من إعدادات بيئة 
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///' + os.path.join(base_dir, 'base_dir.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") # افتراضي إذا لم يوجد

# -------------------------- تصميم الجدول --------------------------
class EnergyRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    city = db.Column(db.String(100))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    ac_status = db.Column(db.String(20))
    temp = db.Column(db.Float)
    wind_speed = db.Column(db.Float)
    clouds = db.Column(db.Integer)
    solar_radiation = db.Column(db.Float)
    solar_pred_amps = db.Column(db.Float)
    wind_pred_amps = db.Column(db.Float)
    total_pred_amps = db.Column(db.Float)
    solar_power_real = db.Column(db.Float)
    wind_power_real = db.Column(db.Float)
    total_power_real = db.Column(db.Float)

with app.app_context():
    db.create_all()

# -------------------------- متغيرات النظام والذاكرة --------------------------
live_data = {"solar": 0.0, "wind": 0.0, "total": 0.0}
system_settings = {
    "solarWatt": 100, "solarVmp": 18, 
    "windWatt": 400, "windCutIn": 3, "windRated": 12,
    "battAh": 100
}

# -------------------------- جلب البيانات --------------------------
def get_solar_data(lat, lon):
    forecasts = []
    ghi_list = []
    WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY')
    
    url_w = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ar"
    
    try:
        response_w = requests.get(url_w, timeout=10)
        data_w = response_w.json()
        
        if data_w.get("cod") == "200":
            city_name = data_w['city']['name']
            for i in [0, 8, 16, 24, 30]:
                f = data_w['list'][i]
                forecasts.append({
                    "city": city_name,
                    "temp": f['main']['temp'],
                    "cloud": f['clouds']['all'],
                    "w_speed": f['wind']['speed']
                })
        else:
            return None

        # جلب بيانات ناسا (تاريخ العام الماضي)
        today = datetime.now()
        start_date_obj = today - timedelta(days=365)
        start_date = start_date_obj.strftime('%Y%m%d')
        end_date = (start_date_obj + timedelta(days=4)).strftime('%Y%m%d')

        url_GHI = (f"https://power.larc.nasa.gov/api/temporal/daily/point"
                   f"?parameters=ALLSKY_SFC_SW_DWN&community=RE&longitude={lon}&latitude={lat}"
                   f"&start={start_date}&end={end_date}&format=JSON")
        
        response_GHI = requests.get(url_GHI, timeout=10)
        if response_GHI.status_code == 200:
            ghi_data = response_GHI.json()['properties']['parameter']['ALLSKY_SFC_SW_DWN']
            for day, value in ghi_data.items():
                ghi_list.append({"day": day, "value": value})
        
        return forecasts, ghi_list
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def mathenatical_equations(ghi_value, cloud, temp, wind_speed):
    # الحسابات (نفس منطقك الرياضي)
    I_solar_max = float(system_settings['solarWatt']) / float(system_settings['solarVmp'])
    cloud_factor = cloud / 100.0
    adjusted_ghi = ghi_value * (1 - (cloud_factor * 0.8))
    f_temp = 0.2 if temp >= 40 else 1.0
    solar_p = round((adjusted_ghi / 5.0) * I_solar_max * f_temp, 3)

    I_wind_max = float(system_settings['windWatt']) / 12
    v_cut_in, v_rated = float(system_settings['windCutIn']), float(system_settings['windRated'])
    
    if wind_speed < v_cut_in: w_eff = 0
    elif wind_speed >= v_rated: w_eff = 1
    else: w_eff = (wind_speed - v_cut_in) / (v_rated - v_cut_in)
    
    wind_p = round(I_wind_max * w_eff, 3)
    total_p = round(solar_p + wind_p, 3)
    batt_charge = round((float(system_settings['battAh']) / total_p) * 1.2, 2) if total_p > 0 else 0

    return [{"soler_power": solar_p, "dir_power": wind_p, "total_power": total_p, "battrey_charge": batt_charge}]


# -------------------------- المسارات (Routes) --------------------------
@app.route('/', methods=['GET', 'POST'])
def index():
    global live_data
    results = None
    
    if request.method == 'POST':
        if 'simulate_sensor' in request.form:
            live_data["solar"] = float(request.form.get('solar_manual', 0))
            live_data["wind"] = float(request.form.get('wind_manual', 0))
            live_data["total"] = live_data["solar"] + live_data["wind"]
            return redirect(url_for('index'))

        elif 'get_weather' in request.form:
            lat, lon = request.form.get('lat'), request.form.get('lon')
            ac_on = 'ac_status' in request.form
            
            data_list = get_solar_data(lat, lon)
            if data_list:
                all_days_power = []
                for i in range(len(data_list[0])):
                    w, g = data_list[0][i], data_list[1][i]
                    calc = mathenatical_equations(g['value'], w['cloud'], w['temp'], w['w_speed'])[0]
                    all_days_power.append(calc)
                
                # حفظ السجل
                new_rec = EnergyRecord(
                    city=data_list[0][0]['city'], lat=float(lat), lon=float(lon),
                    ac_status="ON" if ac_on else "OFF", temp=data_list[0][0]['temp'],
                    clouds=data_list[0][0]['cloud'], wind_speed=data_list[0][0]['w_speed'],
                    solar_radiation=float(data_list[1][0]['value']),
                    solar_pred_amps=all_days_power[0]['soler_power'],
                    wind_pred_amps=all_days_power[0]['dir_power'],
                    total_pred_amps=all_days_power[0]['total_power'],
                    solar_power_real=live_data["solar"],
                    wind_power_real=live_data["wind"],
                    total_power_real=live_data["total"]
                )
                db.session.add(new_rec)
                db.session.commit()
                
                results = {"city": data_list[0][0]['city'], "days": data_list, "power_list": all_days_power, "lat": lat, "lon": lon}
    
    return render_template('index.html', results=results, sensor_data=live_data)

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
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['ID', 'City', 'Lat', 'Lon', 'Temp', 'Solar_Pred', 'Wind_Pred', 'Real_Total'])
    for r in records:
        writer.writerow([r.id, r.city, r.lat, r.lon, r.temp, r.solar_pred_amps, r.wind_pred_amps, r.total_power_real])
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=energy_data.csv"})


@app.route('/update_sensors', methods=['POST'])
def update_sensors():
    global live_data
    data = request.get_json()
    if data:
        live_data["solar"] = float(data.get('ldr1', 0))
        live_data["wind"] = float(data.get('ldr2', 0))
        live_data["total"] = float(data.get('ldr3', 0))
        return {"status": "success"}, 200
    return {"status": "no_data"}, 400


@app.route('/get_live_data')
def get_live_data():
    return jsonify({k: "{:.2f}".format(v) for k, v in live_data.items()})


@app.route('/update_settings', methods=['POST'])
def update_settings():
    global system_settings
    data = request.get_json()
    if data:
        for k in data: system_settings[k] = data[k] if data[k] != "" else 0
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 400


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)



