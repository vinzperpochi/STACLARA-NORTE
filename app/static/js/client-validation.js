/* Basic browser validation shared by every shell. Server checks remain authoritative. */
(() => {
  'use strict';
  const controls = root => Array.from(root.querySelectorAll('input, select, textarea'));
  const peer = (field, name) => Array.from(field.form?.elements || []).find(item => item.name === name);
  const today = () => {
    const parts = new Intl.DateTimeFormat('en-CA', {timeZone:document.body.dataset.timezone || 'Asia/Manila', year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
    const values = Object.fromEntries(parts.map(part => [part.type,part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  };
  function patternMatches(pattern, value) {
    for (const flag of ['v','u','']) {
      try { return new RegExp(`^(?:${pattern})$`, flag).test(value); } catch (_) { /* Older browser or legacy pattern. */ }
    }
    return true;
  }
  function fileError(field) {
    const files = Array.from(field.files || []);
    const extensions = (field.dataset.allowedExtensions || '').toLowerCase().split(',').filter(Boolean).map(ext => `.${ext.replace(/^\./,'')}`);
    const accepted = (extensions.length ? extensions : (field.accept || '').toLowerCase().split(',').map(value=>value.trim())).filter(Boolean);
    const boundedUpload = accepted.length && accepted.every(value => value.startsWith('image/') || value==='application/pdf' || /\.(jpe?g|png|webp|pdf)$/.test(value));
    const max = Number(field.dataset.maxFileBytes || (boundedUpload ? 5 * 1024 * 1024 : 0));
    const mime = {'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp','.pdf':'application/pdf'};
    for (const file of files) {
      if (!file.size) return 'Select a nonempty file.';
      if (max && file.size > max) return `File must be no larger than ${Number((max/1048576).toFixed(2))} MB.`;
      const extension = /\.[^.]+$/.exec(file.name.toLowerCase())?.[0] || '';
      if (accepted.length && !accepted.some(type => type.startsWith('.') ? extension === type : type.endsWith('/*') ? file.type.startsWith(type.slice(0,-1)) : file.type === type)) {
        return `Choose an allowed file type: ${accepted.join(', ')}.`;
      }
      if (mime[extension] && file.type && mime[extension] !== file.type) return 'The file extension and file type do not match.';
    }
    return '';
  }
  function message(field) {
    const raw = String(field.value || '');
    const value = field.type === 'password' || field.autocomplete === 'current-password' || field.autocomplete === 'new-password' ? raw : raw.trim();
    const group = field.type === 'radio' ? Array.from(field.form?.elements || []).filter(item=>item.name===field.name && !item.disabled) : [field];
    const empty = field.type === 'checkbox' || field.type === 'radio' ? !group.some(item=>item.checked) : field.type === 'file' ? !field.files?.length : !value;
    if (field.validity?.badInput) return 'Enter a valid value.';
    const withField = field.dataset.requiredWith && peer(field, field.dataset.requiredWith);
    if ((field.required || field.hasAttribute('data-required') || (withField && String(withField.value || '').trim())) && empty) {
      return field.dataset.requiredMessage || (field.type==='checkbox' ? 'Please check this box to continue.' : 'This field is required.');
    }
    const matchName = field.dataset.equalTo || (field.name==='confirm_password' ? 'password' : field.name==='password_confirmation' ? (peer(field,'new_password') ? 'new_password' : 'password') : '');
    if (matchName && peer(field,matchName) && raw !== peer(field,matchName).value) return 'Passwords must match.';
    if (empty) return '';
    if (field.type === 'file') return fileError(field) || (field.validity?.customError ? field.validationMessage : '');
    const correction = field.dataset.correctionValue ? peer(field,'field_name')?.value : '';
    if ((field.type==='email' || field.dataset.validateEmail || correction==='email') && !/^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/.test(value)) return 'Enter a valid email address.';
    if (field.dataset.standardEmail && (/^\d+@/.test(value) || /@\d+\./.test(value))) return 'Please use a standard email address format.';
    if ((field.type==='tel' || field.dataset.validatePhone || correction==='contact_number') && field.dataset.phoneFormat!=='hotline') {
      const digits = value.replace(/\D/g,'');
      if (!/^[+\d()\s.\-]+$/.test(value) || !((digits.startsWith('09') && digits.length===11) || (digits.startsWith('639') && digits.length===12) || (digits.length>=7 && digits.length<=11))) return 'Enter a valid Philippine phone number (e.g., 09171234567 or (049) 559-0123).';
    }
    if ((field.dataset.validateName || ['first_name','middle_name','last_name'].includes(correction)) && (!/^[\p{L}\p{M} .\-]+$/u.test(value) || !/\p{L}/u.test(value))) return 'Use letters, spaces, hyphens, and periods only.';
    if (correction==='birth_date') {
      const parsed = new Date(`${value}T00:00:00Z`);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0,10)!==value) return 'Enter a valid date in YYYY-MM-DD format.';
      if (value<field.dataset.correctionDateMin || value>field.dataset.correctionDateMax) return `Birth date must be between ${field.dataset.correctionDateMin} and ${field.dataset.correctionDateMax}.`;
    }
    if (field.dataset.minAge) {
      const selected = field.type==='checkbox' ? (field.checked ? [value] : []) : Array.from(field.selectedOptions || []).map(option=>option.value);
      const birth = peer(field,'birth_date')?.value || field.dataset.residentBirthDate;
      if (selected.includes(field.dataset.ageValue) && birth) {
        const now = today();
        const age = Number(now.slice(0,4))-Number(birth.slice(0,4))-(now.slice(5)<birth.slice(5) ? 1 : 0);
        if (age<Number(field.dataset.minAge)) return `This category requires an age of at least ${field.dataset.minAge}.`;
      }
    }
    const length = Array.from(raw).length;
    const minLength = Number(field.getAttribute('minlength') || 0);
    const maxLength = field.getAttribute('maxlength');
    if (minLength && length<minLength) return `Enter at least ${minLength} characters.`;
    if (maxLength!==null && length>Number(maxLength)) return `Use no more than ${maxLength} characters.`;
    if (field.dataset.passwordPolicy==='complex' && (!/\p{Ll}/u.test(raw) || !/\p{Lu}/u.test(raw) || !/\p{Nd}/u.test(raw))) return 'Use uppercase, lowercase, and numbers in the new password.';
    if (field.type==='number' || field.type==='range') {
      const number = Number(value);
      if (!Number.isFinite(number)) return 'Enter a valid number.';
      if (field.min!=='' && field.min!=null && number<Number(field.min)) return `Enter a value of at least ${field.min}.`;
      if (field.max!=='' && field.max!=null && number>Number(field.max)) return `Enter a value no greater than ${field.max}.`;
      if (field.validity?.stepMismatch) return 'Use the allowed number increment.';
    }
    if (['date','datetime-local','time','month'].includes(field.type)) {
      if (field.min && value<field.min) return `Choose a value on or after ${field.min}.`;
      if (field.max && value>field.max) return `Choose a value on or before ${field.max}.`;
      if (field.dataset.noFuture && value.slice(0,10)>today()) return 'Date cannot be in the future.';
    }
    const start = field.dataset.notBefore && peer(field,field.dataset.notBefore);
    if (start?.value && value<start.value) return `This value must be on or after ${start.value}.`;
    if (field.pattern && !patternMatches(field.pattern,raw)) return field.title || 'Please use the requested format.';
    if (field.dataset.validationPattern && !patternMatches(field.dataset.validationPattern,raw)) return field.dataset.patternMessage || 'Please use the requested format.';
    if (field.validity?.typeMismatch || field.validity?.rangeOverflow || field.validity?.rangeUnderflow || field.validity?.patternMismatch) return field.validationMessage || 'Please check this value.';
    if (field.validity?.customError) return field.validationMessage;
    return '';
  }

  class ClientValidation {
    constructor() {
      this.errors = new WeakMap();
      this.touched = new WeakSet();
      this.submitted = new WeakSet();
      this.index = 0;
    }
    eligible(field, includeHidden=false) {
      return field && field.form && field.name && !field.disabled && !field.matches(':disabled') && !field.readOnly && !['hidden','button','submit','reset','image'].includes(field.type) && (includeHidden || field.getClientRects().length>0 || (field.closest('details:not([open])') && !field.closest('[hidden], .hidden')));
    }
    show(field, error) {
      let state = this.errors.get(field);
      if (!state && error) {
        const ids = (field.getAttribute('aria-describedby') || '').split(/\s+/);
        const slot = ids.map(id=>document.getElementById(id)).find(node=>node && node.closest('form')===field.form && (/error/.test(node.id) || node.hasAttribute('data-field-error')))
          || field.closest('[data-field]')?.querySelector('[data-field-error]');
        const node = slot || document.createElement('div');
        if (!node.id) node.id = `client-error-${++this.index}`;
        if (!slot) {
          node.className = 'civic-field-error';
          node.setAttribute('aria-live','polite');
          const parent = field.parentElement;
          const anchor = field.closest('label') || (parent.matches('.relative, .cp-input-wrap, .input-group') ? parent : field);
          anchor.insertAdjacentElement('afterend',node);
        }
        field.setAttribute('aria-describedby',[...new Set([...ids.filter(Boolean),node.id])].join(' '));
        state = {node};
        this.errors.set(field,state);
      }
      if (state) {
        state.node.textContent = error;
        state.node.hidden = !error;
        state.node.classList.toggle('hidden',!error);
        state.node.classList.add('civic-field-error');
      }
      field.classList.toggle('is-invalid',Boolean(error));
      field.setAttribute('aria-invalid',String(Boolean(error)));
    }
    validateField(field, includeHidden=false) {
      if (!this.eligible(field,includeHidden)) return true;
      const error = message(field);
      this.show(field,error);
      return !error;
    }
    validateContainer(container, options={}) {
      const invalid = controls(container).filter(field=>!this.validateField(field,Boolean(options.includeHidden)));
      if (invalid.length && options.focus) this.focus(invalid[0]);
      return !invalid.length;
    }
    focus(field) {
      const closed = field.closest('details:not([open])');
      if (closed) closed.open = true;
      field.focus({preventScroll:true});
      field.scrollIntoView({block:'center',behavior:'auto'});
    }
    prepare(form) {
      if (form.dataset.clientValidation==='off' || form.method==='dialog') return;
      // Native validation remains available when JavaScript is unavailable.
      form.noValidate = true;
      for (const node of document.querySelectorAll('[data-client-validation-schema]')) {
        let schema;
        try { schema = JSON.parse(node.textContent); } catch (_) { continue; }
        if (form.method.toLowerCase()!=='post' || !Array.from(form.elements).some(field=>field.name===schema.anchor)) continue;
        for (const [name,attrs] of Object.entries(schema.fields)) {
          for (const field of Array.from(form.elements).filter(item=>item.name===name && item.type!=='hidden')) {
            for (const [key,value] of Object.entries(attrs)) {
              if (key==='type' && field.tagName!=='INPUT') continue;
              field.setAttribute(key,value===true ? '' : String(value));
            }
          }
        }
      }
      const fields = controls(form);
      for (const field of fields) {
        if (['first_name','middle_name','last_name'].includes(field.name) && field.type!=='hidden') {
          field.dataset.validateName = 'true';
        }
        if (field.dataset.validateName) field.removeAttribute('pattern');
        for (const [end,start] of [['end_date','start_date'],['effective_until','effective_from'],['term_end','term_start'],['time_out','time_in'],['expiration_date','registration_date']]) {
          if (field.name===end && peer(field,start)) field.dataset.notBefore ||= start;
        }
      }
    }
    init() {
      document.querySelectorAll('form').forEach(form=>this.prepare(form));
      document.addEventListener('submit',event=>{
        const form = event.target;
        if (!form.matches('form') || form.dataset.clientValidation==='off' || event.submitter?.formNoValidate || form.method==='dialog') return;
        this.prepare(form);
        // The registration wizard reveals the first invalid step itself.
        if (form.closest('[data-register-wizard]')) return;
        this.submitted.add(form);
        if (!this.validateContainer(form,{focus:true})) {
          event.preventDefault();
          event.stopImmediatePropagation();
        }
      },true);
      for (const type of ['focusout','input','change']) document.addEventListener(type,event=>{
        const field = event.target;
        if (!field.matches?.('input,select,textarea') || !field.form || field.form.dataset.clientValidation==='off') return;
        if (type==='focusout' || type==='change') this.touched.add(field);
        if (this.touched.has(field) || this.submitted.has(field.form) || field.getAttribute('aria-invalid')==='true') this.validateField(field);
        // Recheck only fields the user has already visited or submitted.
        for (const other of controls(field.form)) {
          if (other!==field && (this.touched.has(other) || this.submitted.has(field.form) || other.getAttribute('aria-invalid')==='true')) this.validateField(other);
        }
      });
      document.addEventListener('reset',event=>queueMicrotask(()=>{
        this.submitted.delete(event.target);
        controls(event.target).forEach(field=>{this.touched.delete(field);this.show(field,'');});
      }));
      new MutationObserver(records=>{
        for (const record of records) for (const node of record.addedNodes) {
          if (node.nodeType!==1) continue;
          if (node.matches('form')) this.prepare(node);
          node.querySelectorAll('form').forEach(form=>this.prepare(form));
        }
      }).observe(document.body,{childList:true,subtree:true});
    }
  }
  window.CivicValidationRules = {message,fileError,patternMatches};
  window.civicValidation = new ClientValidation();
  const start = () => window.civicValidation.init();
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',start,{once:true}); else start();
})();
