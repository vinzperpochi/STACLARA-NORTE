/* Shared workspace controls. Data comes from authenticated server endpoints. */
(() => {
  'use strict';
  const element = (tag, text, className) => { const node = document.createElement(tag); if (text != null) node.textContent = text; if (className) node.className = className; return node; };
  const request = async (url, options = {}) => {
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', headers: {Accept: 'application/json'}, ...options});
    if (!response.ok) throw new Error('Unable to load data. Please try again.');
    const json = await response.json();
    if (!json.success) throw new Error(json.message || 'Unable to load data.');
    return json.data;
  };
  document.querySelectorAll('[data-notifications]').forEach(root => {
    const trigger = root.querySelector('[data-notification-trigger]'), panel = root.querySelector('.notification-panel'), count = root.querySelector('[data-notification-count]'), status = root.querySelector('[data-notification-status]'), items = root.querySelector('[data-notification-items]');
    let loading = false;
    const close = () => { panel.hidden = true; trigger.setAttribute('aria-expanded', 'false'); };
    const load = async () => {
      if (loading) return;
      loading = true;
      try {
        const data = await request(root.dataset.listUrl);
        count.textContent = data.unread; count.hidden = !data.unread;
        trigger.setAttribute('aria-label', `Notifications (${data.unread} unread)`);
        items.replaceChildren();
        data.items.forEach(item => {
          const row = element('article', null, item.is_read ? 'notification-item' : 'notification-item notification-unread');
          row.append(element('strong', item.title), element('p', item.message), element('time', new Intl.DateTimeFormat(undefined, {dateStyle: 'medium', timeStyle: 'short', timeZone: document.body.dataset.timezone}).format(new Date(item.created_at))));
          if (!item.is_read) {
            const button = element('button', 'Mark as read', 'civic-btn-outline'); button.type = 'button';
            button.addEventListener('click', () => mark({id: item.id}, button)); row.append(button);
          }
          items.append(row);
        });
        status.textContent = data.items.length ? (data.unread > data.items.filter(n => !n.is_read).length ? 'Showing the 25 most recent notifications.' : '') : 'No notifications yet.';
      } catch (error) { status.textContent = error.message; }
      finally { loading = false; }
    };
    const mark = async (values, button) => {
      button.disabled = true;
      try { await request(root.dataset.readUrl, {method: 'POST', body: new URLSearchParams({...values, csrf_token: root.dataset.csrf})}); await load(); }
      catch (error) { status.textContent = error.message; }
      finally { button.disabled = false; }
    };
    trigger.addEventListener('click', () => { panel.hidden = !panel.hidden; trigger.setAttribute('aria-expanded', String(!panel.hidden)); if (!panel.hidden) load(); });
    root.querySelector('[data-notification-close]').addEventListener('click', () => { close(); trigger.focus(); });
    root.querySelector('[data-notification-read-all]').addEventListener('click', event => mark({all: '1'}, event.currentTarget));
    document.addEventListener('click', event => { if (!root.contains(event.target)) close(); });
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && !panel.hidden) { close(); trigger.focus(); } });
    load(); setInterval(() => { if (!document.hidden) load(); }, 30000);
  });
  document.querySelectorAll('[data-calendar]').forEach(root => {
    let year, month, loading = false, today, navigating = false;
    const status = root.querySelector('[data-calendar-status]'), grid = root.querySelector('[data-calendar-grid]'), events = root.querySelector('[data-calendar-events]');
    const load = async () => {
      if (loading) return; loading = true;
      root.querySelectorAll('button').forEach(b => b.disabled = true);
      try {
        const query = year ? `?year=${year}&month=${month}` : '';
        const data = await request(root.dataset.url + query);
        if (today && today !== data.today && !navigating) { year = undefined; month = undefined; }
        today = data.today; year = data.year; month = data.month;
        const date = new Date(Date.UTC(year, month - 1, 1));
        root.querySelector('[data-calendar-title]').textContent = new Intl.DateTimeFormat('en', {month: 'long', year: 'numeric', timeZone: 'UTC'}).format(date);
        root.querySelector('[data-calendar-today]').textContent = `${data.today} · ${data.timezone}`;
        grid.replaceChildren();
        ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].forEach(day => grid.append(element('span', day, 'calendar-weekday')));
        for (let i = 0; i < date.getUTCDay(); i++) grid.append(element('span'));
        const days = new Date(Date.UTC(year, month, 0)).getUTCDate();
        for (let day = 1; day <= days; day++) {
          const key = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const cell = element('span', day, key === today ? 'calendar-day calendar-today' : 'calendar-day');
          if (key === today) cell.setAttribute('aria-current', 'date');
          const matches = data.events.filter(e => e.starts_at.slice(0, 10) <= key && (e.ends_at || e.starts_at).slice(0, 10) >= key);
          if (matches.length) { cell.classList.add('calendar-event-day'); cell.title = matches.map(e => e.title).join(', '); }
          grid.append(cell);
        }
        events.replaceChildren();
        data.events.forEach(event => { const row = element('article', null, 'calendar-event'); row.append(element('strong', event.title), element('p', new Intl.DateTimeFormat('en', {dateStyle: 'medium', timeStyle: 'short', timeZone: data.timezone}).format(new Date(event.starts_at)) + (event.venue ? ` · ${event.venue}` : ''))); events.append(row); });
        if (!data.events.length) events.append(element('p', 'No events scheduled for this month.'));
        status.textContent = '';
      } catch (error) { status.textContent = error.message; }
      finally { loading = false; root.querySelectorAll('button').forEach(b => b.disabled = false); }
    };
    const move = delta => { navigating = true; const next = new Date(Date.UTC(year, month - 1 + delta, 1)); year = next.getUTCFullYear(); month = next.getUTCMonth() + 1; load(); };
    root.querySelector('[data-calendar-previous]').addEventListener('click', () => move(-1));
    root.querySelector('[data-calendar-next]').addEventListener('click', () => move(1));
    root.querySelector('[data-calendar-reset]').addEventListener('click', () => { navigating = false; year = undefined; month = undefined; load(); });
    load(); setInterval(() => { if (!document.hidden) { if (!navigating) { year = undefined; month = undefined; } load(); } }, 60000);
  });
  document.querySelectorAll('[data-image-preview]').forEach(input => {
    let url;
    input.addEventListener('change', () => {
      const preview = input.closest('form').querySelector('[data-preview-image]');
      if (url) URL.revokeObjectURL(url);
      const file = input.files[0];
      input.setCustomValidity(file && (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) ? 'Select a JPEG, PNG or WebP image up to 5 MB.' : '');
      preview.hidden = !file || !input.checkValidity();
      if (!preview.hidden) { const reader=new FileReader();reader.onload=()=>{if(input.files?.[0]===file)preview.src=reader.result;};reader.readAsDataURL(file); }
    });
  });
  document.querySelectorAll('form[method="post"]').forEach(form => {
    let submitted = false;
    form.addEventListener('submit', event => {
      if (event.defaultPrevented) return;
      if (submitted) { event.preventDefault(); return; }
      submitted = true; form.setAttribute('aria-busy', 'true');
      // Defer disabling to preserve submitter name/value in native form serialization.
      setTimeout(() => form.querySelectorAll('button[type="submit"], button:not([type])').forEach(button => button.disabled = true), 0);
    });
  });
})();
