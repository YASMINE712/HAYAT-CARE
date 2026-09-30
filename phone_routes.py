import json
import math
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, jsonify, render_template, request, session
from ml.phone_fall import PhoneFallDetector

phone = Blueprint('phone', __name__)


def store():
    return current_app.extensions['store']


def fall_status(username):
    with store().connect() as db:
        sensor = db.execute('SELECT * FROM sensors WHERE username=?', (username,)).fetchone()
        events = db.execute('SELECT * FROM falls WHERE username=? ORDER BY created DESC LIMIT 50',
                            (username,)).fetchall()
    active = bool(sensor and sensor['active'] and time.time()-sensor['updated'] < 8)
    pending = next((dict(row) for row in events if row['status'] == 'pending'), None)
    label = 'Possible fall — awaiting response' if pending else (
        'Phone monitoring active' if active else 'Phone monitoring inactive')
    return {'active': active, 'label': label, 'pending': pending,
            'events': [dict(row) for row in events],
            'explanation': 'Experimental phone motion detection; no fall is inferred from missing readings.',
            'last_reading': sensor['updated'] if sensor else None,
            'magnitude': json.loads(sensor['state']).get('magnitude') if sensor else None,
            'notifications_configured': bool(__import__('os').getenv('TWILIO_ACCOUNT_SID') and
                                            __import__('os').getenv('TWILIO_AUTH_TOKEN') and
                                            __import__('os').getenv('TWILIO_WHATSAPP_FROM'))}


@phone.get('/phone-monitor')
def monitor():
    return render_template('phone_monitor.html')


@phone.get('/api/falls')
def status():
    return jsonify(fall_status(session['username']))


@phone.post('/api/phone/start')
def start():
    data = request.get_json() or {}
    device = secrets.token_urlsafe(24)
    notify = data.get('notify') is True
    if notify and not store().profile(session['username']).get('emergency_contact'):
        return jsonify(error='Add a caregiver number before enabling alerts.'), 400
    with store().connect() as db:
        db.execute('INSERT OR REPLACE INTO sensors VALUES (?,?,?,?,?,?)',
                   (session['username'], device, json.dumps(PhoneFallDetector().state), 0, 1, int(notify)))
    return jsonify(device=device)


@phone.post('/api/phone/stop')
def stop():
    data = request.get_json() or {}
    with store().connect() as db:
        db.execute('UPDATE sensors SET active=0 WHERE username=? AND device=?',
                   (session['username'], data.get('device')))
    return jsonify(success=True)


@phone.post('/api/phone/samples')
def samples():
    data = request.get_json() or {}
    batch = data.get('samples')
    if not isinstance(batch, list) or not 1 <= len(batch) <= 60:
        return jsonify(error='Send 1–60 motion samples.'), 400
    now = time.time()
    with store().connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM sensors WHERE username=?', (session['username'],)).fetchone()
        if not row or not row['active'] or row['device'] != data.get('device'):
            return jsonify(error='This phone session has stopped. Start monitoring again.'), 409
        detector = PhoneFallDetector(json.loads(row['state']))
        evidence = None
        try:
            for sample in batch:
                if not isinstance(sample, dict) or not all(k in sample for k in ('t', 'x', 'y', 'z')):
                    raise ValueError('Incomplete motion sample.')
                ts = sample['t']
                if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts) or abs(ts-now*1000) > 30000:
                    raise ValueError('Phone clock is out of sync or readings are too old.')
                event = detector.feed(sample)
                evidence = evidence or event
        except (ValueError, TypeError, KeyError) as exc:
            return jsonify(error=str(exc)), 400
        db.execute('UPDATE sensors SET state=?, updated=? WHERE username=?',
                   (json.dumps(detector.state), now, session['username']))
        pending = db.execute("SELECT id FROM falls WHERE username=? AND status='pending'", (session['username'],)).fetchone()
        if evidence and not pending:
            db.execute('INSERT INTO falls (id,username,created,deadline,status,notify,evidence) VALUES (?,?,?,?,?,?,?)',
                       (secrets.token_hex(16), session['username'], now, now+20, 'pending', row['notify'], json.dumps(evidence)))
    return jsonify(fall_status(session['username']))


@phone.post('/api/falls/<event_id>/cancel')
def cancel(event_id):
    with store().connect() as db:
        result = db.execute("UPDATE falls SET status='cancelled' WHERE id=? AND username=? AND status='pending' AND deadline>?",
                            (event_id, session['username'], time.time()))
    if not result.rowcount:
        return jsonify(error='The countdown has ended or this event was already handled. Any queued message cannot be recalled.'), 409
    return jsonify(success=True)


@phone.post('/api/falls/<event_id>/help')
def help_now(event_id):
    with store().connect() as db:
        result = db.execute("UPDATE falls SET deadline=?, notify=1 WHERE id=? AND username=? AND status='pending'",
                            (time.time(), event_id, session['username']))
    return (jsonify(success=True) if result.rowcount else (jsonify(error='Event already handled.'), 409))


@phone.get('/api/reminders')
def reminders_list():
    with store().connect() as db:
        rows = db.execute('SELECT * FROM reminders WHERE username=? ORDER BY due', (session['username'],)).fetchall()
        deliveries = db.execute("SELECT * FROM deliveries WHERE username=? AND kind='reminder' ORDER BY created DESC LIMIT 30",
                                (session['username'],)).fetchall()
    return jsonify(reminders=[dict(r) for r in rows], deliveries=[dict(r) for r in deliveries])


@phone.post('/api/reminders')
def reminders_save():
    data = request.get_json() or {}
    try:
        title = str(data.get('title', '')).strip()
        description = str(data.get('description', '')).strip()
        due = datetime.fromisoformat(str(data['due']).replace('Z', '+00:00'))
        if due.tzinfo is None:
            raise ValueError('A timezone offset is required.')
        timezone = str(data.get('timezone', 'UTC'))
        ZoneInfo(timezone)
        repeat = data.get('repeat', 'none')
        if not title or len(title) > 150 or len(description) > 1000 or repeat not in {'none', 'daily', 'weekly'}:
            raise ValueError('Check the reminder title, description, and repeat setting.')
        if due.timestamp() < time.time()-5:
            raise ValueError('Choose a future date and time.')
    except (ValueError, TypeError, KeyError, ZoneInfoNotFoundError) as exc:
        return jsonify(error=str(exc)), 400
    reminder_id = data.get('id') or secrets.token_hex(16)
    with store().connect() as db:
        if data.get('id'):
            row = db.execute('SELECT id FROM reminders WHERE id=? AND username=?',
                             (reminder_id, session['username'])).fetchone()
            if not row:
                return jsonify(error='Reminder not found.'), 404
        db.execute('INSERT OR REPLACE INTO reminders VALUES (?,?,?,?,?,?,?,?,?)',
                   (reminder_id, session['username'], title, description, due.timestamp(), repeat,
                    timezone, int(data.get('notify') is True), 1))
    return jsonify(success=True, id=reminder_id)


@phone.delete('/api/reminders/<reminder_id>')
def reminders_delete(reminder_id):
    with store().connect() as db:
        db.execute('DELETE FROM reminders WHERE id=? AND username=?', (reminder_id, session['username']))
    return jsonify(success=True)
