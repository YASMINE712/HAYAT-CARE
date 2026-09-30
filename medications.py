"""Patient-entered medication programs and persistent, self-reported dose records."""
import json
import re
import secrets
from time import time
from datetime import datetime, date, time as wall_time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Blueprint, current_app, jsonify, render_template, request, session

medications=Blueprint('medications',__name__)

def validate(data):
    result={}
    for key,limit in [('name',120),('dose',120),('instructions',600)]:
        value=data.get(key,'')
        if not isinstance(value,str) or len(value)>limit:raise ValueError(f'Invalid {key}.')
        result[key]=value.strip()
    if not result['name'] or not result['dose']:raise ValueError('Enter the medication name and prescribed dose.')
    zone=data.get('timezone','UTC')
    try:ZoneInfo(zone)
    except (ZoneInfoNotFoundError,ValueError,TypeError):raise ValueError('Choose a valid timezone.')
    result['timezone']=zone
    try:
        start=date.fromisoformat(data.get('start_date',''))
        end=date.fromisoformat(data['end_date']) if data.get('end_date') else None
    except (ValueError,TypeError):raise ValueError('Enter valid start and end dates.')
    if end and end<start:raise ValueError('End date must not precede the start date.')
    result.update(start_date=start.isoformat(),end_date=end.isoformat() if end else None)
    times=data.get('times');days=data.get('weekdays')
    if not isinstance(times,list) or not 1<=len(times)<=8 or any(not isinstance(t,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',t) for t in times):raise ValueError('Enter one to eight times in HH:MM format.')
    if len(set(times))!=len(times):raise ValueError('Remove duplicate dose times.')
    if not isinstance(days,list) or not days or any(type(d) is not int or not 0<=d<=6 for d in days):raise ValueError('Choose at least one weekday.')
    result.update(times=sorted(times),weekdays=sorted(set(days)))
    for key in ('notify','escalate'):
        if type(data.get(key,False)) is not bool:raise ValueError('Invalid reminder choice.')
        result[key]=int(data.get(key,False))
    grace=data.get('grace',60)
    if type(grace) is not int or not 15<=grace<=240:raise ValueError('Confirmation window must be 15–240 minutes.')
    result['grace']=grace
    return result

def local_timestamp(day,clock,zone):
    # One occurrence during a repeated hour. A missing local time shifts forward by the DST gap.
    return datetime.combine(day,wall_time.fromisoformat(clock),ZoneInfo(zone)).replace(fold=0).timestamp()

def materialize(db,now):
    for row in db.execute('SELECT * FROM medication_plans WHERE active=1').fetchall():
        today=datetime.fromtimestamp(now,ZoneInfo(row['timezone'])).date()
        until=today+timedelta(days=7)
        if row['end_date']:until=min(until,date.fromisoformat(row['end_date']))
        start=max(date.fromisoformat(row['start_date']),datetime.fromtimestamp(row['updated'],ZoneInfo(row['timezone'])).date())
        if row['generated_until']:start=max(start,date.fromisoformat(row['generated_until'])+timedelta(days=1))
        if start>until:continue
        days=json.loads(row['weekdays']);times=json.loads(row['times']);day=start
        while day<=until:
            if day.weekday() in days:
                for clock in times:
                    scheduled=local_timestamp(day,clock,row['timezone'])
                    if scheduled>=row['updated']:
                        db.execute('''INSERT INTO medication_doses
                            (id,plan_id,username,scheduled,name,dose,instructions) VALUES (?,?,?,?,?,?,?)
                            ON CONFLICT(plan_id,scheduled) DO UPDATE SET name=excluded.name,dose=excluded.dose,
                            instructions=excluded.instructions,status='pending',reminded=0,escalated=0,snooze_until=NULL
                            WHERE medication_doses.status='cancelled' ''',
                            (secrets.token_hex(16),row['id'],row['username'],scheduled,row['name'],row['dose'],row['instructions']))
            day+=timedelta(days=1)
        db.execute('UPDATE medication_plans SET generated_until=? WHERE id=?',(until.isoformat(),row['id']))

def queue_reminders(db,now):
    materialize(db,now)
    rows=db.execute('''SELECT d.*,p.notify,p.escalate,p.grace FROM medication_doses d
        JOIN medication_plans p ON p.id=d.plan_id WHERE p.active=1 AND d.status='pending' AND d.scheduled<=?''',(now,)).fetchall()
    for row in rows:
        late=now>=row['scheduled']+row['grace']*60
        if late:
            db.execute("UPDATE medication_doses SET status='unconfirmed',escalated=1 WHERE id=?",(row['id'],))
            if row['escalate']:
                message=f"HayatCare: {row['name']} has no recorded confirmation. Please check with the person; this does not prove a missed dose. Do not advise an extra dose based on this alert."
                db.execute('INSERT OR IGNORE INTO deliveries VALUES (?,?,?,?,?,?,?)',('medication:'+row['id']+':followup',row['username'],'medication',message,'pending','',now))
        elif not row['reminded'] and (not row['snooze_until'] or row['snooze_until']<=now):
            message=f"HayatCare schedule: {row['name']} — {row['dose']}. {row['instructions']} Follow the prescribed schedule and confirm in the app."
            delivery_id='medication:'+row['id']+':'+str(row['snooze_until'] or 'first')
            db.execute('INSERT OR IGNORE INTO deliveries VALUES (?,?,?,?,?,?,?)',(delivery_id,row['username'],'medication',message,'pending' if row['notify'] else 'in_app','',now))
            db.execute('UPDATE medication_doses SET reminded=1 WHERE id=?',(row['id'],))

def store():return current_app.extensions['store']

@medications.get('/medications')
def page():return render_template('medications.html')

@medications.get('/api/medications')
def listing():
    now=time()
    with store().connect() as db:
        # Scheduling is done by the worker; reading a page never sends a message.
        plans=[dict(r) for r in db.execute('SELECT * FROM medication_plans WHERE username=? ORDER BY created',(session['username'],))]
        doses=[dict(r) for r in db.execute("SELECT * FROM medication_doses WHERE username=? AND scheduled BETWEEN ? AND ? AND status!='cancelled' ORDER BY scheduled",(session['username'],now-7*86400,now+7*86400))]
        deliveries=[dict(r) for r in db.execute("SELECT id,status,created FROM deliveries WHERE username=? AND kind='medication' AND created>=? ORDER BY created",(session['username'],now-7*86400))]
    for row in plans:
        row['times']=json.loads(row['times']);row['weekdays']=json.loads(row['weekdays'])
    return jsonify(plans=plans,doses=doses,deliveries=deliveries,now=now)

@medications.post('/api/medications')
@medications.put('/api/medications/<plan_id>')
def save(plan_id=None):
    values=validate(request.get_json() or {});now=time();username=session['username']
    with store().connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if plan_id:
            old=db.execute('SELECT * FROM medication_plans WHERE id=? AND username=?',(plan_id,username)).fetchone()
            if not old:return jsonify(error='Program not found.'),404
            db.execute("UPDATE medication_doses SET status='cancelled' WHERE plan_id=? AND scheduled>=? AND status='pending'",(plan_id,now))
            assignments=','.join(key+'=?' for key in values)
            db.execute(f'UPDATE medication_plans SET {assignments},updated=?,generated_until=NULL WHERE id=?',
                       [json.dumps(v) if isinstance(v,list) else v for v in values.values()]+[now,plan_id])
        else:
            plan_id=secrets.token_hex(16)
            cols=','.join(values);marks=','.join('?' for _ in values)
            db.execute(f'INSERT INTO medication_plans (id,username,{cols},active,created,updated) VALUES (?,?,{marks},1,?,?)',
                       [plan_id,username]+[json.dumps(v) if isinstance(v,list) else v for v in values.values()]+[now,now])
        materialize(db,now)
    return jsonify(id=plan_id)

@medications.post('/api/medications/<plan_id>/active')
def active(plan_id):
    enabled=(request.get_json() or {}).get('active');now=time()
    if type(enabled) is not bool:raise ValueError('Choose active or paused.')
    with store().connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM medication_plans WHERE id=? AND username=?',(plan_id,session['username'])).fetchone()
        if not row:return jsonify(error='Program not found.'),404
        if bool(row['active'])==enabled:return jsonify(ok=True)
        db.execute('UPDATE medication_plans SET active=?,updated=?,generated_until=NULL WHERE id=?',(int(enabled),now,plan_id))
        if not enabled:
            db.execute("UPDATE medication_doses SET status='cancelled' WHERE plan_id=? AND status='pending' AND scheduled>=?",(plan_id,now))
            db.execute("UPDATE medication_doses SET status='unconfirmed' WHERE plan_id=? AND status='pending' AND scheduled<?",(plan_id,now))
            db.execute("UPDATE deliveries SET status='cancelled' WHERE status='pending' AND EXISTS (SELECT 1 FROM medication_doses d WHERE d.plan_id=? AND deliveries.id LIKE 'medication:'||d.id||':%')",(plan_id,))
        else:materialize(db,now)
    return jsonify(ok=True)

@medications.post('/api/medications/doses/<dose_id>')
def record(dose_id):
    action=(request.get_json() or {}).get('action');now=time()
    if not isinstance(action,str) or action not in {'taken','skipped','snooze'}:raise ValueError('Choose taken, skipped, or snooze.')
    with store().connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM medication_doses WHERE id=? AND username=?',(dose_id,session['username'])).fetchone()
        if not row:return jsonify(error='Dose not found.'),404
        if row['scheduled']>now:return jsonify(error='This dose is scheduled for later.'),409
        if row['status'] in {'taken','skipped','cancelled'}:
            if row['status']==action:return jsonify(ok=True)
            return jsonify(error='This dose already has a final record.'),409
        if action=='snooze':
            if row['status']!='pending':return jsonify(error='This confirmation window has ended. Record the actual status instead.'),409
            db.execute('UPDATE medication_doses SET snooze_until=?,reminded=0 WHERE id=?',(now+600,dose_id))
        else:db.execute('UPDATE medication_doses SET status=?,recorded=? WHERE id=?',(action,now,dose_id))
        db.execute("UPDATE deliveries SET status='cancelled' WHERE status='pending' AND id LIKE ?",('medication:'+dose_id+':%',))
    return jsonify(ok=True)
