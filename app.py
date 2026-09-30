"""HayatCare Flask application. Run with `python run.py`."""
import hmac
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from storage import Store, SQLiteSessions
from phone_routes import phone, fall_status
from cognitive import cognitive, CATALOG, LEVELS, history, suggested_level
from medications import medications

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
GAMES = {'memory': ('memory_game', 'memory_game.html'),
         'drag-shapes': ('drag_shapes', 'shape_game.html'),
         'memory-numbers': ('memory_numbers', 'memory_numbers.html'),
         'color': ('color_game', 'color_game.html'), 'stroop': ('stroop_game', 'stroop_game.html'),
         'count': ('count_game', 'count_game.html'), 'sequence': ('sequence_game', 'sequence_game.html')}


def normalize_profile(data):
    if not isinstance(data, dict):
        raise ValueError('A patient profile is required.')
    source = data.get('profile', data)
    if not isinstance(source, dict):
        raise ValueError('Invalid patient profile.')
    allowed = ('name', 'age', 'gender', 'weight', 'height', 'diseases', 'onset', 'emergency_contact',
               'mobility', 'vision', 'cognitive', 'medications', 'fall_history', 'role', 'house', 'cardiovascular_inputs')
    result = {k: source[k] for k in allowed if k in source}
    for key, maximum in [('age', 125), ('weight', 500), ('height', 300)]:
        value = float(result.get(key) or 0)
        if not math.isfinite(value) or not 0 <= value <= maximum:
            raise ValueError(f'Invalid {key}.')
        result[key] = int(value) if key == 'age' else value
    for key in ('name', 'gender', 'diseases', 'onset', 'mobility', 'vision', 'cognitive', 'role'):
        result[key] = str(result.get(key) or '')[:500]
    meds = result.get('medications', [])
    result['medications'] = ([m.strip() for m in meds.split(',') if m.strip()] if isinstance(meds, str)
                             else [str(m)[:100] for m in meds[:30]] if isinstance(meds, list) else [])
    result['fall_history'] = result.get('fall_history') in (True, 'true', 'True', 'on', '1')
    contact = str(result.get('emergency_contact') or '').strip()
    if contact and not re.fullmatch(r'\+[1-9]\d{9,14}', contact):
        raise ValueError('Caregiver number must include country code, for example +212…')
    result['emergency_contact'] = contact
    return result


def create_app(config=None):
    app = Flask(__name__)
    data_dir = Path(os.getenv('HAYATCARE_DATA_DIR', str(ROOT / 'data')))
    app.config.update(SECRET_KEY=os.getenv('FLASK_SECRET_KEY') or secrets.token_hex(32),
                      DATABASE=str(data_dir / 'hayatcare.sqlite3'),
                      UPLOAD_FOLDER=str(data_dir / 'uploads'), MAX_CONTENT_LENGTH=8*1024*1024,
                      SESSION_COOKIE_NAME='hayatcare_session', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE') == '1',
                      MIGRATE_USERS=True, CSRF_ENABLED=True)
    if config:
        app.config.update(config)
    store = Store(app.config['DATABASE'])
    app.extensions['store'] = store
    app.session_interface = SQLiteSessions(store)
    if app.config['MIGRATE_USERS']:
        store.migrate_users(data_dir / 'users.csv')
    app.register_blueprint(phone)
    app.register_blueprint(cognitive)
    app.register_blueprint(medications)

    def csrf_token():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        return session['csrf']

    app.jinja_env.globals['csrf_token'] = csrf_token

    @app.before_request
    def protect_requests():
        if request.endpoint is None:
            return None
        public = {'index', 'login', 'signup', 'static'}
        if request.endpoint == 'static' and request.view_args.get('filename', '').startswith('uploads/'):
            abort(404)
        if request.endpoint not in public and not session.get('username'):
            if request.path.startswith('/api/') or request.method != 'GET':
                return jsonify(error='Please log in.'), 401
            return redirect(url_for('login'))
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and app.config['CSRF_ENABLED']:
            supplied = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token', '')
            if not supplied or not hmac.compare_digest(supplied, session.get('csrf', '')):
                return jsonify(error='Session expired. Reload the page and try again.'), 400
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.is_json:
            if not isinstance(request.get_json(silent=True), dict):
                return jsonify(error='Send a JSON object.'), 400

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'accelerometer=(self), gyroscope=(self)'
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(ValueError)
    def invalid_input(error):
        return jsonify(error=str(error)), 400

    def patient():
        return normalize_profile(store.profile(session['username']))

    def login_user(username):
        with store.connect() as db:
            db.execute('DELETE FROM sessions WHERE id=?', (session.sid,))
        session.clear()
        session.sid = secrets.token_urlsafe(32)
        session.update(username=username, logged_in=True)

    @app.get('/')
    def index():
        return render_template('home.html')

    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            try:
                username = request.form.get('username', '').strip()
                password = request.form.get('password', '')
                profile = normalize_profile(request.form.to_dict())
                if not re.fullmatch(r'[A-Za-z0-9_.-]{3,60}', username):
                    raise ValueError('Username must contain 3–60 letters, numbers, dots, underscores, or hyphens.')
                if len(password) < 8 or not profile['name']:
                    raise ValueError('Enter your name and a password of at least 8 characters.')
                with store.connect() as db:
                    db.execute('INSERT INTO users VALUES (?,?,?)',
                               (username, generate_password_hash(password), json.dumps(profile)))
                login_user(username)
                return redirect(url_for('menu'))
            except sqlite3.IntegrityError:
                flash('That username is already registered.', 'error')
            except ValueError as exc:
                flash(str(exc), 'error')
        return render_template('signup.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            user = store.user(request.form.get('username', '').strip())
            if user and check_password_hash(user['password'], request.form.get('password', '')):
                login_user(user['username'])
                return redirect(url_for('menu'))
            flash('Invalid username or password.', 'error')
        return render_template('login.html')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.get('/menu')
    def menu():
        return render_template('menu.html', username=session['username'])

    def demo_health():
        from patient.digital_twin_patient import ElderlyDigitalTwin
        import joblib
        profile = patient()
        twin = ElderlyDigitalTwin(profile['name'], profile['age'], profile['diseases'].split(','))
        history = []
        for hour in range(24):
            twin.run_scenario(f'Demo hour {hour}', stress=0.4+0.02*hour)
            history.append(dict(hour=hour, **twin.get_monitoring_reading()))
        health = 'Unavailable'
        try:
            from ml.health_monitor import HealthMonitor
            model = joblib.load(ROOT / 'ml/health_pipeline.joblib')
            health = 'High' if HealthMonitor(twin, model).run() == 1 else 'Normal'
        except Exception:
            app.logger.warning('Demo health model unavailable')
        chd = {'probability': None, 'risk_category': 'Unavailable', 'prediction': None,
               'top_risk_factors': {}, 'feature_contributions': {},
               'reason': 'Complete measured cardiovascular inputs are not available.'}
        if profile.get('cardiovascular_inputs'):
            try:
                from ml.chd_predictor import CHDPredictor
                chd = CHDPredictor().predict(profile['cardiovascular_inputs'])
                chd['reason'] = 'Research-model estimate from your saved inputs; not clinically validated.'
            except Exception:
                chd['reason'] = 'Saved inputs are available, but the CHD research model could not be evaluated.'
        return profile, twin, history, health, chd

    @app.get('/dashboard')
    def dashboard():
        profile, twin, history, health, chd = demo_health()
        fall = fall_status(session['username'])
        return render_template('dashboard.html', profile=profile, df=history, vitals=twin.get_monitoring_reading(),
                               health_risk=health, chd_risk=chd, fall_label=fall['label'], fall_expl=fall['explanation'])

    @app.get('/profile')
    def profile():
        profile, twin, history, health, chd = demo_health()
        fall = fall_status(session['username'])
        from ml.summarizer_agent import SummarizerAgent
        summary = SummarizerAgent()._generate_summary({'health': health, 'fall': fall['label'], 'simulated': True})
        return render_template('profile.html', patient_data=profile, house_data=profile.get('house', {}),
                               vitals=twin.get_monitoring_reading(), summary=summary,
                               health_expl=f'Demo model result: {health}. Readings are simulated.',
                               chd_expl=chd['reason'], chd_pred=chd, fall_expl=fall['explanation'],
                               fall_label=fall['label'], alzheimers_prediction=None)

    @app.route('/heart-risk', methods=['GET','POST'])
    def heart_risk():
        from ml.chd_predictor import CHDPredictor, validate_chd
        profile = patient()
        result, error = None, None
        data = profile.get('cardiovascular_inputs', {})
        if request.method == 'POST':
            try:
                data = validate_chd(request.form)
                profile['cardiovascular_inputs'] = data
                store.save_profile(session['username'], profile)
                result = CHDPredictor().predict(data)
            except FileNotFoundError:
                error = 'Model unavailable. Run python -m ml.train_chd_model. Your inputs were saved.'
            except ValueError as exc:
                error = str(exc)
            except Exception:
                error = 'The CHD model could not be evaluated. Rebuild it with python -m ml.train_chd_model.'
        return render_template('heart_risk.html', data=data, result=result, error=error)

    @app.route('/edit-profile', methods=['GET','POST'])
    def edit_profile():
        profile = patient()
        if request.method == 'POST':
            try:
                incoming = request.form.to_dict()
                incoming['fall_history'] = 'fall_history' in request.form
                profile.update(incoming)
                profile = normalize_profile(profile)
                store.save_profile(session['username'], profile)
                flash('Profile saved.')
                return redirect(url_for('profile'))
            except ValueError as exc:
                flash(str(exc), 'error')
        return render_template('edit_profile.html', profile=profile)

    @app.get('/house')
    def house():
        profile = patient()
        return render_template('index.html', patient_data=profile, house_data=profile.get('house', {}),
                               vitals=None, chd_risk=None, fall_risk=fall_status(session['username']),
                               alzheimers_prediction=None, health_risk=None, last_image=None)

    @app.route('/eldora', methods=['GET', 'POST'])
    def eldora():
        profile, twin, _, _, _ = demo_health()
        response, question = '', ''
        if request.method == 'POST':
            question = request.form.get('question', '').strip()[:2000]
            language = request.form.get('language', 'fr')
            if question:
                from Eldora_Assistant.eldora.assistant import EldoraAssistant
                response = EldoraAssistant().generate_advice(
                    {'name': profile['name'], 'age': profile['age'], 'conditions': profile['diseases'].split(','),
                     'vitals': twin.get_monitoring_reading(), 'simulated': True}, language, question=question)
        fall = fall_status(session['username'])
        return render_template('eldora.html', profile=profile, vitals=twin.get_monitoring_reading(),
                               question=question, response=response, fall_label=fall['label'], fall_expl=fall['explanation'])

    @app.get('/reminders')
    def reminders():
        return render_template('reminders.html', data=patient())

    @app.get('/fall-history')
    def fall_history():
        return render_template('fall.html', fall=fall_status(session['username']))

    @app.get('/contact')
    def contact():
        return render_template('contact.html')

    @app.get('/alzheimertest')
    def alzheimer():
        return redirect(url_for('cognitive.hub'))

    @app.get('/start-assessment')
    def start_assessment():
        session['assessment'] = secrets.token_hex(16)
        session['assessment_started'] = True
        return redirect(url_for('memory_game'))

    def game_page(template):
        if not session.get('assessment'):
            return redirect(url_for('start_assessment'))
        return render_template(template)

    for slug, (endpoint, template) in GAMES.items():
        app.add_url_rule('/games/'+slug, endpoint, lambda slug=slug: render_template('brain_game.html', game=slug, info=CATALOG[slug], levels=LEVELS, suggested=suggested_level(history(session['username']),slug)))

    @app.route('/quiz', methods=['GET', 'POST'])
    def cognitive_quiz():
        return game_page('quiz.html')

    @app.post('/games/<game_name>/submit')
    def game_result(game_name):
        game_name = game_name.replace('_', '-')
        if game_name not in GAMES and game_name != 'quiz':
            abort(404)
        if not session.get('assessment'):
            return jsonify(error='Start an assessment first.'), 409
        score = float(request.form.get('score', 0))
        attempts = int(request.form.get('attempts', 1))
        duration = float(request.form.get('duration', 0))
        accuracy = float(request.form.get('accuracy', min(1, score/max(1, attempts))))
        if not all(math.isfinite(v) for v in (score, duration, accuracy)) or not (0 <= score <= 10000 and 0 <= attempts <= 100000 and 0 <= duration <= 86400 and 0 <= accuracy <= 1):
            raise ValueError('Invalid game metrics.')
        with store.connect() as db:
            db.execute('INSERT INTO games (username,assessment,game,score,attempts,duration,accuracy,created) VALUES (?,?,?,?,?,?,?,?)',
                       (session['username'], session['assessment'], game_name.replace('-', '_'), score, attempts, duration, accuracy, time.time()))
        sequence = list(GAMES)+['quiz']
        next_game = sequence[sequence.index(game_name)+1] if game_name != 'quiz' else None
        next_url = ('/quiz' if next_game == 'quiz' else '/games/'+next_game) if next_game else '/summary'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best != 'text/html':
            return jsonify(success=True, next_game=next_url)
        return redirect(next_url)

    @app.get('/summary')
    def summary():
        with store.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT *, username AS user_id FROM games WHERE username=? AND assessment=? ORDER BY created',
                                               (session['username'], session.get('assessment', '')))]
        metrics = []
        for game in list(GAMES)+['quiz']:
            games = [r for r in rows if r['game'] == game.replace('-', '_')]
            if games:
                metrics.append({'name': game.replace('-', ' ').title(), 'avg_score': sum(r['score'] for r in games)/len(games),
                                'accuracy': sum(r['accuracy'] for r in games)/len(games), 'attempts': sum(r['attempts'] for r in games),
                                'avg_time': sum(r['duration'] for r in games)/len(games)})
        prediction, error = None, None
        completed = {r['game'] for r in rows}
        required = {slug.replace('-', '_') for slug in GAMES} | {'quiz'}
        if rows and completed != required:
            error = 'Complete all seven games and the questionnaire to generate the demonstration category.'
        elif rows:
            try:
                from ml.alzheimer_model import AlzheimerModel
                import pandas as pd
                model = AlzheimerModel.load(ROOT / 'ml/alz_model.joblib')
                features = model.prepare_data(pd.DataFrame(rows))
                prediction = model.predict(features.iloc[0].to_dict())
                if 'error' in prediction:
                    error, prediction = prediction['error'], None
            except Exception as exc:
                error = f'Cognitive model unavailable: {exc}'
        return render_template('summary.html', game_metrics=metrics, prediction=prediction, error=error, no_results=not rows)

    def save_profile_data(data):
        current = store.profile(session['username'])
        incoming = data.get('patientTwin', data)
        if isinstance(incoming, dict):
            incoming = incoming.get('profile', incoming)
        if not isinstance(incoming, dict):
            raise ValueError('Invalid patient profile.')
        current.update(incoming)
        profile = normalize_profile(current)
        if 'houseTwin' in data:
            house = data['houseTwin']
            if not isinstance(house, dict) or len(house) > 30 or any(not isinstance(v, list) or len(v)>100 for v in house.values()):
                raise ValueError('Invalid room information.')
            profile['house'] = {str(k)[:100]: [str(x)[:100] for x in v] for k, v in house.items()}
        store.save_profile(session['username'], profile)
        return profile

    @app.post('/save-profile')
    @app.post('/save-patient')
    def save_profile():
        profile = save_profile_data(request.get_json() or {})
        return jsonify(status='success', patient=profile)

    @app.post('/upload-room-image')
    def upload_room_image():
        file = request.files.get('file')
        room = request.form.get('room_name', '').strip()[:100]
        if not file or not room:
            raise ValueError('Select a room and an image.')
        suffix = Path(secure_filename(file.filename or '')).suffix.lower()
        if suffix not in {'.png', '.jpg', '.jpeg', '.webp'}:
            raise ValueError('Use PNG, JPEG, or WebP images.')
        folder = Path(app.config['UPLOAD_FOLDER']) / hashlib.sha256(session['username'].encode()).hexdigest()
        folder.mkdir(parents=True, exist_ok=True)
        filename = secrets.token_hex(16)+suffix
        path = folder / filename
        file.save(path)
        try:
            from utils import detect_objects_yolo_with_boxes
            detections, annotated = detect_objects_yolo_with_boxes(str(path), filename)
        except Exception:
            path.unlink(missing_ok=True)
            return jsonify(error='Object detection unavailable. Install requirements-vision.txt and verify yolov8n.pt.'), 503
        profile = patient()
        house = profile.get('house', {})
        house[room] = [d['name'] for d in detections]
        profile['house'] = house
        store.save_profile(session['username'], profile)
        return jsonify(room=room, objects=house[room], annotations=detections,
                       annotated_image_url=url_for('serve_uploads', filename=annotated))

    @app.get('/uploads/<path:filename>')
    def serve_uploads(filename):
        return send_from_directory(Path(app.config['UPLOAD_FOLDER']) / hashlib.sha256(session['username'].encode()).hexdigest(), filename)

    @app.post('/run-scenario')
    def run_scenario_endpoint():
        from simulator import run_scenario
        data = request.get_json() or {}
        profile = patient()
        return jsonify(recommendations=run_scenario({'patient': profile, 'house': profile.get('house', {}),
                                                   'activity': str(data.get('activity', 'general movement'))[:200],
                                                   'time': str(data.get('time_of_day', 'day'))[:50], 'events': data.get('events', [])}))

    @app.post('/notify-caregiver')
    @app.post('/send-reminder-whatsapp')
    def notify_caregiver():
        from notifications import send_whatsapp
        profile = patient()
        data = request.get_json() or {}
        message = (f"HayatCare: {profile['name']} requests caregiver assistance." if request.path == '/notify-caregiver'
                   else f"Reminder from {profile['name']}: {str(data.get('title', ''))[:150]}")
        if time.time()-session.get('last_manual_alert', 0) < 60:
            return jsonify(error='Please wait a minute before sending another message.'), 429
        session['last_manual_alert'] = time.time()
        status, detail = send_whatsapp(profile['emergency_contact'], message)
        return jsonify(success=status == 'queued', status=status, detail=detail), (200 if status == 'queued' else 503)

    return app


app = create_app()

if __name__ == '__main__':
    from run import serve_app
    serve_app(app)
