/* Browser sensor readings are in m/s² INCLUDING gravity; backend keeps detector state. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  let device = null, queue = [], lastSample = 0, lastSensorAt = 0, busy = false;
  let pending = null, wakeLock = null, announced = null, running = false;
  const status = text => { byId('motion-status').textContent = text; };
  const error = text => { byId('motion-error').textContent = text; byId('fall-error').textContent = text; };
  async function api(path, data) {
    const response = await fetch(path, data === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Server request failed.');
    return result;
  }
  function render(result) {
    pending = result.pending;
    byId('fall-prompt').hidden = !pending;
    if (pending && announced !== pending.id) {
      announced = pending.id;
      if (navigator.vibrate) navigator.vibrate([300, 100, 300]);
      byId('cancel-fall').focus();
    }
    renderCountdown();
    byId('motion-reading').textContent = result.magnitude == null ? '' : `Acceleration: ${result.magnitude} m/s²`;
    if (running && result.active) status('Phone monitoring active.');
    byId('provider-status').textContent = result.notifications_configured
      ? 'WhatsApp is connected. Check your event history for the status of caregiver messages.'
      : 'WhatsApp is not connected yet. You can still record events, but caregiver messages are unavailable.';
  }
  function motion(event) {
    const now = Date.now();
    if (!running || now-lastSample < 90) return;
    const a = event.accelerationIncludingGravity;
    if (!a || ![a.x, a.y, a.z].every(v => typeof v === 'number' && Number.isFinite(v))) return;
    lastSample = now; lastSensorAt = now;
    queue.push({t: now, x: a.x, y: a.y, z: a.z});
    if (queue.length > 50) {
      queue = queue.slice(-10);
      error('Connection is too slow. Readings were dropped; detection may miss events.');
    }
  }
  async function stop() {
    const stopped = device;
    running = false; device = null; queue = [];
    window.removeEventListener('devicemotion', motion);
    if (wakeLock) { try { await wakeLock.release(); } catch (_) {} wakeLock = null; }
    byId('start-monitor').disabled = false; byId('stop-monitor').disabled = true;
    status('Monitoring stopped. Any pending countdown still needs cancellation.');
    if (stopped) {
      try { await api('/api/phone/stop', {device: stopped}); } catch (e) { error(e.message); }
    }
  }
  byId('start-monitor').addEventListener('click', async () => {
    error(''); byId('start-monitor').disabled = true;
    try {
      if (!window.isSecureContext) throw new Error('Use an HTTPS address to enable phone sensors.');
      if (!window.DeviceMotionEvent) throw new Error('This browser does not expose phone motion sensors.');
      if (typeof DeviceMotionEvent.requestPermission === 'function') {
        const permission = await DeviceMotionEvent.requestPermission();
        if (permission !== 'granted') throw new Error('Motion permission was denied. Enable it in browser settings.');
      }
      const result = await api('/api/phone/start', {notify: byId('notify-caregiver').checked});
      device = result.device; queue = []; lastSample = 0; lastSensorAt = Date.now(); running = true;
      window.addEventListener('devicemotion', motion);
      byId('stop-monitor').disabled = false;
      status('Waiting for phone sensor readings…');
      if (navigator.wakeLock) {
        try { wakeLock = await navigator.wakeLock.request('screen'); } catch (_) { error('Keep the screen awake manually.'); }
      }
    } catch (e) { error(e.message); byId('start-monitor').disabled = false; }
  });
  byId('stop-monitor').addEventListener('click', stop);
  byId('cancel-fall').addEventListener('click', async () => {
    if (!pending) return;
    try { await api(`/api/falls/${pending.id}/cancel`, {}); render(await api('/api/falls')); error(''); }
    catch (e) { error(e.message); }
  });
  byId('help-now').addEventListener('click', async () => {
    if (!pending) return;
    try { await api(`/api/falls/${pending.id}/help`, {}); status('Caregiver alert requested. Check event history for provider status.'); }
    catch (e) { error(e.message); }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && running) stop();
  });
  window.addEventListener('pagehide', () => {
    if (!device) return;
    fetch('/api/phone/stop', {method: 'POST', keepalive: true,
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({device})}).catch(() => {});
  });
  setInterval(async () => {
    if (busy) return;
    busy = true;
    try {
      if (running && Date.now()-lastSensorAt > 5000) {
        await stop(); error('No sensor readings received. This device may not support motion sensing or permission was revoked.');
      }
      if (running && queue.length) {
        const batch = queue.splice(0, 50);
        render(await api('/api/phone/samples', {device, samples: batch}));
        error('');
      } else render(await api('/api/falls'));
    } catch (e) {
      error(e.message); status('Connection or sensor error — monitoring is not confirmed.');
    } finally { busy = false; }
  }, 1000);
  function renderCountdown() {
    if (!pending) return;
    const remaining = Math.max(0, Math.ceil(pending.deadline-Date.now()/1000));
    byId('countdown').textContent = pending.notify
      ? `Caregiver alert will be requested in ${remaining} seconds unless cancelled.`
      : `Event will be recorded in ${remaining} seconds. Automatic caregiver messages are off.`;
  }
  setInterval(renderCountdown, 200);
  api('/api/falls').then(render).catch(e => error(e.message));
})();
