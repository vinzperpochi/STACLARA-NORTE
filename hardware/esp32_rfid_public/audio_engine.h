#pragma once
#include <Arduino.h>
#include <driver/i2s.h>
#include <Preferences.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#include <atomic>
#include <math.h>
#include "audio_clips.h"

// Digital volume does not establish the electrical capacity of the 3.3V rail.
constexpr int DEFAULT_AUDIO_VOLUME_PERCENT=20;
constexpr int MAX_AUDIO_VOLUME_PERCENT=35;
static std::atomic<uint8_t> audioVolumePercent{DEFAULT_AUDIO_VOLUME_PERCENT};
struct SoundRequest { SoundKind kind; char token[64]; uint32_t epoch,expires; bool transient; };
struct AudioCompletion { char token[64]; bool success; };
static QueueHandle_t soundQueue=nullptr,statusQueue=nullptr,completionQueue=nullptr;
static bool audioAvailable=false;
static std::atomic<uint32_t> audioEpoch{0};
static SoundRequest playing={}; // Only the worker reads/writes this object.
static uint32_t lastVoiceAt[VOICE_CLIP_COUNT]={};
static bool voiceWasQueued[VOICE_CLIP_COUNT]={};

static void invalidateTransientAudio() { audioEpoch.fetch_add(1); }
static bool audioCurrent() {
  return !playing.transient || (playing.epoch==audioEpoch.load() && uxQueueMessagesWaiting(soundQueue)==0);
}

static bool writeSamples(const int16_t* mono,size_t count) {
  int16_t stereo[256];
  for(size_t offset=0;offset<count;offset+=128) {
    if(!audioCurrent())return false;
    size_t n=min((size_t)128,count-offset);
    int volume=audioVolumePercent.load();
    for(size_t i=0;i<n;i++) {
      int16_t value=(int16_t)((int32_t)mono[offset+i]*volume/100);
      stereo[i*2]=value;stereo[i*2+1]=value;
    }
    size_t written=0;
    if(i2s_write(I2S_NUM_0,stereo,n*4,&written,portMAX_DELAY)!=ESP_OK || written!=n*4)return false;
  }
  return true;
}
static bool audioTone(float hz,uint32_t ms) {
  int16_t samples[128];
  size_t total=(AUDIO_RATE*ms)/1000;
  for(size_t offset=0;offset<total;offset+=128) {
    size_t n=min((size_t)128,total-offset);
    for(size_t i=0;i<n;i++)samples[i]=hz>0 ? (int16_t)(10000.0f*sinf(2.0f*PI*hz*(offset+i)/AUDIO_RATE)) : 0;
    if(!writeSamples(samples,n))return false;
  }
  return true;
}
static bool playSound(SoundKind kind) {
  if((uint8_t)kind<VOICE_CLIP_COUNT) {
    const VoiceClip& clip=VOICE_CLIPS[(uint8_t)kind];
    int16_t decoded[128];
    for(size_t offset=0;offset<clip.count;offset+=128) {
      size_t n=min((size_t)128,clip.count-offset);
      for(size_t i=0;i<n;i++)decoded[i]=((int)pgm_read_byte(clip.samples+offset+i)-128)*256;
      if(!writeSamples(decoded,n))return false;
    }
    return audioTone(0,120);
  }
  switch(kind) {
    case START_TONE:return audioTone(1200,80)&&audioTone(1800,100);
    case TAP_TONE:return audioTone(2400,55);
    case CAPTURE_TONE:return audioTone(1400,80)&&audioTone(1900,80);
    case WARNING_TONE:return audioTone(700,90)&&audioTone(0,70)&&audioTone(700,90);
    default:return audioTone(500,180)&&audioTone(0,80)&&audioTone(300,220);
  }
}
static void audioWorker(void*) {
  Preferences audioStorage;
  bool persistent=audioStorage.begin("brgy-audio",false);
  if(!persistent)Serial.println("Audio dedup storage unavailable; check ESP32 flash.");
  while(true) {
    SoundRequest request;
    // Results are FIFO and protected from transient status replacement.
    if(xQueueReceive(soundQueue,&request,0)!=pdTRUE &&
       xQueueReceive(statusQueue,&request,pdMS_TO_TICKS(20))!=pdTRUE)continue;
    if(request.transient && (request.epoch!=audioEpoch.load() || (int32_t)(millis()-request.expires)>0))continue;
    playing=request;
    bool done=request.token[0] && persistent && audioStorage.getString("reg_done","")==String(request.token);
    if(!done)done=playSound(request.kind);
    if(!done)i2s_zero_dma_buffer(I2S_NUM_0);
    if(request.token[0]) {
      if(done && persistent)audioStorage.putString("reg_done",request.token);
      AudioCompletion result={};strlcpy(result.token,request.token,sizeof(result.token));result.success=done;
      xQueueSend(completionQueue,&result,portMAX_DELAY);
    }
  }
}
static bool audioInit() {
  i2s_config_t config={};
  config.mode=(i2s_mode_t)(I2S_MODE_MASTER|I2S_MODE_TX);
  config.sample_rate=AUDIO_RATE;config.bits_per_sample=I2S_BITS_PER_SAMPLE_16BIT;
  config.channel_format=I2S_CHANNEL_FMT_RIGHT_LEFT;
  config.communication_format=I2S_COMM_FORMAT_STAND_I2S;
  config.dma_buf_count=6;config.dma_buf_len=256;config.tx_desc_auto_clear=true;
  i2s_pin_config_t pins={};pins.mck_io_num=I2S_PIN_NO_CHANGE;
  pins.bck_io_num=32;pins.ws_io_num=13;pins.data_out_num=33;pins.data_in_num=I2S_PIN_NO_CHANGE;
  if(i2s_driver_install(I2S_NUM_0,&config,0,nullptr)!=ESP_OK)return false;
  if(i2s_set_pin(I2S_NUM_0,&pins)!=ESP_OK){i2s_driver_uninstall(I2S_NUM_0);return false;}
  soundQueue=xQueueCreate(8,sizeof(SoundRequest));
  statusQueue=xQueueCreate(1,sizeof(SoundRequest));
  completionQueue=xQueueCreate(2,sizeof(AudioCompletion));
  if(!soundQueue || !statusQueue || !completionQueue)return false;
  audioAvailable=xTaskCreate(audioWorker,"rfid-audio",4096,nullptr,1,nullptr)==pdPASS;
  return audioAvailable;
}
static bool queueSound(SoundKind kind,const String& token="") {
  if(!audioAvailable || token.length()>=64)return false;
  bool finalResult=token.length() || kind==TIME_IN_VOICE || kind==TIME_OUT_VOICE;
  uint32_t now=millis();
  if(!finalResult && (uint8_t)kind<VOICE_CLIP_COUNT && kind!=CONFIRM_IN && kind!=AUDIO_TEST &&
     voiceWasQueued[kind] && now-lastVoiceAt[kind]<10000)return false;
  SoundRequest request={};request.kind=kind;request.transient=!finalResult;
  strlcpy(request.token,token.c_str(),sizeof(request.token));
  request.expires=now+8000;
  if(finalResult) {
    if(xQueueSend(soundQueue,&request,0)!=pdTRUE) { Serial.println("Final audio queue full."); return false; }
  } else {
    request.epoch=audioEpoch.fetch_add(1)+1;
    if(xQueueOverwrite(statusQueue,&request)!=pdTRUE)return false;
  }
  if((uint8_t)kind<VOICE_CLIP_COUNT){lastVoiceAt[kind]=now;voiceWasQueued[kind]=true;}
  return true;
}
