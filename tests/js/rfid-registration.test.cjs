// Exercise the actual UI controller against a small DOM/API test double.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../../app/static/js/rfid-registration.js'),'utf8');

class Element {
  constructor() {
    this.value='';this.hidden=false;this.disabled=false;this.required=false;this.checked=false;
    this.textContent='';this.dataset={};this.listeners={};this.open=false;this.attributes={};
    const classes=new Set();
    this.classList={add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle:(c,on)=>on?classes.add(c):classes.delete(c)};
  }
  addEventListener(event,listener) { (this.listeners[event] ||= []).push(listener); }
  async fire(event) { for(const listener of this.listeners[event] || []) await listener({preventDefault(){}}); }
  showModal() { this.open=true; }
  close() { this.open=false;this.fire('close'); }
  focus() {}
  setAttribute(name,value) { this.attributes[name]=value; }
  removeAttribute(name) { delete this.attributes[name]; }
  getAttribute(name) { return this.attributes[name] ?? null; }
}

function setup(retainedToken = '') {
  const ids=['rfidRegistrationForm','rfidScanDialog','rfidScanTitle','rfidScanSymbol','rfidScanStatus','rfidAttachedStatus','rfidCaptureId','rfidSaveButton','rfidScanButton','rfidScanDone','rfidScanAgain','rfidScanCancel','rfidOtherRole','rfidAccountPicker','rfidUserAccount','rfidReactivation','rfidReactivateCheck','rfidReactivationId','rfidReactivationName','rfidReactivationLink','rfidSavedAssignment','rfidSavedAssignmentText','rfidSavedAssignmentLink'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));
  ['rfidReaderLabel','rfidScanHint','rfidStepConnect','rfidStepScan','rfidStepConfirm'].forEach(id=>elements[id]=new Element());
  const form=elements.rfidRegistrationForm;
  form.dataset.startUrl='/attendance/registration/start';
  form.elements=Object.fromEntries(['first_name','last_name','email','barangay_role','other_role','csrf_token'].map(name=>[name,new Element()]));
  form.elements.first_name.value='Juan';form.elements.last_name.value='Dela Cruz';
  form.elements.barangay_role.options=[{value:''},{value:'Barangay Staff'},{value:'Others'}];
  elements.rfidCaptureId.value=retainedToken;
  elements.rfidSaveButton.disabled=!retainedToken;
  elements.rfidSavedAssignment.hidden=true;
  const existing=new Element(),none=new Element();existing.value='existing';none.value='none';none.checked=true;
  const choices=[existing,none].map(input=>Object.assign(new Element(),{querySelector:()=>input}));
  form.querySelector=()=>existing.checked?existing:none;
  form.querySelectorAll=selector=>selector==='.rfid-account-option'?choices:[existing,none];
  let timerId=0,counter=0;
  const timers=new Map(),calls=[];
  const remote={state:'waiting',suffix:'11223344'};
  const context={document:{getElementById:id=>elements[id]},window:{addEventListener(){}},
    setTimeout:callback=>{timers.set(++timerId,callback);return timerId;},clearTimeout:id=>timers.delete(id),
    fetch:async(url,options)=>{
      calls.push({url,options});
      if(url.endsWith('/cancel')) return {ok:true,json:async()=>({success:true})};
      if(url.endsWith('/start')) {counter++;return {ok:true,json:async()=>({capture_id:'token-'+counter})};}
      return {ok:true,json:async()=>({...remote,ready:true})};
    }};
  vm.runInNewContext(source,context);
  const settle=async()=>{for(let i=0;i<5;i++) await new Promise(resolve=>setImmediate(resolve));};
  async function detect() {
    await elements.rfidScanButton.fire('click');await settle();
    assert.equal(elements.rfidScanDialog.open,true);
    assert.match(elements.rfidScanStatus.textContent,/Waiting for card/);
    assert.equal(elements.rfidScanDialog.dataset.reader,'ready');
    assert.equal(elements.rfidReaderLabel.textContent,'Reader ready');
    assert.equal(elements.rfidStepScan.getAttribute('aria-current'),'step');
    remote.state='captured';
    const next=timers.entries().next().value;timers.delete(next[0]);
    await next[1]();await settle();
  }
  return {elements,existing,none,choices,remote,calls,settle,detect};
}

test('a detected card requires Use this card before Save is enabled',async()=>{
  const app=setup(),e=app.elements;await app.detect();
  assert.match(e.rfidScanTitle.textContent,/confirm/);
  assert.match(e.rfidScanStatus.textContent,/Juan Dela Cruz/);
  assert.equal(e.rfidScanDialog.dataset.reader,'captured');
  assert.equal(e.rfidReaderLabel.textContent,'Card detected');
  assert.equal(e.rfidStepConfirm.getAttribute('aria-current'),'step');
  assert.equal(e.rfidStepScan.getAttribute('aria-current'),null);
  assert.equal(e.rfidScanDone.hidden,false);
  assert.equal(e.rfidCaptureId.value,'');assert.equal(e.rfidSaveButton.disabled,true);
  await e.rfidScanDone.fire('click');
  assert.equal(e.rfidCaptureId.value,'token-1');assert.equal(e.rfidSaveButton.disabled,false);
  assert.equal(e.rfidScanDialog.open,false);assert.match(e.rfidAttachedStatus.textContent,/Not saved yet/);
  assert.equal(app.calls.some(call=>call.url==='/attendance/devices'),false);
});

test('cancelling detection discards the pending card',async()=>{
  const app=setup(),e=app.elements;await app.detect();
  await e.rfidScanCancel.fire('click');await app.settle();
  assert.equal(e.rfidCaptureId.value,'');assert.equal(e.rfidSaveButton.disabled,true);
  assert.equal(e.rfidScanDialog.open,false);
  assert.equal(app.calls.some(call=>call.url.endsWith('/token-1/cancel')),true);
});

test('Scan again cancels the old capture and waits for a new tap',async()=>{
  const app=setup(),e=app.elements;await app.detect();
  app.remote.state='waiting';await e.rfidScanAgain.fire('click');await app.settle();
  assert.equal(e.rfidScanDialog.dataset.stage,'waiting');assert.equal(e.rfidScanDone.hidden,true);
  assert.equal(e.rfidCaptureId.value,'');assert.equal(e.rfidSaveButton.disabled,true);
  const cancelled=app.calls.findIndex(call=>call.url.endsWith('/token-1/cancel'));
  const starts=app.calls.map((call,i)=>call.url.endsWith('/start')?i:-1).filter(i=>i>=0);
  assert.ok(cancelled<starts[1]);
});

test('an expired detection cannot be confirmed',async()=>{
  const app=setup(),e=app.elements;await app.detect();app.remote.state='expired';
  await e.rfidScanDone.fire('click');
  assert.equal(e.rfidCaptureId.value,'');assert.equal(e.rfidSaveButton.disabled,true);
  assert.equal(e.rfidScanDialog.dataset.stage,'error');assert.match(e.rfidScanStatus.textContent,/expired/);
  assert.equal(e.rfidReaderLabel.textContent,'Needs attention');
  assert.equal(e.rfidStepConfirm.getAttribute('aria-current'),null);
});

test('account cards show the selected choice and toggle the account picker',async()=>{
  const app=setup(),e=app.elements;
  assert.equal(app.choices[1].classList.contains('is-selected'),true);
  assert.equal(e.rfidAccountPicker.hidden,true);assert.equal(e.rfidUserAccount.disabled,true);
  app.none.checked=false;app.existing.checked=true;await app.existing.fire('change');
  assert.equal(app.choices[0].classList.contains('is-selected'),true);
  assert.equal(app.choices[1].classList.contains('is-selected'),false);
  assert.equal(e.rfidAccountPicker.hidden,false);assert.equal(e.rfidUserAccount.required,true);
});

test('an inactive linked profile requires explicit reactivation and resets consent for another account',async()=>{
  const app=setup(),e=app.elements;
  app.none.checked=false;app.existing.checked=true;
  e.rfidUserAccount.selectedOptions=[{value:'20',dataset:{personnelId:'44',personnelActive:'no',personnelName:'Juan Dela Cruz',personnelUrl:'/attendance/personnel/44',firstName:'Juan',lastName:'Dela Cruz',position:'Barangay Staff'}}];
  await e.rfidUserAccount.fire('change');
  assert.equal(e.rfidReactivation.hidden,false);assert.equal(e.rfidReactivateCheck.required,true);
  assert.equal(e.rfidReactivateCheck.checked,false);assert.equal(e.rfidReactivationId.value,'44');
  e.rfidReactivateCheck.checked=true;
  e.rfidUserAccount.selectedOptions=[{value:'21',dataset:{personnelId:'45',personnelActive:'no',personnelName:'Another Person'}}];
  await e.rfidUserAccount.fire('change');
  assert.equal(e.rfidReactivationId.value,'45');assert.equal(e.rfidReactivateCheck.checked,false);
  app.none.checked=true;app.existing.checked=false;await app.none.fire('change');
  assert.equal(e.rfidReactivation.hidden,true);assert.equal(e.rfidReactivateCheck.disabled,true);
});

test('a confirmed card retained after validation stays usable and is cancelled before a rescan',async()=>{
  const app=setup('retained-token'),e=app.elements;
  assert.equal(e.rfidCaptureId.value,'retained-token');assert.equal(e.rfidSaveButton.disabled,false);
  await e.rfidScanButton.fire('click');await app.settle();
  assert.equal(app.calls[0].url,'/attendance/registration/retained-token/cancel');
  assert.equal(app.calls[1].url,'/attendance/registration/start');
  assert.equal(e.rfidCaptureId.value,'');assert.equal(e.rfidSaveButton.disabled,true);
});

test('selecting an already registered user shows the saved card and blocks another registration',async()=>{
  const app=setup(),e=app.elements;
  app.none.checked=false;app.existing.checked=true;
  e.rfidUserAccount.selectedOptions=[{value:'20',dataset:{firstName:'Juan',lastName:'Dela Cruz',personnelId:'44',personnelActive:'yes',personnelName:'Juan Dela Cruz',personnelUrl:'/attendance/personnel/44',rfidRegistered:'yes',rfidSuffix:'AABBCCDD',rfidActive:'yes'}}];
  await e.rfidUserAccount.fire('change');
  assert.equal(e.rfidSavedAssignment.hidden,false);
  assert.match(e.rfidSavedAssignmentText.textContent,/AABBCCDD/);
  assert.equal(e.rfidSaveButton.disabled,true);assert.equal(e.rfidScanButton.disabled,true);
  await e.rfidScanButton.fire('click');
  assert.equal(app.calls.length,0);
  app.none.checked=true;app.existing.checked=false;await app.none.fire('change');
  assert.equal(e.rfidSavedAssignment.hidden,true);assert.equal(e.rfidScanButton.disabled,false);
});
