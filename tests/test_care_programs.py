import json
import os
import tempfile
import time
import unittest
from datetime import datetime,timedelta,timezone,date
from unittest.mock import patch

BOOT=tempfile.TemporaryDirectory()
os.environ['HAYATCARE_DATA_DIR']=BOOT.name
from app import create_app
from cognitive import make_rounds,personal_progress,suggested_level,PROTOCOL
from medications import local_timestamp,validate
from ml.cognitive_progress import analyze_series,personal_outliers
from worker import tick
from storage import Store

class CareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app({'TESTING':True,'MIGRATE_USERS':False,'DATABASE':self.tmp.name+'/care.sqlite3','CSRF_ENABLED':False})
        self.store=self.app.extensions['store'];self.client=self.app.test_client()
        with self.client.session_transaction() as s:s['username']='alice'
    def tearDown(self):self.tmp.cleanup()
    def post(self,url,data={}):return self.client.post(url,json=data)
    def plan(self,**changes):
        tomorrow=datetime.now(timezone.utc).date()+timedelta(days=1)
        data=dict(name='Prescribed medicine',dose='As prescribed',instructions='Test schedule',start_date=str(tomorrow),end_date=None,times=['08:00','20:00'],weekdays=list(range(7)),timezone='UTC',notify=False,escalate=False,grace=60)
        data.update(changes);r=self.post('/api/medications',data);self.assertEqual(r.status_code,200,r.json);return r.json['id'],data
    def first_dose(self):return self.client.get('/api/medications').json['doses'][0]
    def test_pages(self):
        for path in ['/brain-training','/brain-progress','/medications']:
            self.assertEqual(self.client.get(path).status_code,200)
    def test_all_games_server_grading_persistence_retry_and_privacy(self):
        for game in ['memory','drag-shapes','memory-numbers','color','stroop','count','sequence']:
            sid=self.post('/api/cognitive/start',dict(game=game,level=1,timezone='UTC')).json['id']
            for index in range(5):
                public=self.post(f'/api/cognitive/{sid}/round').json
                self.assertNotIn('answer',public['question'])
                with self.store.connect() as db:
                    row=db.execute('SELECT rounds FROM cognitive_sessions WHERE id=?',(sid,)).fetchone();rounds=json.loads(row[0]);rounds[index]['started_at']-=20
                    db.execute('UPDATE cognitive_sessions SET rounds=? WHERE id=?',(json.dumps(rounds),sid))
                payload=dict(index=index,answer=rounds[index]['answer'],response_ms=1250,assisted=False)
                r=self.post(f'/api/cognitive/{sid}/answer',payload);self.assertTrue(r.json['result']['correct'])
                self.assertEqual(self.post(f'/api/cognitive/{sid}/answer',payload).status_code,200)
                self.assertEqual(self.post(f'/api/cognitive/{sid}/answer',dict(payload,answer='wrong')).status_code,409)
            summary=self.post(f'/api/cognitive/{sid}/round').json['summary'];self.assertEqual(summary['correct'],5)
            stranger=self.app.test_client()
            with stranger.session_transaction() as s:s['username']='bob'
            self.assertEqual(stranger.post(f'/api/cognitive/{sid}/round',json={}).status_code,404)
        with Store(self.store.path).connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM cognitive_sessions WHERE completed IS NOT NULL').fetchone()[0],7)
        self.assertEqual(len(self.client.get('/api/cognitive/progress').json['series']),7)
    def test_invalid_and_premature_game_answers(self):
        for value in [0,6,True,'1']:
            self.assertEqual(self.post('/api/cognitive/start',dict(game='memory',level=value)).status_code,400)
        self.assertEqual(self.post('/api/cognitive/start',dict(game='memory',timezone='Bad/Zone')).status_code,400)
        sid=self.post('/api/cognitive/start',dict(game='memory')).json['id'];payload=dict(index=0,answer='Cup',response_ms=100)
        self.assertEqual(self.post(f'/api/cognitive/{sid}/answer',payload).status_code,409)
        self.post(f'/api/cognitive/{sid}/round')
        self.assertEqual(self.post(f'/api/cognitive/{sid}/answer',payload).status_code,409)
        self.assertEqual(self.post(f'/api/cognitive/{sid}/answer',dict(payload,response_ms=float('nan'))).status_code,400)
    def test_revealed_round_marks_assisted(self):
        sid=self.post('/api/cognitive/start',dict(game='count')).json['id']
        self.post(f'/api/cognitive/{sid}/round');q=self.post(f'/api/cognitive/{sid}/round').json['question']
        r=self.post(f'/api/cognitive/{sid}/answer',dict(index=0,answer=q['choices'][0],response_ms=100))
        self.assertTrue(r.json['result']['assisted'])
    def test_schedule_validation_and_account_isolation(self):
        pid,data=self.plan();self.assertGreaterEqual(len(self.client.get('/api/medications').json['doses']),12)
        self.assertEqual(self.post('/api/medications',dict(data,times=['08:00','08:00'])).status_code,400)
        self.assertEqual(self.post('/api/medications',dict(data,weekdays=[])).status_code,400)
        self.assertEqual(self.post('/api/medications',dict(data,timezone='bad')).status_code,400)
        other=self.app.test_client()
        with other.session_transaction() as s:s['username']='bob'
        self.assertEqual(other.get('/api/medications').json['plans'],[])
        self.assertEqual(other.put('/api/medications/'+pid,json=data).status_code,404)
        self.assertEqual(other.post('/api/medications/doses/'+self.first_dose()['id'],json={'action':'taken'}).status_code,404)
    def test_reminder_once_and_taken_record(self):
        self.plan();dose=self.first_dose();now=dose['scheduled']+5;sent=[]
        for _ in range(2):tick(self.store,sender=lambda *a:sent.append(a),now=now)
        self.assertEqual(sent,[])
        with self.store.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM deliveries WHERE kind='medication'").fetchone()[0],1)
        with patch('medications.time',return_value=now):
            self.assertEqual(self.post('/api/medications/doses/'+dose['id'],{'action':'taken'}).status_code,200)
            self.assertEqual(self.post('/api/medications/doses/'+dose['id'],{'action':'taken'}).status_code,200)
            self.assertEqual(self.post('/api/medications/doses/'+dose['id'],{'action':'skipped'}).status_code,409)
        tick(self.store,sender=lambda *a:sent.append(a),now=now+4000)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT status FROM medication_doses WHERE id=?',(dose['id'],)).fetchone()[0],'taken')
    def test_unconfirmed_outage_is_not_instruction_to_take(self):
        self.plan(notify=True,escalate=True);dose=self.first_dose();sent=[]
        def send(*args):sent.append(args);return 'queued','test'
        tick(self.store,sender=send,now=dose['scheduled']+3700);tick(self.store,sender=send,now=dose['scheduled']+3800)
        self.assertEqual(len(sent),1);self.assertIn('no recorded confirmation',sent[0][1]);self.assertIn('Do not advise an extra dose',sent[0][1])
    def test_snooze_then_due_and_future_rejected(self):
        self.plan();dose=self.first_dose()
        self.assertEqual(self.post('/api/medications/doses/'+dose['id'],{'action':'taken'}).status_code,409)
        now=dose['scheduled']+1;tick(self.store,now=now)
        with patch('medications.time',return_value=now):self.post('/api/medications/doses/'+dose['id'],{'action':'snooze'})
        tick(self.store,now=now+500)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM deliveries').fetchone()[0],1)
        tick(self.store,now=now+601)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM deliveries').fetchone()[0],2)
    def test_edit_pause_resume_preserves_taken_history(self):
        pid,data=self.plan();dose=self.first_dose();now=dose['scheduled']+1
        with patch('medications.time',return_value=now):
            self.post('/api/medications/doses/'+dose['id'],{'action':'taken'})
            self.assertEqual(self.client.put('/api/medications/'+pid,json=dict(data,dose='Updated prescription')).status_code,200)
            self.post('/api/medications/'+pid+'/active',{'active':False})
            self.post('/api/medications/'+pid+'/active',{'active':True})
        with self.store.connect() as db:
            old=db.execute('SELECT * FROM medication_doses WHERE id=?',(dose['id'],)).fetchone()
            self.assertEqual(old['status'],'taken');self.assertEqual(old['dose'],'As prescribed')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM (SELECT plan_id,scheduled FROM medication_doses GROUP BY plan_id,scheduled HAVING count(*)>1)').fetchone()[0],0)
    def test_weekdays_end_date_and_dst(self):
        tomorrow=datetime.now(timezone.utc).date()+timedelta(days=1)
        self.plan(end_date=str(tomorrow),weekdays=[tomorrow.weekday()])
        self.assertEqual(len(self.client.get('/api/medications').json['doses']),2)
        from zoneinfo import ZoneInfo
        spring=local_timestamp(date(2026,3,8),'02:30','America/New_York')
        self.assertEqual(datetime.fromtimestamp(spring,ZoneInfo('America/New_York')).strftime('%H:%M'),'03:30')
        fall=local_timestamp(date(2026,11,1),'01:30','America/New_York')
        self.assertEqual(datetime.fromtimestamp(fall,ZoneInfo('America/New_York')).fold,0)

class ProgressTests(unittest.TestCase):
    def daily(self,scores):return [dict(date=str(date(2026,1,1)+timedelta(days=2*i)),accuracy=s,response_ms=1000+50*i) for i,s in enumerate(scores)]
    def test_no_one_bad_day_alert_and_sustained_changes(self):
        self.assertEqual(analyze_series(self.daily([.8,.8,.8,.8,.8,.2]))['trend'],'Similar / mixed')
        self.assertEqual(analyze_series(self.daily([.8,.8,.8,.2,.2,.8]))['trend'],'Lower recently')
        self.assertEqual(analyze_series(self.daily([.3,.3,.3,.8,.8,.3]))['trend'],'Improving')
        self.assertEqual(analyze_series(self.daily([.8,.2]))['trend'],'Building baseline')
    def test_ml_fits_only_after_enough_personal_history(self):
        personal_outliers.cache_clear()
        self.assertEqual(analyze_series(self.daily([.8]*14))['ml_status'],'Collecting history')
        result=analyze_series(self.daily([.7,.8,.9]*5))
        self.assertIn('with 12 earlier days',result['ml_message']);self.assertEqual(personal_outliers.cache_info().misses,1)
    def test_separate_levels_and_assisted_daily_weighting(self):
        rows=[dict(game='memory',level=1,protocol=PROTOCOL,completed=1767225600,timezone='UTC',accuracy=.8,response_ms=1000,hints=0),dict(game='memory',level=2,protocol=PROTOCOL,completed=1767225600,timezone='UTC',accuracy=.2,response_ms=1000,hints=0)]
        rows.append(dict(rows[0],hints=1,accuracy=0))
        series=personal_progress(rows);self.assertEqual(len(series),2);self.assertEqual(series[0]['days'][0]['accuracy'],.8)
        self.assertEqual(series[0]['assisted'],1)
    def test_difficulty_and_adaptation(self):
        self.assertGreater(len(make_rounds('memory-numbers',5)[0]['answer']),len(make_rounds('memory-numbers',1)[0]['answer']))
        rows=[dict(game='memory',level=1,accuracy=1,hints=0,protocol=PROTOCOL)]
        self.assertEqual(suggested_level(rows,'memory'),1)
        self.assertEqual(suggested_level(rows*2,'memory'),2)

if __name__=='__main__':unittest.main()
