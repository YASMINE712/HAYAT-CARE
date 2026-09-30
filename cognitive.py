"""Versioned game trials, server scoring, and comparable personal history."""
import csv
import io
import json
import math
import random
import secrets
import statistics
import time
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, Response, current_app, jsonify, render_template, request, session

cognitive = Blueprint('cognitive', __name__)
PROTOCOL = 'adaptive-v1'
CATALOG = {
    'memory': {'name':'Everyday recall', 'domain':'Memory', 'description':'Remember familiar objects and find the missing one.', 'icon':'☕'},
    'drag-shapes': {'name':'Shape sequence', 'domain':'Visual memory', 'description':'Remember shapes in order, then tap them back.', 'icon':'▲'},
    'memory-numbers': {'name':'Number recall', 'domain':'Working memory', 'description':'Remember a number and enter it on the large keypad.', 'icon':'123'},
    'color': {'name':'Color sequence', 'domain':'Attention & memory', 'description':'Remember a sequence of named colors and symbols.', 'icon':'◆'},
    'stroop': {'name':'Focus on the ink', 'domain':'Attention', 'description':'Choose the ink color, even when the word says something else.', 'icon':'Aa'},
    'count': {'name':'Count and find', 'domain':'Visual attention', 'description':'Count the requested objects among the others.', 'icon':'●'},
    'sequence': {'name':'Complete the pattern', 'domain':'Reasoning', 'description':'Find the next number in a pattern.', 'icon':'…'},
}
LEVELS = {1:'Gentle',2:'Easy',3:'Moderate',4:'Challenging',5:'Advanced'}
OBJECTS = ['Cup','Key','Book','Apple','Spoon','Clock','Hat','Chair','Flower','Phone','Bread','Glass','Shoe','Bag','Comb','Plate']
SHAPES = ['Circle ●','Square ■','Triangle ▲','Star ★','Diamond ◆','Heart ♥']
COLORS = ['Red ●','Blue ■','Green ▲','Purple ◆']
COLOR_HEX = ['#b91c1c','#1d4ed8','#166534','#7e22ce']


def store():
    return current_app.extensions['store']


def make_rounds(game, level, rng=None):
    rng = rng or random.SystemRandom()
    rounds = []
    for _ in range(5):
        question = {'kind':game, 'preview_ms':0, 'choices':[], 'stimulus':[], 'answer':None}
        if game == 'memory':
            items = rng.sample(OBJECTS, level+2)
            answer = rng.choice(items)
            choices = [answer]+rng.sample([x for x in OBJECTS if x not in items],3)
            rng.shuffle(choices)
            question.update(stimulus=items, remaining=[x for x in items if x!=answer], answer=answer,
                            choices=choices, preview_ms=max(3500,8500-level*700),
                            instruction='Remember these everyday objects.', prompt='Which object is missing from the list below?')
        elif game in {'drag-shapes','color'}:
            symbols = SHAPES[:min(6,level+2)] if game == 'drag-shapes' else COLORS
            items = [rng.choice(symbols) for _ in range(level+1)]
            question.update(stimulus=items, choices=symbols, answer=items, preview_ms=5000+level*500,
                            instruction='Remember the sequence from left to right.', prompt='Tap the items in the same order.')
        elif game == 'memory-numbers':
            answer = ''.join(str(rng.randrange(10)) for _ in range(level+1))
            question.update(stimulus=[answer], answer=answer, preview_ms=max(3500,8000-level*600),
                            instruction='Remember this number, including any zero.', prompt='Enter the number you remember.')
        elif game == 'stroop':
            ink = rng.randrange(4)
            word = ink if level == 1 else rng.choice([n for n in range(4) if n != ink])
            distractors = [COLORS[rng.randrange(4)].split()[0] for _ in range(level-2)] if level>2 else []
            question.update(stimulus=[COLORS[word].split()[0]], ink=COLOR_HEX[ink], distractors=distractors,
                            choices=COLORS, answer=COLORS[ink], instruction='Focus on the color of the large word.',
                            prompt='What is the INK color of the large word? Ignore what the word says.')
        elif game == 'count':
            target = rng.choice(['Apple 🍎','Flower 🌼','Cup ☕'])
            number = rng.randint(2+level,4+level*2)
            distractors = [x for x in ['Apple 🍎','Flower 🌼','Cup ☕'] if x!=target]
            items = [target]*number + [rng.choice(distractors) for _ in range((level-1)*3)]
            rng.shuffle(items)
            choices = {number}
            while len(choices)<4:choices.add(max(1,number+rng.choice([-3,-2,-1,1,2,3])))
            choices=list(map(str,choices));rng.shuffle(choices)
            question.update(stimulus=items, choices=choices, answer=str(number),
                            instruction='Take your time. Count only the requested object.',prompt=f'How many {target} are there?')
        else:
            first=rng.randint(1,10)
            if level < 4:
                step = 1 if level==1 else rng.randint(2,level+1)
                numbers = [first+i*step for i in range(4)]
                answer = first+4*step
            elif level == 4:
                a,b=rng.randint(1,3),rng.randint(4,6)
                numbers=[first,first+a,first+a+b,first+2*a+b,first+2*a+2*b]
                answer=numbers[-1]+a
            else:
                numbers=[first,first+1,first+3,first+6,first+10]
                answer=first+15
            choices={answer}
            while len(choices)<4:choices.add(answer+rng.choice([-4,-2,-1,1,2,4]))
            choices=list(map(str,choices));rng.shuffle(choices)
            question.update(stimulus=[str(n) for n in numbers]+['?'],answer=str(answer),choices=choices,
                            instruction='Look for how the numbers change.',prompt='Which number comes next?')
        question['hint_text'] = ('Look again at the original items.' if question['preview_ms'] else
                                 'Work slowly. For patterns, compare the difference between neighboring numbers; for counting, point to each target once; for ink, ignore the word meaning.')
        rounds.append(question)
    return rounds


def summarize(row):
    row=dict(row)
    results=json.loads(row['results'])
    correct=sum(r['correct'] for r in results)
    return {'id':row['id'],'game':row['game'],'level':row['level'],'protocol':row['protocol'],
            'created':row['created'],'completed':row['completed'],'timezone':row['timezone'],
            'context':json.loads(row['context']), 'accuracy':correct/len(results) if results else 0,
            'correct':correct,'attempts':len(results), 'hints':sum(r['assisted'] for r in results),
            'response_ms':statistics.median(r['response_ms'] for r in results) if results else 0,
            'results':results}


def history(username):
    with store().connect() as db:
        rows=db.execute('SELECT * FROM cognitive_sessions WHERE username=? AND completed IS NOT NULL ORDER BY completed',
                        (username,)).fetchall()
    return [summarize(row) for row in rows]


def suggested_level(rows, game):
    same=[row for row in rows if row['game']==game and row['protocol']==PROTOCOL]
    if not same:return 1
    level=same[-1]['level']
    recent=[r for r in same if r['level']==level][-2:]
    if len(recent)==2:
        if all(r['accuracy']>=.8 and r['hints']==0 for r in recent):return min(5,level+1)
        if all(r['accuracy']<.5 for r in recent):return max(1,level-1)
    return level


def personal_progress(rows):
    from ml.cognitive_progress import analyze_series
    grouped=defaultdict(list)
    for row in rows:
        if row['protocol']==PROTOCOL:grouped[(row['game'],row['level'])].append(row)
    series=[]
    for (game,level),values in grouped.items():
        # Equal weight per calendar day. Assisted sessions never enter unassisted comparisons.
        days=defaultdict(list)
        for row in values:
            if not row['hints']:
                day=datetime.fromtimestamp(row['completed'],ZoneInfo(row['timezone'])).date().isoformat()
                days[day].append(row)
        daily=[{'date':day,'accuracy':statistics.mean(v['accuracy'] for v in vals),
                'response_ms':statistics.median(v['response_ms'] for v in vals)} for day,vals in sorted(days.items())]
        analysis=analyze_series(daily)
        series.append(dict(game=game,name=CATALOG[game]['name'],level=level,days=daily[-30:],
                           sessions=len(values),assisted=sum(bool(v['hints']) for v in values),**analysis))
    return sorted(series,key=lambda s:(list(CATALOG).index(s['game']),s['level']))


@cognitive.get('/brain-training')
def hub():
    rows=history(session['username'])
    return render_template('brain_hub.html',catalog=CATALOG,levels=LEVELS,
                           suggestions={key:suggested_level(rows,key) for key in CATALOG},recent=rows[-7:][::-1])


@cognitive.get('/brain-progress')
def progress():
    rows=history(session['username'])
    return render_template('brain_progress.html',series=personal_progress(rows),recent=rows[-30:][::-1],catalog=CATALOG)


@cognitive.get('/api/cognitive/progress')
def progress_data():
    return jsonify(series=personal_progress(history(session['username'])))


@cognitive.get('/brain-progress/export.csv')
def export():
    file=io.StringIO();writer=csv.writer(file)
    writer.writerow(['date','game','level','accuracy_percent','median_response_ms','assisted_rounds','protocol'])
    for row in history(session['username']):
        writer.writerow([datetime.fromtimestamp(row['completed'],ZoneInfo(row['timezone'])).isoformat(),row['game'],
                         row['level'],round(row['accuracy']*100,1),round(row['response_ms']),row['hints'],row['protocol']])
    return Response(file.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=game-progress.csv'})


@cognitive.post('/api/cognitive/start')
def start():
    data=request.get_json() or {}
    game=data.get('game')
    if not isinstance(game,str) or game not in CATALOG:raise ValueError('Choose a listed game.')
    timezone=str(data.get('timezone','UTC'))
    try: ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError): raise ValueError('Choose a valid timezone.')
    level=data.get('level',suggested_level(history(session['username']),game))
    if type(level) is not int or level not in LEVELS:raise ValueError('Choose a difficulty from 1 to 5.')
    context={key:str(data.get(key,'not_recorded')) for key in ('energy','mood')}
    if context['energy'] not in {'rested','usual','tired','not_recorded'} or context['mood'] not in {'good','usual','low','not_recorded'}:
        raise ValueError('Invalid check-in choice.')
    sid=secrets.token_hex(16)
    with store().connect() as db:
        db.execute('INSERT INTO cognitive_sessions (id,username,game,level,protocol,timezone,created,context,rounds) VALUES (?,?,?,?,?,?,?,?,?)',
                   (sid,session['username'],game,level,PROTOCOL,timezone,time.time(),json.dumps(context),json.dumps(make_rounds(game,level))))
    return jsonify(id=sid)


@cognitive.post('/api/cognitive/<sid>/round')
def current_round(sid):
    with store().connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM cognitive_sessions WHERE id=? AND username=?',(sid,session['username'])).fetchone()
        if not row:return jsonify(error='Session not found.'),404
        rounds=json.loads(row['rounds']);results=json.loads(row['results']);index=len(results)
        if index==len(rounds):return jsonify(done=True,summary=summarize(row))
        question=rounds[index]
        question['started_at']=time.time()
        # Returning to a revealed round counts as assistance, so it cannot bias the baseline.
        question['views']=question.get('views',0)+1
        db.execute('UPDATE cognitive_sessions SET rounds=? WHERE id=?',(json.dumps(rounds),sid))
        public={key:value for key,value in question.items() if key not in {'answer','started_at','views'}}
    return jsonify(done=False,index=index,total=len(rounds),question=public)


@cognitive.post('/api/cognitive/<sid>/answer')
def answer(sid):
    data=request.get_json() or {}
    index=data.get('index');response_ms=data.get('response_ms');assisted=data.get('assisted',False)
    if type(index) is not int or isinstance(response_ms,bool) or not isinstance(response_ms,(float,int)) or not math.isfinite(response_ms) or not 0<=response_ms<=3600000 or type(assisted) is not bool:
        raise ValueError('Invalid round response.')
    with store().connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM cognitive_sessions WHERE id=? AND username=?',(sid,session['username'])).fetchone()
        if not row:return jsonify(error='Session not found.'),404
        rounds=json.loads(row['rounds']);results=json.loads(row['results'])
        if index<0 or index>=len(rounds):raise ValueError('Invalid round number.')
        if index<len(results):
            if results[index]['answer']!=data.get('answer'):return jsonify(error='This round has already been saved.'),409
            return jsonify(result=results[index],done=len(results)==len(rounds),index=index)
        if index!=len(results):return jsonify(error='Complete the current round first.'),409
        question=rounds[index]
        if 'started_at' not in question:return jsonify(error='Start the round first.'),409
        if time.time()<question['started_at']+question['preview_ms']/1000:
            return jsonify(error='Finish viewing the items before answering.'),409
        submitted=data.get('answer')
        if not isinstance(submitted,(str,list)) or len(submitted)>100:raise ValueError('Invalid answer.')
        if isinstance(submitted,list) and any(not isinstance(x,str) or len(x)>100 for x in submitted):raise ValueError('Invalid answer.')
        result={'answer':submitted,'correct':submitted==question['answer'],'response_ms':round(response_ms),
                'assisted':assisted or question.get('views',0)>1}
        results.append(result);done=len(results)==len(rounds)
        db.execute('UPDATE cognitive_sessions SET results=?,completed=? WHERE id=?',
                   (json.dumps(results),time.time() if done else None,sid))
    return jsonify(result=result,expected=question['answer'],done=done,index=index)
