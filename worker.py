"""Persistent reminder and fall escalation worker; also usable as a separate process."""
import json
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from notifications import send_whatsapp
from medications import queue_reminders


def tick(store, sender=send_whatsapp, now=None):
    now = time.time() if now is None else now
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        queue_reminders(db,now)
        for row in db.execute("SELECT * FROM falls WHERE status='pending' AND deadline<=?", (now,)).fetchall():
            db.execute("UPDATE falls SET status='unconfirmed' WHERE id=?", (row['id'],))
            if row['notify']:
                profile = store.profile(row['username'])
                message = (f"HayatCare: possible fall detected by {profile.get('name', row['username'])}'s phone. "
                           'They did not cancel the alert. Please check on them. This is an unconfirmed sensor alert.')
                db.execute('INSERT OR IGNORE INTO deliveries VALUES (?,?,?,?,?,?,?)',
                           ('fall:'+row['id'], row['username'], 'fall', message, 'pending', '', now))
                db.execute("UPDATE falls SET delivery='pending' WHERE id=?", (row['id'],))
        for row in db.execute('SELECT * FROM reminders WHERE enabled=1 AND due<=?', (now,)).fetchall():
            delivery_id = f"reminder:{row['id']}:{int(row['due'])}"
            message = f"Reminder: {row['title']}. {row['description']}"
            db.execute('INSERT OR IGNORE INTO deliveries VALUES (?,?,?,?,?,?,?)',
                       (delivery_id, row['username'], 'reminder', message,
                        'pending' if row['notify'] else 'in_app', '', now))
            if row['repeat'] == 'none':
                db.execute('UPDATE reminders SET enabled=0 WHERE id=?', (row['id'],))
            else:
                due = datetime.fromtimestamp(row['due'], ZoneInfo(row['timezone']))
                days = 1 if row['repeat'] == 'daily' else 7
                while due.timestamp() <= now:
                    due += timedelta(days=days)
                db.execute('UPDATE reminders SET due=? WHERE id=?', (due.timestamp(), row['id']))
        pending = db.execute("SELECT * FROM deliveries WHERE status='pending'").fetchall()
        for row in pending:
            db.execute("UPDATE deliveries SET status='sending' WHERE id=?", (row['id'],))
    for row in pending:
        profile = store.profile(row['username'])
        try:
            status, detail = sender(profile.get('emergency_contact'), row['message'])
        except Exception:
            status, detail = 'unknown', 'Delivery attempt interrupted; check the messaging provider.'
        with store.connect() as db:
            db.execute('UPDATE deliveries SET status=?, detail=? WHERE id=?', (status, detail, row['id']))
            if row['kind'] == 'fall':
                db.execute('UPDATE falls SET delivery=?, delivery_detail=? WHERE id=?',
                           (status, detail, row['id'].removeprefix('fall:')))


def run_worker(store, stop=None):
    while stop is None or not stop.is_set():
        try:
            tick(store)
        except Exception:
            logging.exception('Scheduler tick failed')
        if stop:
            stop.wait(1)
        else:
            time.sleep(1)


if __name__ == '__main__':
    from app import app
    run_worker(app.extensions['store'])
