/*
  Barangay RFID: ESP32 + MFRC522 + SSD1306 + button, LEDs and MAX98357A I2S speech.
  Libraries: MFRC522, Adafruit GFX, Adafruit SSD1306, ArduinoJson 7.
  Works with ESP32 Arduino core 2.x / 3.x.

  Public HTTPS reader. Configure reader_secrets.h before uploading.

  Wiring v4 (classic ESP32 + SSD1306 128x64 I2C):
  RC522 SS=5, RST=27, SCK=18, MISO=19, MOSI=23, VCC=3.3V, GND.
  OLED physical labels GND,VCC,SCL,SDA: GND,3.3V,22,21. Address auto 0x3C/0x3D.
  Green LED=26, Red LED=25 (each through a 220-ohm resistor).
  MAX98357A DIN=33, BCLK=32, LRC=13. Button=4 to GND, INPUT_PULLUP.
  Open this sketch with audio_engine.h and audio_clips.h in the SAME folder.
  For a 4 MB classic ESP32, select Huge APP (3 MB No OTA) in Arduino IDE.

  Registration taps are never attendance events. Green success means the
  server accepted attendance. Unknown delivery results retain ONE event in
  flash and retry its SAME ID; they are never displayed as successful.
*/
#include <WiFi.h>
#include <freertos/semphr.h>
#include <WiFiClientSecure.h>
#if __has_include("reader_secrets.h")
#include "reader_secrets.h"
#else
#include "reader_secrets_example.h"
#endif
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <SPI.h>
#include <Wire.h>
#include <MFRC522.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <esp_arduino_version.h>
#include <esp_random.h>
#include <esp_system.h>
#if !defined(CONFIG_IDF_TARGET_ESP32)
#error "This diagram uses classic ESP32 GPIOs. Do not select ESP32-C3/S3."
#endif
#include <time.h>
#include <sys/time.h>
#include "audio_engine.h"
#include "oled_ui.h"

enum ReaderState { BOOTING, WIFI_DOWN, SERVER_DOWN, SETUP_NEEDED, ONLINE };

const char* SERVER_URL = "https://staclara-norte.vercel.app";

constexpr uint8_t SS_PIN=5, RST_PIN=27, GREEN_LED=26, RED_LED=25;
constexpr uint8_t BUTTON_PIN=4, I2C_SDA=21, I2C_SCL=22;
constexpr uint32_t CONFIRM_WINDOW_MS=10000, MODE_POLL_MS=1000;
constexpr uint32_t RETRY_MS=8000;
MFRC522 rfid(SS_PIN,RST_PIN);
// Use 100 kHz during and after OLED transfers for the wiring stability test.
constexpr uint16_t OLED_WIDTH=128, OLED_HEIGHT=64;
Adafruit_SSD1306 display(OLED_WIDTH,OLED_HEIGHT,&Wire,-1,100000UL,100000UL);

bool beginOLED() {
  Wire.begin(I2C_SDA,I2C_SCL);
  Wire.setClock(100000);
  Wire.setTimeOut(50);
  for (uint8_t address : {uint8_t(0x3C), uint8_t(0x3D)}) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission()!=0) continue;
    Serial.printf("OLED I2C response at 0x%02X; using SSD1306 128x64 driver.\n",address);
    // An I2C acknowledgement does not identify the controller model.
    if (!display.begin(SSD1306_SWITCHCAPVCC,address,true,false)) return false;
    display.clearDisplay();
    display.dim(true);
    display.display();
    return true;
  }
  return false;
}
Preferences storage;
String server, captureId, pendingEvent;
bool configured=false;
uint32_t lastModePoll=0, lastRetry=0;
String lastScreen;
String feedbackInFlight, audioAckToken;
ReaderState readerState=BOOTING;
bool wasReady=false;
bool classifyingCard=false;
uint32_t greenUntil=0;
uint32_t wifiDownSince=0;

void readerStatus(ReaderState next) {
  if(readerState==next)return;
  readerState=next;
  invalidateTransientAudio();
  if(next==ONLINE) {
    if(!pendingEvent.length())queueSound(wasReady ? RESTORED : READY);
    wasReady=true;
  } else if(next==WIFI_DOWN)queueSound(WIFI_LOST);
  else if(next==SERVER_DOWN)queueSound(OFFLINE_VOICE);
  else if(next==SETUP_NEEDED)queueSound(READER_SETUP);
}

SoundKind voiceForReply(JsonDocument& reply) {
  String value=String(reply["voice_code"] | "GENERIC_ERROR");
  for(uint8_t i=0;i<VOICE_CLIP_COUNT;i++)
    if(value==VOICE_CODES[i])return (SoundKind)i;
  return GENERIC_ERROR;
}
bool pendingAnnounced=false;

void screen(const String& title, const String& line1="",
            const String& line2="", const String& line3="") {
  String signature=title+"|"+line1+"|"+line2+"|"+line3;
  if (signature==lastScreen) return;
  lastScreen=signature;
  CivicOLED::render(display,title,line1,line2,line3,
    WiFi.status()==WL_CONNECTED,WiFi.RSSI());
}

void failure(const String& message, SoundKind voice=GENERIC_ERROR) {
  invalidateTransientAudio();
  Serial.println(message);
  screen("ERROR",message);
  digitalWrite(RED_LED,HIGH);
  queueSound(voice);
  delay(1500); digitalWrite(RED_LED,LOW);
}

bool clockReady() { return time(nullptr)>1700000000; }

void syncServerTime(JsonDocument& reply) {
  String stamp=String(reply["time"] | "");
  struct tm value={};
  if (strptime(stamp.c_str(),"%Y-%m-%dT%H:%M:%S",&value)) {
    time_t epoch=mktime(&value);
    if (epoch>1700000000) {
      struct timeval now={epoch,0}; settimeofday(&now,nullptr);
    }
  }
}

// Returns a positive HTTP status or a negative transport/JSON error.
int postJson(const char* endpoint, const String& body, JsonDocument& reply) {
  reply.clear();
  if (WiFi.status()!=WL_CONNECTED) {
    reply["message"]="Wi-Fi not connected"; return -1;
  }
  if (!clockReady()) {
    reply["message"]="Waiting for NTP clock"; return -1;
  }
  WiFiClientSecure client;
  client.setCACert(READER_ROOT_CA);
  HTTPClient http;
  http.setConnectTimeout(4000); http.setTimeout(20000);
  if (!http.begin(client,server+endpoint)) {
    reply["message"]="Cannot open server URL"; return -1;
  }
  http.addHeader("Content-Type","application/json");
  http.addHeader("Accept","application/json");
  http.addHeader("Authorization", String("Bearer ") + READER_CREDENTIAL);
  int code=http.POST(body);
  String response=code>0 ? http.getString() : String();
  http.end();
  if (code != 200) Serial.printf("Reader API %s returned %d\n", endpoint, code);
  if (code<=0) {
    reply["message"]="Cannot reach HTTPS server"; return code;
  }
  if (deserializeJson(reply,response)) {
    reply.clear(); reply["message"]=String("Server returned HTTP ")+code;
    return code==200 ? -2 : code;
  }
  return code;
}

String messageOf(JsonDocument& reply) {
  return String(reply["message"] | "Server rejected request");
}

int requestMode(const String& sentAck, JsonDocument& reply) {
  JsonDocument modeRequest;
  if(sentAck.length())modeRequest["ack_capture_id"]=sentAck;
  String modeBody;serializeJson(modeRequest,modeBody);
  return postJson("/attendance/api/registration-mode",modeBody,reply);
}

bool applyMode(int code, JsonDocument& reply, const String& sentAck) {
  String oldCapture=captureId;
  if(code==200) {
    if(sentAck.length() && String(reply["feedback_acknowledged"] | "")==sentAck)audioAckToken="";
    JsonObject feedback=reply["registration_feedback"].as<JsonObject>();
    String id=String(feedback["capture_id"] | "");
    if(!feedback.isNull() && String(feedback["state"] | "")=="consumed" && id.length() &&
       !feedbackInFlight.length() && !audioAckToken.length() && !feedback["acknowledged"].as<bool>()) {
      invalidateTransientAudio();
      if(queueSound(REGISTERED,id))feedbackInFlight=id;
    }
  }
  lastModePoll=millis();
  if (code==409) {
    readerStatus(SETUP_NEEDED);
    screen("PAIR FIRST","Open Scan RFID","Card/Tag on web page","Keep modal open"); return false;
  }
  if (code!=200 || !reply["capture_id"].is<const char*>() && !reply["capture_id"].isNull()) {
    readerStatus(code==401 || code==403 ? SETUP_NEEDED : SERVER_DOWN);
    screen(code==401 || code==403 ? "SETUP" : "OFFLINE",messageOf(reply),"Check HTTPS and Wi-Fi", "and reader credential");
    return false;
  }
  // The server returns a null capture_id outside the modal's waiting period.
  captureId=String(reply["capture_id"] | "");
  readerStatus(ONLINE);
  if(oldCapture!=captureId) {
    invalidateTransientAudio();
    if(captureId.length())queueSound(REGISTRATION_MODE);
    else if(!pendingEvent.length() && !feedbackInFlight.length() && !audioAckToken.length())queueSound(READY);
  }
  syncServerTime(reply);
  if (classifyingCard) return true;
  if (!greenUntil || captureId.length()) screen(captureId.length() ? "REGISTER" : "ATTENDANCE",
         captureId.length() ? "Tap card for web form" : "Tap your card",
         "Wi-Fi connected", "Barangay Sta. Clara");
  return true;
}

// Only the loop owns the display, RFID reader, and registration state.
TaskHandle_t modeTask=nullptr;
SemaphoreHandle_t modeDone=nullptr;
String modeAck;
JsonDocument modeReply;
int modeCode=0;
bool modeInFlight=false, discardModeReply=false;

void pollModeWorker(void*) {
  for (;;) {
    ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
    modeCode=requestMode(modeAck,modeReply);
    xSemaphoreGive(modeDone);
  }
}

bool refreshMode() {
  if (modeInFlight) discardModeReply=true;
  JsonDocument reply;
  String sentAck=audioAckToken;
  int code=requestMode(sentAck,reply);
  return applyMode(code,reply,sentAck);
}

void pollMode() {
  if (!modeTask) {
    if (!lastModePoll || millis()-lastModePoll>=MODE_POLL_MS) refreshMode();
    return;
  }
  if (modeInFlight && xSemaphoreTake(modeDone,0)==pdTRUE) {
    modeInFlight=false;
    if (!discardModeReply && WiFi.status()==WL_CONNECTED) applyMode(modeCode,modeReply,modeAck);
    modeReply.clear();
  }
  if (!modeInFlight && (!lastModePoll || millis()-lastModePoll>=MODE_POLL_MS)) {
    discardModeReply=false;
    modeAck=audioAckToken;
    modeInFlight=true;
    xTaskNotifyGive(modeTask);
  }
}

String uidString() {
  String uid;
  for (byte i=0;i<rfid.uid.size;i++) {
    if (rfid.uid.uidByte[i]<16) uid+='0';
    uid+=String(rfid.uid.uidByte[i],HEX);
  }
  uid.toUpperCase(); return uid;
}

String eventId() {
  char value[33];
  snprintf(value,sizeof(value),"%08lx%08lx%08lx%08lx",
    (unsigned long)esp_random(),(unsigned long)esp_random(),
    (unsigned long)esp_random(),(unsigned long)esp_random());
  return String(value);
}

String utcTimestamp() {
  time_t now=time(nullptr); struct tm value;
  gmtime_r(&now,&value);
  char result[25]; strftime(result,sizeof(result),"%Y-%m-%dT%H:%M:%SZ",&value);
  return String(result);
}

bool waitForButton(const String& name) {
  invalidateTransientAudio();
  queueSound(CONFIRM_IN);
  uint32_t started=millis();
  bool released=digitalRead(BUTTON_PIN)==HIGH;
  int previous=-1;
  while (millis()-started<CONFIRM_WINDOW_MS) {
    if (digitalRead(BUTTON_PIN)==HIGH) released=true;
    if (released && digitalRead(BUTTON_PIN)==LOW) {
      delay(30);
      if (digitalRead(BUTTON_PIN)==LOW && millis()-started<CONFIRM_WINDOW_MS) { invalidateTransientAudio(); return true; }
    }
    int left=(CONFIRM_WINDOW_MS-(millis()-started)+999)/1000;
    if (left!=previous) {
      previous=left;
      screen("TIME IN",name,"Press button: "+String(left)+"s","to confirm time in");
    }
    delay(10);
  }
  invalidateTransientAudio();
  return false;
}

void retryPending() {
  if (!pendingEvent.length()) return;
  lastRetry=millis();
  screen("SENDING","Checking server...","Do not tap again");
  JsonDocument reply;
  int code=postJson("/attendance/api/scan",pendingEvent,reply);
  if (code==200 && reply["success"].as<bool>()) {
    storage.remove("pending"); pendingEvent=""; pendingAnnounced=false;
    String action=String(reply["action"] | "");
    String name=String(reply["employee"] | "");
    String recorded=String(reply["time"] | "");
    screen(action=="IN" ? "TIME IN" : "TIME OUT",name,
      recorded.length()>=19 ? recorded.substring(11,19)+" PHT" : "Server confirmed",
      action=="IN" ? "Goodluck ngayong araw!" : "Ingat sa pag-uwi!");
    Serial.println(String("Accepted: ")+action+" "+recorded);
    digitalWrite(GREEN_LED,HIGH);
    invalidateTransientAudio();
    queueSound(action=="IN" ? TIME_IN_VOICE : TIME_OUT_VOICE);
    greenUntil=millis()+2500; lastModePoll=0;
  } else if (code>=400 && code<500 && code!=401 && code!=403 && code!=429 && code!=408) {
    storage.remove("pending"); pendingEvent=""; pendingAnnounced=false;
    failure(messageOf(reply),voiceForReply(reply)); lastModePoll=0;
  } else {
    // Delivery may already have succeeded. Never create a new ID for this tap.
    screen("PENDING",code==401 || code==403 ? "Check reader credential" : "Waiting for server",
           "Do not tap again", "Will retry same event");
    Serial.println(String("Pending attendance; HTTP ")+code);
    if(!pendingAnnounced)pendingAnnounced=queueSound(PENDING_VOICE);
  }
}

void handleCard(const String& uid) {
  invalidateTransientAudio();
  // Require a fresh server mode check before classifying every tap.
  if (!refreshMode()) return;
  JsonDocument request,reply;
  String body;
  if (captureId.length()) {
    request["capture_id"]=captureId; request["uid"]=uid;
    serializeJson(request,body);
    int code=postJson("/attendance/api/registration-tap",body,reply);
    if (code==200 && reply["success"].as<bool>()) {
      screen("CAPTURED","Card sent to web form","Click Register there","Not attendance yet");
      invalidateTransientAudio(); queueSound(CAPTURED);
    } else { failure(messageOf(reply),voiceForReply(reply)); }
    // No attendance event is created or queued for registration taps.
    lastModePoll=0; return;
  }
  request["uid"]=uid; serializeJson(request,body);
  int code=postJson("/attendance/api/preview",body,reply);
  String name=String(reply["employee"] | "");
  String action=String(reply["action"] | "");
  if (code!=200 || !reply["success"].as<bool>()) {
    failure(messageOf(reply),voiceForReply(reply));
    lastModePoll=0;return;
  }
  if (action!="IN" && action!="OUT") { failure("Invalid action from server"); return; }
  if (action=="IN" && !waitForButton(name)) { failure("Time in cancelled. Tap card again.",CANCELLED); lastModePoll=0; return; }
  // The server rechecks the registration reservation before accepting attendance.
  if (!clockReady()) { failure("Clock not synced. Check Wi-Fi and retry."); return; }
  request.clear(); body="";
  request["event_id"]=eventId(); request["uid"]=uid;
  request["action"]=action; request["occurred_at"]=utcTimestamp();
  serializeJson(request,body);
  if (storage.putString("pending",body)==0) { failure("Flash storage failed. Attendance not sent.",STORAGE_ERROR); return; }
  pendingEvent=body; pendingAnnounced=false;
  retryPending();
}

void setup() {
  Serial.begin(115200);
  delay(200);
  esp_reset_reason_t reason=esp_reset_reason();
  Serial.printf("\nRFID VOICE V6 | chip=%s | flash=%u bytes | reset reason=%d\n",
    ESP.getChipModel(),(unsigned)ESP.getFlashChipSize(),(int)reason);
  if(reason==ESP_RST_BROWNOUT)
    Serial.println("BROWNOUT: supply voltage dropped. Inspect shared 3.3V rail, USB cable and amplifier power.");
  pinMode(GREEN_LED,OUTPUT); pinMode(RED_LED,OUTPUT);
  pinMode(BUTTON_PIN,INPUT_PULLUP);
  digitalWrite(GREEN_LED,LOW); digitalWrite(RED_LED,LOW);
  if (!beginOLED()) {
    Serial.println("OLED unavailable. Check GND/VCC/SCL22/SDA21, 3.3V, address 0x3C/0x3D and controller model.");
    // Stop scans without repeatedly beeping when the display is disconnected.
    digitalWrite(RED_LED,HIGH);
    while (true) delay(1000);
  }
  if(!audioInit())Serial.println("MAX98357A audio initialization failed; inspect wiring/core/memory.");
  else {
    Serial.printf("I2S ready DIN33 BCLK32 LRC13; volume %d%%, cap %d%%. T=test, +/-=volume.\n",
      DEFAULT_AUDIO_VOLUME_PERCENT,MAX_AUDIO_VOLUME_PERCENT);
    // Do not replay the boot tone after a brownout, crash or watchdog reset.
    if(reason==ESP_RST_POWERON || reason==ESP_RST_EXT) queueSound(START_TONE);
  }
  SPI.begin(18,19,23,SS_PIN); rfid.PCD_Init();
  server=String(SERVER_URL); while(server.endsWith("/")) server.remove(server.length()-1);
  if (!*WIFI_SSID || !strchr(READER_CREDENTIAL, ':') || !*READER_ROOT_CA) {
    screen("CONFIGURE","Set reader secrets");
    Serial.println("Set Wi-Fi, device credential, and trusted CA in reader_secrets.h.");
    return;
  }
  if (!storage.begin("brgy-rfid-pub",false)) { failure("Cannot open flash storage",STORAGE_ERROR); return; }
  pendingEvent=storage.getString("pending","");
  setenv("TZ","UTC0",1); tzset();
  // Serial-only logging: Wi-Fi callbacks run on a separate task.
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event==ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
      Serial.printf("WiFi disconnected. Reason code: %u\n",info.wifi_sta_disconnected.reason);
    }
    if (event==ARDUINO_EVENT_WIFI_STA_GOT_IP) {
      Serial.print("WiFi connected! ESP32 IP: ");
      Serial.println(WiFi.localIP());
    }
  });
  WiFi.mode(WIFI_STA); WiFi.setAutoReconnect(true);
  Serial.print("Connecting to: "); Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  configTime(0,0,"time.google.com","pool.ntp.org");
  modeDone=xSemaphoreCreateBinary();
  if (modeDone && xTaskCreate(pollModeWorker,"rfid-mode",8192,nullptr,1,&modeTask)!=pdPASS) modeTask=nullptr;
  configured=true;
  screen("CONNECTING","Connecting to Wi-Fi");
}

void loop() {
  if (greenUntil && int32_t(millis()-greenUntil)>=0) {
    digitalWrite(GREEN_LED,LOW);
    greenUntil=0;
  }
  while(Serial.available()) {
    char command=(char)Serial.read();
    if(command=='t' || command=='T')Serial.println(queueSound(AUDIO_TEST) ? "Audio test queued." : "Audio unavailable or queue busy.");
    if(command=='+' || command=='-') {
      int volume=(int)audioVolumePercent+(command=='+' ? 5 : -5);
      audioVolumePercent=(uint8_t)constrain(volume,5,MAX_AUDIO_VOLUME_PERCENT);
      Serial.printf("Audio volume: %u%%\n",(unsigned)audioVolumePercent);
    }
  }
  AudioCompletion completed;
  while(completionQueue && xQueueReceive(completionQueue,&completed,0)==pdTRUE) {
    if(feedbackInFlight==String(completed.token))feedbackInFlight="";
    if(completed.success)audioAckToken=String(completed.token);
    lastModePoll=0;
  }
  if (!configured) { delay(100); return; }
  if (WiFi.status()!=WL_CONNECTED) {
    if(!wifiDownSince)wifiDownSince=millis();
    if(millis()-wifiDownSince>=5000)readerStatus(WIFI_DOWN);
    screen("NO WI-FI","Reconnecting...",pendingEvent.length() ? "Pending event retained" : "No new scans accepted");
    // Automatic reconnect owns retries; do not interrupt an in-progress attempt.
    delay(50); return;
  }
  wifiDownSince=0;
  if (pendingEvent.length()) {
    pollMode();
    if (!lastRetry || millis()-lastRetry>=RETRY_MS) retryPending();
    delay(20); return;
  }
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    pollMode();
    delay(5); return;
  }
  String uid=uidString(); rfid.PICC_HaltA(); rfid.PCD_StopCrypto1();
  Serial.println("RFID card detected");
  screen("CARD READ","Checking server...");
  classifyingCard=true;
  handleCard(uid);
  classifyingCard=false;
  lastModePoll=0;
}
