

#include <WiFi.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include <Adafruit_MCP3008.h>

const char* ssid = "Alqasim Alrubkhi";
const char* password = "12345678";
const char* serverName = "https://smart-energy-system-w0xz.onrender.com/update_sensors";

// تعريف أطراف SPI
#define MCP_CS   5
#define MCP_MOSI 23
#define MCP_MISO 19
#define MCP_CLK  18

Adafruit_MCP3008 adc;

void setup() {
  Serial.begin(115200);

  // بدء الاتصال بـ MCP3008
  if (!adc.begin(MCP_CLK, MCP_MOSI, MCP_MISO, MCP_CS)) {
    Serial.println("Error: MCP3008 not found! Check your wiring.");
    while (1);
  }
  
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");
}

void loop() {
  // 1. قراءة البيانات مع تأخير بسيط بين كل قناة لضمان استقرار الجهد
  int l1 = adc.readADC(0); delay(10);
  int l2 = adc.readADC(1); delay(10);
  int l3 = adc.readADC(2); delay(10);
  int ml = adc.readADC(3); delay(10);

  // طباعة القيم في الـ Serial للتأكد أنها تتغير في يدك
  Serial.printf("Raw: CH0:%d | CH1:%d | CH2:%d | LDR:%d\n", l1, l2, l3, ml);

  if (WiFi.status() == WL_CONNECTED) {
    NetworkClientSecure client;
    client.setInsecure();
    HTTPClient http;
    
    if (http.begin(client, serverName)) { 
      http.addHeader("Content-Type", "application/json");

      StaticJsonDocument<200> doc;
      doc["ldr1"] = l1;
      doc["ldr2"] = l2;
      doc["ldr3"] = l3;
      doc["my_ldr"] = ml;

      String requestBody;
      serializeJson(doc, requestBody);

      int httpResponseCode = http.POST(requestBody);
      Serial.print("HTTP Status: ");
      Serial.println(httpResponseCode);
      http.end();
    }
  }
  
  delay(3000); // إرسال كل 3 ثوانٍ للاختبار السريع
}
