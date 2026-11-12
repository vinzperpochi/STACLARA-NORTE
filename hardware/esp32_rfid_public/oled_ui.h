#pragma once
#include <Arduino.h>
#include <Adafruit_SSD1306.h>
#include <vector>

// 128x64 monochrome civic theme: 4px margins, shared masthead and status footer.
// Layout only; this module never sends an attendance event or queues audio.
namespace CivicOLED {
enum Icon { CARD, CHECK, CLOCK, ALERT, NETWORK, SEND };

inline String ascii(String text) {
  String result;
  for(size_t i=0;i<text.length();i++) {
    uint8_t c=text[i];
    if(c>=32 && c<=126)result+=(char)c;
    else if(c=='\n' || c=='\r' || c=='\t')result+=' ';
    else if(c>=0xC0)result+='?'; // Classic GFX font cannot display UTF-8 glyphs.
  }
  result.trim();return result;
}
inline String fit(String text,uint8_t columns) {
  text=ascii(text);
  return text.length()>columns ? text.substring(0,columns-3)+"..." : text;
}
inline std::vector<String> wrap(String text,uint8_t columns) {
  text=ascii(text);
  std::vector<String> rows;
  while(text.length()) {
    if(text.length()<=columns) {rows.push_back(text);break;}
    int cut=text.lastIndexOf(' ',columns);
    if(cut<1)cut=columns;
    rows.push_back(text.substring(0,cut));
    text=text.substring(cut);text.trim();
  }
  if(rows.empty())rows.push_back("");
  return rows;
}
inline void text(Adafruit_SSD1306& d,int x,int y,const String& value,uint8_t size=1) {
  d.setTextSize(size);d.setTextColor(SSD1306_WHITE);d.setCursor(x,y);d.print(value);
}
inline void centered(Adafruit_SSD1306& d,int y,const String& value) {
  String line=fit(value,20);
  text(d,(128-line.length()*6)/2,y,line);
}
inline void masthead(Adafruit_SSD1306& d,bool connected,int rssi,const String& label="STA.CLARA NORTE") {
  d.clearDisplay();d.setFont(nullptr);d.setTextWrap(false);
  // Civic shield mark, rendered as pixels rather than an unreadable tiny seal.
  d.drawLine(4,1,12,1,SSD1306_WHITE);d.drawLine(4,1,4,6,SSD1306_WHITE);
  d.drawLine(12,1,12,6,SSD1306_WHITE);d.drawLine(4,6,8,9,SSD1306_WHITE);d.drawLine(12,6,8,9,SSD1306_WHITE);
  d.drawLine(6,4,8,6,SSD1306_WHITE);d.drawLine(8,6,11,3,SSD1306_WHITE);
  text(d,17,2,fit(label,15));
  if(connected) {
    int bars=rssi>=-60 ? 3 : (rssi>=-75 ? 2 : 1);
    for(int i=0;i<3;i++) {
      int height=3+i*3;
      if(i<bars)d.fillRect(115+i*4,10-height,2,height,SSD1306_WHITE);
      else d.drawPixel(115+i*4,9,SSD1306_WHITE);
    }
  } else {
    d.drawLine(116,3,122,9,SSD1306_WHITE);d.drawLine(122,3,116,9,SSD1306_WHITE);
  }
  d.drawFastHLine(4,12,120,SSD1306_WHITE);
}
inline void footer(Adafruit_SSD1306& d,const String& value) {
  d.drawFastHLine(4,53,120,SSD1306_WHITE);centered(d,56,value);
}
inline void icon(Adafruit_SSD1306& d,Icon kind) {
  if(kind==CARD) {
    d.drawRoundRect(5,20,18,23,3,SSD1306_WHITE);
    d.drawRoundRect(9,25,6,6,1,SSD1306_WHITE);
    d.drawFastHLine(9,36,10,SSD1306_WHITE);
  } else if(kind==CHECK) {
    d.drawCircle(14,30,10,SSD1306_WHITE);
    d.drawLine(8,30,12,34,SSD1306_WHITE);d.drawLine(12,34,20,25,SSD1306_WHITE);
  } else if(kind==CLOCK) {
    d.drawCircle(14,30,10,SSD1306_WHITE);
    d.drawLine(14,23,14,30,SSD1306_WHITE);d.drawLine(14,30,19,33,SSD1306_WHITE);
  } else if(kind==ALERT) {
    d.drawTriangle(4,41,14,21,24,41,SSD1306_WHITE);
    d.drawFastVLine(14,28,7,SSD1306_WHITE);d.drawPixel(14,38,SSD1306_WHITE);
  } else if(kind==NETWORK) {
    d.drawRoundRect(5,24,18,13,2,SSD1306_WHITE);
    d.drawLine(14,24,14,19,SSD1306_WHITE);d.drawCircle(14,18,1,SSD1306_WHITE);
    d.drawPixel(9,33,SSD1306_WHITE);d.drawPixel(13,33,SSD1306_WHITE);
  } else {
    d.drawRoundRect(4,24,15,15,2,SSD1306_WHITE);
    d.drawLine(10,31,24,31,SSD1306_WHITE);d.drawLine(20,27,24,31,SSD1306_WHITE);d.drawLine(20,35,24,31,SSD1306_WHITE);
  }
}
inline void render(Adafruit_SSD1306& d,const String& title,const String& a,
                   const String& b,const String& c,bool connected,int rssi) {
  masthead(d,connected,rssi);
  if(title=="ATTENDANCE") {
    icon(d,CARD);text(d,37,18,"READY",2);text(d,36,39,"Tap card or tag");
    footer(d,"ATTENDANCE | ONLINE");
  } else if(title=="TIME IN" && b.startsWith("Press button: ")) {
    int seconds=constrain(b.substring(14).toInt(),0,10);
    text(d,4,17,"CONFIRM TIME IN");text(d,4,28,fit(a,20));
    text(d,4,40,"PRESS BUTTON");
    d.drawRoundRect(96,36,28,14,3,SSD1306_WHITE);
    String secondsLabel=String(seconds)+"s";
    text(d,96+(28-secondsLabel.length()*6)/2,39,secondsLabel);
    d.drawRect(4,49,88,3,SSD1306_WHITE);
    if(seconds>0)d.drawFastHLine(5,50,(86*seconds)/10,SSD1306_WHITE);
    footer(d,"Confirm within 10s");
  } else if(title=="ERROR") {
    d.drawTriangle(4,23,9,15,14,23,SSD1306_WHITE);d.drawPixel(9,20,SSD1306_WHITE);
    text(d,20,16,"PLEASE CHECK");
    auto lines=wrap(a+" "+b+" "+c,20);
    for(size_t i=0;i<lines.size() && i<3;i++)
      text(d,4,26+i*9,(i==2 && lines.size()>3) ? fit(lines[i]+"...",20) : lines[i]);
    footer(d,"Tap again when ready");
  } else {
    String heading=title,foot=c,detail1=a,detail2=b;
    Icon mark=CARD;
    if(title=="CONNECTING"){heading="CONNECT";mark=NETWORK;detail1="Joining network";detail2="Please wait";foot="Joining Wi-Fi";}
    else if(title=="NO WI-FI"){
      heading="NO WI-FI";mark=NETWORK;detail1="Reconnecting...";
      detail2=b.indexOf("Pending")>=0 ? "Pending retained" : "Scans on hold";foot="Please wait";
    }
    else if(title=="OFFLINE"){mark=NETWORK;detail1="Server offline";detail2="Check connection";foot="Check server / Wi-Fi";}
    else if(title=="PAIR FIRST" || title=="SETUP" || title=="CONFIGURE"){
      heading="SETUP";mark=ALERT;foot=title=="PAIR FIRST" ? "Open web RFID scan" : "Contact admin";
      detail1=title=="PAIR FIRST" ? "Pair your reader" : "Setup required";
      detail2=title=="PAIR FIRST" ? "Keep popup open" : "Contact admin";
    }
    else if(title=="PENDING"){
      mark=CLOCK;detail1=a.indexOf("local test")>=0 ? "Check setup" : "Awaiting server";
      detail2=a.indexOf("local test")>=0 ? "Contact admin" : "Retrying safely";foot="Do not tap again";
    }
    else if(title=="SENDING"){mark=SEND;detail1="Sending record";detail2="Please wait";foot="Saving attendance";}
    else if(title=="REGISTER"){mark=CARD;detail1="Tap card or tag";detail2="New registration";foot="CARD REGISTRATION";}
    else if(title=="CAPTURED"){mark=CARD;detail1="Card detected";detail2="Not saved yet";foot="Save on web form";}
    else if(title=="TIME IN" || title=="TIME OUT"){
      mark=CHECK;foot=title=="TIME IN" ? "Magandang araw!" : "Ingat sa pag-uwi!";
    }
    icon(d,mark);
    text(d,29,17,fit(heading,8),2);
    text(d,29,35,fit(detail1,16));text(d,29,44,fit(detail2,16));
    footer(d,foot);
  }
  d.display();
}
inline void owner(Adafruit_SSD1306& d,const std::vector<String>& rows,size_t page,
                  size_t pageCount,const String& nextAction) {
  masthead(d,false,0,"CARD OWNER");
  // Replace connection mark with a page indicator; this is an identity preview.
  d.fillRect(108,0,20,12,SSD1306_BLACK);
  text(d,108,2,fit(String(page+1)+"/"+String(pageCount),3));
  for(size_t i=0;i<4;i++) {
    size_t index=page*4+i;
    if(index<rows.size())text(d,4,17+i*9,rows[index]);
  }
  footer(d,nextAction=="IN" ? "NEXT: TIME IN" : (nextAction=="OUT" ? "NEXT: TIME OUT" : "Saved card owner"));
  d.display();
}
} // namespace CivicOLED
