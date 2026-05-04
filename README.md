

# 🚀 Renewable Energy Generation & Forecasting System (IoT)

An intelligent full-stack IoT ecosystem designed to monitor real-time Solar and Wind power generation and provide data-driven production forecasts.

---

## 💡 Project Overview
Traditional renewable energy systems often lack predictive insights. This project bridges that gap by combining **IoT sensing** with **Climate Data Analytics**. It doesn't just show you what you are producing now; it tells you what you will likely produce over the next 5 days.

## ✨ Key Features
* **Live Monitoring:** High-precision tracking of Solar and Wind current (Amps) and Power (Watts).
* **5-Day Predictive Engine:** Integrated **NASA POWER API** and **OpenWeatherMap** to estimate future energy yield based on solar irradiance, cloud cover, and wind speeds.

* **Interactive UI:** A modern dashboard featuring **Leaflet.js** for geographic positioning and **AJAX** for real-time updates without page reloads.
* **ML-Ready Architecture:** Automated data logging using **SQLAlchemy** with a built-in **CSV Export** feature to build datasets for training future Machine Learning models.

## 🛠️ Tech Stack

### Hardware
* **ESP32:** Main microcontroller with Wi-Fi connectivity.
* **ACS712 Sensors:** For measuring generated current from Solar/Wind.

### Software
* **Backend:** Python (Flask)
* **Database:** SQLite / PostgreSQL (via SQLAlchemy)
* **Frontend:** HTML5, CSS3 (Bootstrap), JavaScript (AJAX, Leaflet.js)
* **APIs:** NASA POWER (Climate Data) & OpenWeather (Real-time Weather)

## 📊 Data Analytics & ML Readiness
The system is designed with a **"Data-First"** approach:
1.  **Collection:** Every generation cycle is logged into the database.
2.  **Archiving:** Users can download historical data as a `.csv` file.
3.  **Future Integration:** The exported data is structured for training Regression Models to further optimize generation forecasting.

## 🚀 Installation & Setup

1. **Hardware Setup:** Connect sensors to MCP3008 and link to ESP32 via SPI protocol.
2. **Clone the Repository:**
   ```bash
   cd ~/Desktop
   git clone https://github.com/s1j2b1/Smart-Energy-System.git

## Install Dependencies
pip install -r requirements.txt

## Environment Variables: Create a .env file and add your API keys
WEATHER_API_KEY=your_openweather_key
ADMIN_PASSWORD=your_secure_password

## Run the Application
python app.py


## 🔗 Live Demo
Check out the live dashboard here: https://smart-energy-system-w0xz.onrender.com

