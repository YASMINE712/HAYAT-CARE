"""SQLite persistence. No patient information is placed in browser cookies."""
import csv
import json
import secrets
import sqlite3
import time
from pathlib import Path

from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict
from werkzeug.security import generate_password_hash


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY, password TEXT NOT NULL, profile TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, data TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY, username TEXT NOT NULL, assessment TEXT NOT NULL,
                    game TEXT NOT NULL, score REAL, attempts INTEGER, duration REAL,
                    accuracy REAL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sensors (
                    username TEXT PRIMARY KEY, device TEXT NOT NULL, state TEXT NOT NULL,
                    updated REAL NOT NULL, active INTEGER NOT NULL, notify INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS falls (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL, created REAL NOT NULL,
                    deadline REAL NOT NULL, status TEXT NOT NULL, notify INTEGER NOT NULL,
                    evidence TEXT NOT NULL, delivery TEXT NOT NULL DEFAULT 'not_requested',
                    delivery_detail TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL, title TEXT NOT NULL,
                    description TEXT NOT NULL, due REAL NOT NULL, repeat TEXT NOT NULL,
                    timezone TEXT NOT NULL, notify INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS deliveries (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL, kind TEXT NOT NULL,
                    message TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
                    created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS cognitive_sessions (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL, game TEXT NOT NULL,
                    level INTEGER NOT NULL, protocol TEXT NOT NULL, timezone TEXT NOT NULL,
                    created REAL NOT NULL, completed REAL, context TEXT NOT NULL,
                    rounds TEXT NOT NULL, results TEXT NOT NULL DEFAULT '[]');
                CREATE INDEX IF NOT EXISTS cognitive_user_history ON cognitive_sessions(username,completed);
                CREATE TABLE IF NOT EXISTS medication_plans (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL, name TEXT NOT NULL,
                    dose TEXT NOT NULL, instructions TEXT NOT NULL, start_date TEXT NOT NULL,
                    end_date TEXT, timezone TEXT NOT NULL, times TEXT NOT NULL, weekdays TEXT NOT NULL,
                    notify INTEGER NOT NULL, escalate INTEGER NOT NULL, grace INTEGER NOT NULL,
                    active INTEGER NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                    generated_until TEXT);
                CREATE TABLE IF NOT EXISTS medication_doses (
                    id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, username TEXT NOT NULL,
                    scheduled REAL NOT NULL, name TEXT NOT NULL, dose TEXT NOT NULL,
                    instructions TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    recorded REAL, reminded INTEGER NOT NULL DEFAULT 0,
                    escalated INTEGER NOT NULL DEFAULT 0, snooze_until REAL,
                    UNIQUE(plan_id,scheduled));
                CREATE INDEX IF NOT EXISTS medication_due ON medication_doses(status,scheduled);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        return db

    def user(self, username):
        with self.connect() as db:
            row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        return dict(row) if row else None

    def profile(self, username):
        user = self.user(username)
        return json.loads(user['profile']) if user else {}

    def save_profile(self, username, profile):
        with self.connect() as db:
            db.execute('UPDATE users SET profile=? WHERE username=?', (json.dumps(profile), username))

    def migrate_users(self, path):
        """One-time import, retaining the legacy CSV with hashed passwords only."""
        path = Path(path)
        if not path.exists():
            return
        with path.open(encoding='utf-8-sig', newline='') as file:
            reader = csv.DictReader(file)
            fields = list(reader.fieldnames or [])
            rows = list(reader)
        changed = False
        extras = ['mobility', 'vision', 'cognitive', 'medications', 'fall_history']
        with self.connect() as db:
            for row in rows:
                overflow = row.pop(None, [])
                for key, value in zip(extras, overflow):
                    row.setdefault(key, value)
                    if key not in fields:
                        fields.append(key)
                username, password = row.get('username'), row.get('password', '')
                if not username or not password:
                    continue
                if not password.startswith(('scrypt:', 'pbkdf2:')):
                    row['password'] = generate_password_hash(password)
                    changed = True
                profile = {key: value for key, value in row.items() if key != 'password'}
                db.execute('INSERT OR IGNORE INTO users VALUES (?,?,?)',
                           (username, row['password'], json.dumps(profile)))
        if changed:
            tmp = path.with_suffix('.tmp')
            with tmp.open('w', encoding='utf-8', newline='') as file:
                writer = csv.DictWriter(file, fields)
                writer.writeheader()
                writer.writerows(rows)
            tmp.replace(path)


class ServerSession(CallbackDict, SessionMixin):
    def __init__(self, data=None, sid=None):
        super().__init__(data, lambda self: setattr(self, 'modified', True))
        self.sid = sid or secrets.token_urlsafe(32)
        self.modified = False


class SQLiteSessions(SessionInterface):
    def __init__(self, store):
        self.store = store

    def open_session(self, app, request):
        sid = request.cookies.get(self.get_cookie_name(app))
        if sid:
            with self.store.connect() as db:
                row = db.execute('SELECT data FROM sessions WHERE id=? AND expires>?',
                                 (sid, time.time())).fetchone()
            if row:
                return ServerSession(json.loads(row['data']), sid)
        return ServerSession()

    def save_session(self, app, session, response):
        if not session.modified:
            return
        name = self.get_cookie_name(app)
        with self.store.connect() as db:
            if not session:
                db.execute('DELETE FROM sessions WHERE id=?', (session.sid,))
                response.delete_cookie(name)
                return
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?)',
                       (session.sid, json.dumps(dict(session)), time.time() + 43200))
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
        response.set_cookie(name, session.sid, max_age=43200, httponly=True,
                            secure=app.config['SESSION_COOKIE_SECURE'], samesite='Lax')
