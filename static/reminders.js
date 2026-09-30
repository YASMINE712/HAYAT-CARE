(() => {
  const el = id => document.getElementById(id);
  const message = text => { el('reminder-message').textContent = text; };
  async function api(path, options) {
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed.');
    return data;
  }
  const localDate = timestamp => {
    const date = new Date(timestamp);
    return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
  };
  function reset() { el('reminder-form').reset(); el('reminder-id').value = ''; }
  el('reminder-reset').onclick = reset;
  async function refresh() {
    const data = await api('/api/reminders');
    el('reminder-list').replaceChildren();
    for (const reminder of data.reminders) {
      const card = document.createElement('article'); card.className = 'p-4 border rounded';
      const title = document.createElement('h2'); title.textContent = reminder.title; title.className = 'font-semibold';
      const detail = document.createElement('p'); detail.textContent = `${new Date(reminder.due*1000).toLocaleString()} · ${reminder.repeat} · ${reminder.enabled ? 'scheduled' : 'completed'} · ${reminder.description}`;
      const edit = document.createElement('button'); edit.textContent = 'Edit'; edit.className = 'text-blue-700 p-2';
      edit.onclick = () => {
        el('reminder-id').value = reminder.id; el('reminder-title').value = reminder.title;
        el('reminder-due').value = localDate(reminder.due*1000);
        el('reminder-description').value = reminder.description; el('reminder-repeat').value = reminder.repeat;
        el('reminder-notify').checked = !!reminder.notify; el('reminder-title').focus();
      };
      const remove = document.createElement('button'); remove.textContent = 'Delete'; remove.className = 'text-red-700 p-2';
      remove.onclick = async () => {
        try { await api(`/api/reminders/${reminder.id}`, {method:'DELETE'}); await refresh(); }
        catch (e) { message(e.message); }
      };
      card.append(title, detail, edit, remove); el('reminder-list').append(card);
    }
    el('reminder-deliveries').replaceChildren();
    for (const delivery of data.deliveries) {
      const item = document.createElement('p');
      item.textContent = `${delivery.message} — ${delivery.status}${delivery.detail && delivery.status !== 'queued' ? ': '+delivery.detail : ''}`;
      el('reminder-deliveries').append(item);
    }
  }
  el('reminder-form').onsubmit = async event => {
    event.preventDefault();
    const data = {id: el('reminder-id').value || undefined, title:el('reminder-title').value,
      due:new Date(el('reminder-due').value).toISOString(), description:el('reminder-description').value,
      repeat:el('reminder-repeat').value, notify:el('reminder-notify').checked,
      timezone:Intl.DateTimeFormat().resolvedOptions().timeZone};
    try {
      await api('/api/reminders', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
      reset(); message('Reminder saved.'); await refresh();
    } catch (e) { message(e.message); }
  };
  refresh().catch(e => message(e.message));
  setInterval(() => refresh().catch(e => message(e.message)), 15000);
})();
