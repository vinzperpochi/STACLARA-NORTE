const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = {window:{}, document:{readyState:'loading',body:{dataset:{timezone:'Asia/Manila'}},addEventListener(){}},Intl,Date};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../app/static/js/client-validation.js'),'utf8'),context);
const {message,patternMatches} = context.window.CivicValidationRules;

function field(options={}) {
  const item = {type:'text',name:'test',value:'',dataset:{},validity:{},required:false,min:'',max:'',
    getAttribute(name){ return Object.hasOwn(this.attrs || {},name) ? String(this.attrs[name]) : null; },
    hasAttribute(name){ return Object.hasOwn(this.attrs || {},name); },...options};
  return item;
}
function form(...fields) { fields.forEach(item=>item.form={elements:fields}); }

test('required text rejects whitespace while zero is a valid numeric value',()=>{
  assert.match(message(field({value:'  ',required:true})),/required/);
  assert.equal(message(field({value:'0',type:'number',min:'0',required:true})),'');
  assert.equal(message(field()),'');
});
test('consent checks actual checked state, not the checkbox value',()=>{
  assert.match(message(field({type:'checkbox',value:'on',required:true,checked:false})),/check this box/);
  assert.equal(message(field({type:'checkbox',value:'on',required:true,checked:true})), '');
});
test('a required radio group accepts another checked option',()=>{
  const a=field({name:'role',type:'radio',required:true,checked:false}), b=field({name:'role',type:'radio',checked:true});
  form(a,b);assert.equal(message(a),'');
});
test('email and phone formats support local mobile, international mobile, and landline',()=>{
  assert.match(message(field({type:'email',value:'invalid'})),/email/);
  assert.equal(message(field({type:'email',value:'person+tag@example.com'})), '');
  for (const value of ['09171234567','+639171234567','(049) 559-0123']) {
    const input=field({type:'tel',value});assert.equal(message(input),'');assert.equal(input.value,value);
  }
  assert.match(message(field({type:'tel',value:'letters123'})),/phone/);
});
test('person names accept Filipino diacritics and reject digits/markup',()=>{
  for (const value of ['Peña','Dela Cruz','José Niño']) assert.equal(message(field({value,dataset:{validateName:'true'}})), '');
  for (const value of ['Name123','<b>Juan</b>']) assert.match(message(field({value,dataset:{validateName:'true'}})),/letters/);
});
test('emergency short codes stay valid without allowing letters in hotline fields',()=>{
  const input=field({type:'tel',value:'911',dataset:{phoneFormat:'hotline'},pattern:'\\+?[0-9 \\(\\)\\-]{3,30}'});
  assert.equal(message(input),'');input.value='bad';assert.match(message(input),/format/);
});
test('minimum and maximum lengths apply to manually entered values',()=>{
  assert.match(message(field({value:'abc',attrs:{minlength:4}})),/at least 4/);
  assert.match(message(field({value:'abcdef',attrs:{maxlength:5}})),/no more than 5/);
});
test('existing/login passwords have no invented new-password restriction',()=>{
  assert.equal(message(field({type:'password',name:'password',value:'x',required:true})), '');
  assert.match(message(field({type:'password',value:'alllowercase123',dataset:{passwordPolicy:'complex'}})),/uppercase/);
  assert.equal(message(field({type:'password',value:'A valid passphrase 123!',dataset:{passwordPolicy:'complex'}})), '');
});
test('confirmation is validated within its own form and cannot be blank',()=>{
  const password=field({name:'password',value:'Secret123!'}), confirmation=field({name:'confirm_password',value:''});
  form(password,confirmation);assert.match(message(confirmation),/match/);
  confirmation.value=password.value;assert.equal(message(confirmation),'');
});
test('number limits and browser step mismatch prevent invalid amounts',()=>{
  assert.match(message(field({type:'number',value:'-1',min:'0'})),/at least 0/);
  assert.match(message(field({type:'number',value:'101',max:'100'})),/no greater than 100/);
  assert.match(message(field({type:'number',value:'NaN'})),/valid number/);
  assert.match(message(field({type:'number',value:'1.5',validity:{stepMismatch:true}})),/increment/);
});
test('date boundaries and reversed date ranges are checked without rejecting overnight shifts',()=>{
  assert.match(message(field({type:'date',value:'2026-02-01',max:'2026-01-01'})),/on or before/);
  const start=field({name:'start_date',type:'date',value:'2026-11-07'}), end=field({name:'end_date',type:'date',value:'2026-11-06',dataset:{notBefore:'start_date'}});
  form(start,end);assert.match(message(end),/on or after/);
  assert.equal(message(field({type:'time',name:'end_time',value:'06:00'})), '');
});
test('cross-field emergency contact requires its partner only when provided',()=>{
  const name=field({name:'emergency_contact_name',value:'Juan'}), number=field({name:'emergency_contact_number',dataset:{requiredWith:'emergency_contact_name'}});
  form(name,number);assert.match(message(number),/required/);
  name.value='';assert.equal(message(number),'');
});
test('file type, zero bytes, MIME mismatch and maximum size are checked before upload',()=>{
  const upload = (file,more={})=>message(field({type:'file',files:[file],accept:'image/jpeg,image/png',...more}));
  assert.equal(upload({name:'portrait.png',type:'image/png',size:100}),'');
  assert.match(upload({name:'fake.exe',type:'application/octet-stream',size:100}),/allowed file type/);
  assert.match(upload({name:'portrait.png',type:'image/png',size:0}),/nonempty/);
  assert.match(upload({name:'portrait.png',type:'image/png',size:5*1024*1024+1}),/5 MB/);
  assert.match(upload({name:'portrait.png',type:'image/jpeg',size:100}),/do not match/);
  assert.equal(upload({name:'document.pdf',type:'application/pdf',size:100},{accept:'application/pdf'}),'');
});
test('selected correction fields validate their corresponding data type',()=>{
  const selected=field({name:'field_name',value:'email'}), proposed=field({name:'proposed_value',value:'invalid',dataset:{correctionValue:'true',correctionDateMin:'1970-01-01',correctionDateMax:'2016-01-01'}});
  form(selected,proposed);assert.match(message(proposed),/email/);
  selected.value='birth_date';proposed.value='2000-02-30';assert.match(message(proposed),/valid date/);
  proposed.value='2000-02-29';assert.equal(message(proposed),'');
});
test('external image/crop validators retain their own error messages',()=>{
  assert.equal(message(field({value:'value',validity:{customError:true},validationMessage:'Existing crop validation.'})),'Existing crop validation.');
  assert.equal(message(field({type:'file',files:[{name:'image.png',type:'image/png',size:100}],validity:{customError:true},validationMessage:'Image could not be decoded.'})),'Image could not be decoded.');
});
test('required fields in collapsed details are still validated and revealed for focus',()=>{
  const detail={open:false};let focused=false;
  const input=field({form:{},name:'reason',required:true,getClientRects:()=>[],matches:()=>false,
    closest:selector=>selector.startsWith('details') ? detail : null,focus:()=>{focused=true;},scrollIntoView(){}});
  assert.equal(Boolean(context.window.civicValidation.eligible(input)),true);
  context.window.civicValidation.focus(input);assert.equal(detail.open,true);assert.equal(focused,true);
});
test('malformed legacy HTML patterns do not crash validation on other fields',()=>{
  assert.equal(patternMatches('[','value'),true);
  assert.equal(patternMatches('[A-Z]+','ABC'),true);
  assert.equal(patternMatches('[A-Z]+','123'),false);
});
