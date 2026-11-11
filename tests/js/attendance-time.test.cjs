const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../../app/static/js/portal.js'),'utf8');

function format(elements) {
  const context={
    document:{querySelector:()=>null,querySelectorAll:selector=>selector==='time[datetime]'?elements:[],addEventListener(){}},
    window:{addEventListener(){}},Date,Intl,setTimeout,clearTimeout
  };
  vm.runInNewContext(source,context);
  return elements.map(el=>el.textContent.replace(/\s+/g,' ').trim());
}

function time(iso,mode='time') {
  return {getAttribute:name=>name==='datetime'?iso:null,dataset:{fmt:mode},textContent:''};
}

test('8:07/8:08 AM Philippine scans stay in the morning after portal formatting',()=>{
  const values=[time('2026-11-05T00:07:00+00:00'),time('2026-11-05T00:08:00+00:00')];
  assert.deepEqual(format(values),['8:07 AM','8:08 AM']);
  assert.deepEqual(format(values),['8:07 AM','8:08 AM']);
});

test('UTC and explicit Philippine offsets represent the same attendance time',()=>{
  assert.deepEqual(format([time('2026-11-05T00:07:00Z'),time('2026-11-05T08:07:00+08:00')]),['8:07 AM','8:07 AM']);
});

test('overnight clocks and legacy naive UTC timestamps retain their intended semantics',()=>{
  assert.deepEqual(format([time('2026-11-04T15:58:00+00:00'),time('2026-11-04T22:05:00+00:00'),time('2026-11-05T00:07:00')]),['11:58 PM','6:05 AM','8:07 AM']);
});
