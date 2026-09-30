import csv
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

# No access to real patient data or outbound messages in these tests.
BOOT = tempfile.TemporaryDirectory()
os.environ['HAYATCARE_DATA_DIR'] = BOOT.name
from app import create_app
from ml.phone_fall import PhoneFallDetector
from storage import Store
from worker import tick


def trace(start=None):
    start = start or time.time()*1000-5000
    magnitudes = [9.81]*5 + [1, 1, 30] + [9.81]*25
    return [{'t': start+i*100, 'x': 0, 'y': 0, 'z': z} for i, z in enumerate(magnitudes)]


class DetectorTests(unittest.TestCase):
    def test_rest_and_walking_do_not_trigger(self):
        detector = PhoneFallDetector()
        for i in range(100):
            self.assertIsNone(detector.feed({'t': 10000+i*100, 'x': (i % 3)-1, 'y': 0, 'z': 9.81+(i%2)}))

    def test_fall_pattern_and_duplicate_cooldown(self):
        detector = PhoneFallDetector()
        first = trace(10000)
        events = [event for sample in first if (event := detector.feed(sample))]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['peak_m_s2'], 30)
        self.assertTrue(all(detector.feed(sample) is None for sample in trace(15000)))

    def test_impact_without_freefall_and_motion_after_impact(self):
        detector = PhoneFallDetector()
        for i, z in enumerate([9.81, 35]+[9.81]*30):
            self.assertIsNone(detector.feed({'t': 10000+i*100, 'x': 0, 'y': 0, 'z': z}))
        detector = PhoneFallDetector()
        for i, z in enumerate([1, 30]+[15, 4]*40):
            self.assertIsNone(detector.feed({'t': 10000+i*100, 'x': 0, 'y': 0, 'z': z}))

    def test_gaps_do_not_complete_a_fall(self):
        detector = PhoneFallDetector()
        detector.feed({'t':10000, 'x':0, 'y':0, 'z':1})
        detector.feed({'t':10100, 'x':0, 'y':0, 'z':30})
        for i in range(30):
            self.assertIsNone(detector.feed({'t':15000+i*100, 'x':0, 'y':0, 'z':9.81}))

    def test_missing_nonfinite_and_replayed_readings(self):
        detector = PhoneFallDetector()
        detector.feed({'t':10000, 'x':0, 'y':0, 'z':9.81})
        for sample in [{'t':10000, 'x':0, 'y':0, 'z':9.81},
                       {'t':10100, 'x':float('nan'), 'y':0, 'z':9.81}]:
            with self.assertRaises(ValueError):
                detector.feed(sample)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.tmp.name)/'test.db'),
                               'UPLOAD_FOLDER': str(Path(self.tmp.name)/'uploads'), 'MIGRATE_USERS': False})
        self.store = self.app.extensions['store']
        self.client = self.app.test_client()
        self.signup(self.client, 'alice')

    def tearDown(self):
        self.tmp.cleanup()

    def token(self, client):
        client.get('/login')
        with client.session_transaction() as session:
            return session['csrf']

    def post(self, path, data=None, client=None, form=False):
        client = client or self.client
        token = self.token(client)
        return client.post(path, headers={'X-CSRF-Token':token}, **({'data':data or {}} if form else {'json':data or {}}))

    def signup(self, client, username):
        response = self.post('/signup', {'username':username,'password':'test-password-123','name':username,
                                        'age':'72', 'emergency_contact':'+212600000001'}, client, True)
        self.assertEqual(response.status_code, 302)

    def start_phone(self, client=None, notify=False):
        response = self.post('/api/phone/start', {'notify':notify}, client)
        self.assertEqual(response.status_code, 200)
        return response.json['device']

    def create_fall(self, client=None, notify=False):
        device = self.start_phone(client, notify)
        response = self.post('/api/phone/samples', {'device':device, 'samples':trace()}, client)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIsNotNone(response.json['pending'])
        return response.json['pending']

    def test_passwords_are_hashed_and_duplicates_rejected(self):
        self.assertTrue(self.store.user('alice')['password'].startswith('scrypt:'))
        response = self.post('/signup', {'username':'alice','password':'other-password','name':'Other'}, form=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'already registered', response.data)

    def test_csrf_and_authentication(self):
        self.assertEqual(self.client.post('/api/phone/start', json={}).status_code, 400)
        stranger = self.app.test_client()
        self.assertEqual(stranger.get('/api/falls').status_code, 401)
        self.assertEqual(stranger.get('/phone-monitor').status_code, 302)

    def test_phone_fall_persists_across_batches_and_restart(self):
        device = self.start_phone()
        samples = trace()
        for batch in [samples[:8], samples[8:20], samples[20:]]:
            response = self.post('/api/phone/samples', {'device':device, 'samples':batch})
            self.assertEqual(response.status_code, 200)
        event_id = response.json['pending']['id']
        reopened = Store(self.store.path)
        with reopened.connect() as db:
            self.assertIsNotNone(db.execute('SELECT id FROM falls WHERE id=?', (event_id,)).fetchone())

    def test_cancel_prevents_caregiver_message(self):
        event = self.create_fall(notify=True)
        self.assertEqual(self.post('/api/falls/'+event['id']+'/cancel').status_code, 200)
        sent = []
        tick(self.store, sender=lambda *args: sent.append(args), now=event['deadline']+1)
        self.assertEqual(sent, [])
        self.assertEqual(self.client.get('/api/falls').json['events'][0]['status'], 'cancelled')

    def test_expired_cancel_does_not_claim_to_recall_message(self):
        event = self.create_fall(notify=True)
        with patch('phone_routes.time.time', return_value=event['deadline']+1):
            self.assertEqual(self.post('/api/falls/'+event['id']+'/cancel').status_code, 409)

    def test_timeout_escalates_exactly_once(self):
        event = self.create_fall(notify=True)
        sent = []
        def sender(*args):
            sent.append(args)
            return 'queued', 'test-sid'
        tick(self.store, sender=sender, now=event['deadline']+1)
        tick(self.store, sender=sender, now=event['deadline']+2)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], '+212600000001')
        self.assertIn('possible fall', sent[0][1])
        self.assertEqual(self.client.get('/api/falls').json['events'][0]['delivery'], 'queued')

    def test_no_opt_in_means_no_automatic_message(self):
        event = self.create_fall()
        sent = []
        tick(self.store, sender=lambda *args: sent.append(args), now=event['deadline']+1)
        self.assertEqual(sent, [])

    def test_missing_configuration_is_not_reported_as_delivered(self):
        event = self.create_fall(notify=True)
        tick(self.store, sender=lambda *args: ('not_configured', 'Configure messaging'), now=event['deadline']+1)
        self.assertEqual(self.client.get('/api/falls').json['events'][0]['delivery'], 'not_configured')

    def test_second_account_cannot_read_or_cancel_event(self):
        event = self.create_fall()
        bob = self.app.test_client()
        self.signup(bob, 'bobby')
        self.assertEqual(bob.get('/api/falls').json['events'], [])
        self.assertEqual(self.post('/api/falls/'+event['id']+'/cancel', client=bob).status_code, 409)

    def test_stale_stopped_replayed_or_superseded_sensors(self):
        first = self.start_phone()
        self.assertFalse(self.client.get('/api/falls').json['active'])
        second = self.start_phone()
        self.assertEqual(self.post('/api/phone/samples', {'device': first,'samples':trace()}).status_code, 409)
        self.post('/api/phone/stop', {'device':second})
        self.assertEqual(self.post('/api/phone/samples', {'device': second,'samples':trace()}).status_code, 409)

    def test_sensor_heartbeat_expires_and_state_survives_login(self):
        device=self.start_phone()
        response=self.post('/api/phone/samples',{'device':device,'samples':[{'t':time.time()*1000,'x':0,'y':0,'z':9.81}]})
        self.assertTrue(response.json['active'])
        with patch('phone_routes.time.time',return_value=time.time()+10):
            self.assertFalse(self.client.get('/api/falls').json['active'])

    def test_invalid_sensor_input_and_no_false_fall(self):
        device = self.start_phone()
        for samples in [[], [{'t':time.time()*1000,'x':None,'y':0,'z':9.81}], trace(10000)]:
            self.assertEqual(self.post('/api/phone/samples', {'device':device,'samples':samples}).status_code, 400)
        self.assertEqual(self.client.get('/api/falls').json['events'], [])

    def test_profiles_are_persistent_and_isolated(self):
        self.post('/save-profile', {'patientTwin':{'profile':{'name':'Alice Updated','medications':'one, two'}},
                                    'houseTwin':{'Kitchen':['chair']}})
        self.assertEqual(self.store.profile('alice')['medications'], ['one','two'])
        bob = self.app.test_client(); self.signup(bob,'bobby')
        self.assertNotIn('house', self.store.profile('bobby'))
        self.assertIn(b'Alice Updated', self.client.get('/house').data)

    def test_reminders_deliver_once_and_are_account_scoped(self):
        due = time.time()+60
        result = self.post('/api/reminders', {'title':'Water','due':datetime.fromtimestamp(due,timezone.utc).isoformat(),
                                            'timezone':'Africa/Casablanca','repeat':'none','notify':True})
        self.assertEqual(result.status_code, 200, result.json)
        sent=[]
        def sender(*args): sent.append(args); return 'queued','sid'
        tick(self.store, sender, now=due+1); tick(self.store,sender,now=due+5)
        self.assertEqual(len(sent),1)
        bob=self.app.test_client(); self.signup(bob,'bobby')
        self.assertEqual(bob.get('/api/reminders').json['reminders'],[])

    def test_invalid_reminder_and_other_account_edit(self):
        self.assertEqual(self.post('/api/reminders', {'title':'Test','due':'2020-01-01T12:00:00'}).status_code,400)
        result=self.post('/api/reminders', {'title':'Test','due':datetime.fromtimestamp(time.time()+60,timezone.utc).isoformat()})
        bob=self.app.test_client();self.signup(bob,'bobby')
        update={'id':result.json['id'],'title':'Changed','due':datetime.fromtimestamp(time.time()+60,timezone.utc).isoformat()}
        self.assertEqual(self.post('/api/reminders',update,bob).status_code,404)

    def test_recurring_reminder_preserves_local_time_across_dst(self):
        from zoneinfo import ZoneInfo
        zone=ZoneInfo('Europe/Paris')
        due=datetime(2027,3,27,9,tzinfo=zone).timestamp()
        self.post('/api/reminders',{'title':'Daily','due':datetime.fromtimestamp(due,zone).isoformat(),
                                   'timezone':'Europe/Paris','repeat':'daily'})
        tick(self.store, sender=lambda *a:('queued','sid'), now=due+1)
        row=self.client.get('/api/reminders').json['reminders'][0]
        self.assertEqual(datetime.fromtimestamp(row['due'],zone).hour,9)
        self.assertEqual(row['due']-due,23*3600)

    def test_two_workers_do_not_duplicate_a_message(self):
        from concurrent.futures import ThreadPoolExecutor
        event=self.create_fall(notify=True)
        sent=[]
        def sender(*args):
            sent.append(args)
            return 'queued','sid'
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(tick,self.store,sender,event['deadline']+1) for _ in range(2)]
            for future in futures:future.result()
        self.assertEqual(len(sent),1)

    def test_edit_profile_preserves_other_fields(self):
        response=self.post('/edit-profile',{'name':'Updated','age':'73','emergency_contact':'+212600000002'},form=True)
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.store.profile('alice')['emergency_contact'],'+212600000002')

    def test_pages_and_no_fake_assessment(self):
        for path in ['/menu','/house','/profile','/edit-profile','/dashboard','/reminders','/eldora','/phone-monitor','/fall-history','/summary','/alzheimertest']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, follow_redirects=True).status_code,200)
        text=self.client.get('/summary').get_data(as_text=True)
        self.assertIn('No results',text);self.assertNotIn('confidence: 90',text)
        self.assertNotIn('Slipped on wet floor',self.client.get('/fall-history').get_data(as_text=True))

    def test_games_render_save_and_separate_assessments(self):
        self.client.get('/start-assessment')
        from app import GAMES
        for slug in GAMES:
            self.assertEqual(self.client.get('/games/'+slug).status_code,200)
            result=self.post('/games/'+slug+'/submit', {'score':'5','attempts':'10','accuracy':'.5','duration':'30'},form=True)
            self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.client.get('/quiz').status_code,200)
        self.assertEqual(self.post('/games/quiz/submit',{'score':'4','accuracy':'.8'},form=True).status_code,200)
        summary=self.client.get('/summary').data
        self.assertIn(b'Memory',summary)
        self.assertIn(b'Demonstration category:',summary)
        self.client.get('/start-assessment')
        self.assertIn(b'No results',self.client.get('/summary').data)

    def test_eldora_receives_question(self):
        with patch('Eldora_Assistant.eldora.assistant.call_gemini_api',return_value='Test answer') as call:
            response=self.post('/eldora', {'question':'How do I save a reminder?','language':'en'},form=True)
            self.assertEqual(response.status_code,200)
            self.assertIn('How do I save a reminder?',call.call_args.args[0])

    def test_uploaded_paths_are_not_public(self):
        self.assertEqual(self.client.get('/static/uploads/living%20room_R.jpeg').status_code,404)
        self.assertEqual(self.client.get('/uploads/../../users.csv').status_code,404)

    def test_cardiovascular_uses_measured_inputs_and_missing_values_are_rejected(self):
        self.assertEqual(self.client.get('/heart-risk').status_code,200)
        values={'age':65,'cigsPerDay':0,'totChol':190,'sysBP':125,'diaBP':80,'BMI':24,
                'heartRate':72,'glucose':90,'male':0,'currentSmoker':0,'BPMeds':0,
                'prevalentStroke':0,'prevalentHyp':0,'diabetes':0,'education':'College'}
        response=self.post('/heart-risk',values,form=True)
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Research-model estimate:',response.data)
        self.assertEqual(self.store.profile('alice')['cardiovascular_inputs']['male'],0)
        invalid=values.copy();invalid.pop('glucose')
        self.assertIn(b'Provide glucose',self.post('/heart-risk',invalid,form=True).data)

    def test_nonobject_json_is_rejected(self):
        token=self.token(self.client)
        self.assertEqual(self.client.post('/api/phone/start',json=[],headers={'X-CSRF-Token':token}).status_code,400)


class MigrationTests(unittest.TestCase):
    def test_import_hashes_legacy_password_and_preserves_extra_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'users.csv'
            path.write_text('username,password,name\nlegacy,plaintext,Person,limited,normal,normal,medication,false\n')
            store=Store(Path(folder)/'test.db');store.migrate_users(path)
            self.assertNotIn('plaintext',path.read_text())
            self.assertEqual(store.profile('legacy')['mobility'],'limited')
            store.migrate_users(path)
            self.assertTrue(store.user('legacy')['password'].startswith('scrypt:'))


class NotificationTests(unittest.TestCase):
    def test_configured_template_uses_content_variables(self):
        from notifications import send_whatsapp
        settings={'TWILIO_ACCOUNT_SID':'ACtest','TWILIO_AUTH_TOKEN':'test-token',
                  'TWILIO_WHATSAPP_FROM':'whatsapp:+10000000001','TWILIO_WHATSAPP_CONTENT_SID':'HXtest',
                  'TWILIO_MESSAGING_SERVICE_SID':'MGtest'}
        with patch.dict(os.environ,settings), patch('requests.post') as post:
            post.return_value.ok=True
            post.return_value.json.return_value={'sid':'SMtest'}
            self.assertEqual(send_whatsapp('+212600000001','Possible fall'),('queued','SMtest'))
            payload=post.call_args.kwargs['data']
            self.assertEqual(payload['ContentSid'],'HXtest')
            self.assertEqual(json.loads(payload['ContentVariables']),{'1':'Possible fall'})
            self.assertNotIn('Body',payload)

    def test_provider_rejection_and_missing_configuration(self):
        from notifications import send_whatsapp
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(send_whatsapp('+212600000001','Test')[0],'not_configured')
        settings={'TWILIO_ACCOUNT_SID':'ACtest','TWILIO_AUTH_TOKEN':'test-token','TWILIO_WHATSAPP_FROM':'whatsapp:+10000000001'}
        with patch.dict(os.environ,settings), patch('requests.post') as post:
            post.return_value.ok=False;post.return_value.status_code=400
            self.assertEqual(send_whatsapp('+212600000001','Test')[0],'failed')


class LegacyModelTests(unittest.TestCase):
    def test_missing_or_insufficient_readings_are_unknown(self):
        import numpy as np
        from ml.safety_monitor import SafetyMonitor
        class Model:
            def predict(self, data, **kwargs): return np.array([[.9]])
        monitor=SafetyMonitor(model=Model(),sequence_length=3)
        self.assertIsNone(monitor.run(simulate=True))
        self.assertEqual(monitor.last_label,'No sensor data')
        reading={key:0 for key in monitor.feature_names}
        self.assertIsNone(monitor.run(real_data=reading))
        self.assertIsNone(monitor.run(real_data=reading))
        self.assertEqual(monitor.run(real_data=reading),1)
        self.assertEqual(monitor.last_label,'Possible fall')
        self.assertIsNone(monitor.run())
        self.assertEqual(monitor.history,[])

    def test_failed_model_never_reports_safe(self):
        from ml.safety_monitor import SafetyMonitor
        class Model:
            def predict(self,*a,**k):raise RuntimeError('Model failure')
        monitor=SafetyMonitor(model=Model(),sequence_length=1)
        self.assertIsNone(monitor.run(real_data={key:0 for key in monitor.feature_names}))
        self.assertEqual(monitor.last_label,'Fall model unavailable')


if __name__=='__main__':
    unittest.main()
