/* Recommendations are server decisions; no call or agency transmission is automated. */
(()=>{const form=document.querySelector('[data-incident-form]');if(!form)return;const result=form.querySelector('[data-routing-result]');let timer,controller,sequence=0;const node=(tag,text,cls)=>{const element=document.createElement(tag);element.textContent=text;if(cls)element.className=cls;return element;};async function update(){const current=++sequence;controller?.abort();controller=new AbortController();try{const response=await fetch(form.dataset.classifyUrl,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':form.elements.csrf_token.value},body:JSON.stringify({category:form.elements.category.value,description:form.elements.description.value,urgency:form.elements.urgency.value,immediate_danger:form.elements.immediate_danger.checked,external_review:form.elements.external_review.checked}),signal:controller.signal});if(!response.ok)throw Error('Unable to load recommendations. Emergency 911 remains available above.');const payload=await response.json();if(current!==sequence)return;const data=payload.data;result.replaceChildren();result.className='ops-full '+(data.classification==='EMERGENCY'?'ops-urgent':'');result.append(node('h3',data.classification==='EMERGENCY'?'Possible emergency — contact emergency services':`Suggested routing: ${data.agency_codes.join(' / ')}`),node('p',data.warning,'small'));for(const contact of data.contacts){const card=node('div','', 'ops-contact');card.append(node('strong',`${contact.agency} · ${contact.number}`));const call=node('a',`CALL ${contact.code}`,'ops-call');call.href=`tel:${contact.tel}`;card.append(call);result.append(card);}if(!data.contacts.length)result.append(node('p','No recently verified local contact is available. The barangay will review the report.','ops-muted'));}catch(error){if(error.name!=='AbortError')result.replaceChildren(node('p',error.message,'ops-muted'));}}for(const field of ['category','urgency','immediate_danger','external_review'])form.elements[field].addEventListener('change',update);form.elements.description.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(update,450);});update();})();

(() => {
  const input = document.querySelector('[data-incident-form] input[name="evidence"]');
  if (!input) return;
  const validate = () => {
    const files = [...input.files];
    const limit = Number(input.dataset.totalLimit);
    const size = files.reduce((total, file) => total + file.size, 0);
    input.setCustomValidity(
      files.length > 4 ? 'Attach at most four evidence files.' :
      limit && size > limit ? 'Combined evidence files must be 4 MB or smaller.' : ''
    );
  };
  input.addEventListener('change', validate);
  validate();
})();
