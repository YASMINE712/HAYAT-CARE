"""Optional real-model checks: install requirements-vision.txt and local YOLO weights."""
import importlib.util
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AVAILABLE=importlib.util.find_spec('ultralytics') is not None and (ROOT/'yolov8n.pt').exists()

@unittest.skipUnless(AVAILABLE,'Optional vision packages and local YOLO weights are required.')
class VisionIntegrationTests(unittest.TestCase):
    def test_actual_upload_detection_and_private_image_access(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict('os.environ',{'HAYATCARE_DATA_DIR':folder}):
                from app import create_app
            app=create_app({'TESTING':True,'MIGRATE_USERS':False,'CSRF_ENABLED':False,
                            'DATABASE':str(Path(folder)/'test.sqlite3'),'UPLOAD_FOLDER':str(Path(folder)/'uploads')})
            client=app.test_client()
            with client.session_transaction() as session:session['username']='vision-demo'
            # Existing public-facing project artwork, not a patient upload.
            with (ROOT/'static/images/hero.jpg').open('rb') as image:
                response=client.post('/upload-room-image',data={'room_name':'Demo','file':(image,'demo.jpg')})
            self.assertEqual(response.status_code,200,response.json)
            detections=response.json['annotations']
            self.assertTrue(detections)
            for item in detections:
                self.assertGreater(item['confidence'],.5)
                self.assertLessEqual(item['confidence'],1)
                x1,y1,x2,y2=item['box']
                self.assertGreater(x2,x1);self.assertGreater(y2,y1)
            with client.get(response.json['annotated_image_url']) as downloaded:
                self.assertEqual(downloaded.status_code,200)
            other=app.test_client()
            with other.session_transaction() as session:session['username']='another-demo'
            self.assertEqual(other.get(response.json['annotated_image_url']).status_code,404)

if __name__=='__main__':unittest.main()
