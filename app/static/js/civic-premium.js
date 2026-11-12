(() => {
  const initialize = () => {
  'use strict';
  const storage={get:key=>{try{return localStorage.getItem(key);}catch{return null;}},set:(key,value)=>{try{localStorage.setItem(key,value);}catch{}}};
  const theme = dark => {document.documentElement.dataset.civicTheme=dark?'dark':'light'; document.querySelectorAll('button[data-civic-theme]').forEach(button=>{button.setAttribute('aria-pressed',String(dark));const label=button.querySelector('[data-theme-label]');if(label)label.textContent=dark?'Light mode':'Dark mode';});};
  theme(document.documentElement.dataset.civicTheme==='dark');
  document.querySelectorAll('button[data-civic-theme]').forEach(button=>button.addEventListener('click',()=>{const dark=document.documentElement.dataset.civicTheme!=='dark';theme(dark);storage.set('scn-theme',dark?'dark':'light');}));
  const compact = enabled => {document.body.classList.toggle('civic-compact',enabled);document.querySelectorAll('[data-civic-compact]').forEach(b=>b.setAttribute('aria-expanded',String(!enabled)));};
  compact(storage.get('scn-compact')==='1');
  document.querySelectorAll('[data-civic-compact]').forEach(button=>button.addEventListener('click',()=>{const enabled=!document.body.classList.contains('civic-compact');compact(enabled);storage.set('scn-compact',enabled?'1':'0');}));
  document.querySelectorAll('#portal-sidebar nav > div').forEach(group=>{
    const heading=group.querySelector(':scope > span'), list=group.querySelector(':scope > ul'); if(!heading||!list)return;
    const button=document.createElement('button');button.type='button';button.className='civic-nav-group';button.textContent=heading.textContent;button.setAttribute('aria-expanded','true');
    button.addEventListener('click',()=>{list.hidden=!list.hidden;button.setAttribute('aria-expanded',String(!list.hidden));});heading.replaceWith(button);
  });
  document.querySelectorAll('#portal-sidebar nav a').forEach(link=>{link.title=link.textContent.trim().replace(/\s+/g,' ');if(!link.hasAttribute('aria-label'))link.setAttribute('aria-label',link.title);});
  document.querySelectorAll('#portal-main table, .content-area table').forEach((table, index) => {
    // Keep headings, filters and actions outside the horizontal scrolling area.
    let wrapper = table.parentElement;
    if (!wrapper.matches('.table-responsive, .overflow-x-auto, .civic-table-scroll') || wrapper.children.length > 1) {
      wrapper = document.createElement('div');
      table.before(wrapper);
      wrapper.append(table);
    }
    wrapper.classList.add('civic-table-scroll');
    wrapper.setAttribute('role', 'region');
    const caption = table.caption?.textContent.trim();
    wrapper.setAttribute('aria-label', caption || `Records table ${index + 1}`);
    const hint = document.createElement('p');
    hint.className = 'civic-table-hint';
    hint.id = `civic-table-hint-${index + 1}`;
    hint.textContent = 'Scroll horizontally to see all columns.';
    hint.hidden = true;
    wrapper.before(hint);
    wrapper.setAttribute('aria-describedby', hint.id);
    const updateScroll = () => {
      const scrollable = wrapper.scrollWidth > wrapper.clientWidth + 1;
      wrapper.tabIndex = scrollable ? 0 : -1;
      wrapper.classList.toggle('is-scrollable', scrollable);
      hint.hidden = !scrollable;
    };
    if ('ResizeObserver' in window) {
      const observer = new ResizeObserver(updateScroll);
      observer.observe(wrapper);
      observer.observe(table);
    }
    updateScroll();
    const headers = [...table.querySelectorAll('thead th')];
    headers.forEach(header => { if (!header.hasAttribute('scope')) header.scope = 'col'; });
    table.querySelectorAll('tbody tr').forEach(row => [...row.children].forEach((cell, i) => {
      if (cell.colSpan === 1 && headers[i]) cell.dataset.columnLabel = headers[i].textContent.trim();
    }));
  });
  document.querySelectorAll('form').forEach(form => {
    if (form.method.toLowerCase() === 'get') {
      form.addEventListener('formdata', event => {
        const action = new URL(form.action, location.href);
        if (action.origin !== location.origin || action.pathname !== location.pathname) return;
        for (const [key, value] of new URLSearchParams(location.search)) {
          if (/^(?:[a-z]+_)*per_page$/.test(key) && ['5','10','25','50','all'].includes(value) &&
              !event.formData.has(key)) event.formData.set(key, value);
        }
      });
      return;
    }
    if (form.method.toLowerCase() !== 'post') return;
    const reset = () => {
      form.removeAttribute('aria-busy');
      form.removeAttribute('data-civic-in-flight');
      form.querySelectorAll('[data-civic-submitting]').forEach(button => {
        button.classList.remove('is-submitting');
        button.removeAttribute('aria-disabled');
        delete button.dataset.civicSubmitting;
      });
    };
    window.addEventListener('pageshow', reset);
    form.addEventListener('reset', reset);
    form.addEventListener('submit', event => {
      if (form.hasAttribute('data-civic-in-flight')) {
        event.preventDefault();
        return;
      }
      // Wait for validation, confirmations and async handlers to cancel submission.
      queueMicrotask(() => {
        if (event.defaultPrevented || (!form.noValidate && !form.checkValidity())) return;
        const button = event.submitter;
        const target = button?.formTarget || form.target;
        const method = button?.getAttribute('formmethod') || form.method;
        if (method.toLowerCase() !== 'post' || (target && target !== '_self') ||
            button?.hasAttribute('data-no-loading')) return;
        form.dataset.dirty = '';
        form.setAttribute('data-civic-in-flight', '');
        form.setAttribute('aria-busy', 'true');
        if (button) {
          button.classList.add('is-submitting');
          button.setAttribute('aria-disabled', 'true');
          button.dataset.civicSubmitting = '1';
        }
      });
    });
    if (form.hasAttribute('data-unsaved-warning')) {
      form.addEventListener('input', () => form.dataset.dirty = '1');
      window.addEventListener('beforeunload', event => {
        if (form.dataset.dirty === '1') { event.preventDefault(); event.returnValue = ''; }
      });
    }
  });
  // Native Bootstrap focus management and confirmation for profile forms.
  const sidebar=document.getElementById('portal-sidebar');
  if (!sidebar) document.querySelectorAll('[data-civic-compact]').forEach(button=>button.hidden=true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
