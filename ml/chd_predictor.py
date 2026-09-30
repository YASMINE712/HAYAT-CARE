"""CHD research-model adapter. Inputs must be supplied, never randomly invented."""
from pathlib import Path
import math
import joblib
import pandas as pd

MODEL_PATH = Path(__file__).resolve().parent / 'chd_pipeline.joblib'
NUMERIC = ['age', 'cigsPerDay', 'totChol', 'sysBP', 'diaBP', 'BMI', 'heartRate', 'glucose']
FLAGS = ['male', 'currentSmoker', 'BPMeds', 'prevalentStroke', 'prevalentHyp', 'diabetes']
EDUCATION = {'1':'Some High School','2':'High School/GED','3':'Some College','4':'College'}


def validate_chd(data):
    result = {}
    limits = {'age':125,'cigsPerDay':200,'totChol':1500,'sysBP':350,'diaBP':250,'BMI':150,'heartRate':350,'glucose':2000}
    for field in NUMERIC:
        if data.get(field) in (None, ''):
            raise ValueError(f'Provide {field}; unknown values must not be guessed.')
        value = float(data[field])
        if not math.isfinite(value) or not 0 <= value <= limits[field]:
            raise ValueError(f'Invalid {field}.')
        result[field] = value
    for field in FLAGS:
        if str(data.get(field)) not in {'0', '1'}:
            raise ValueError(f'Provide a yes/no value for {field}.')
        result[field] = int(data[field])
    education = EDUCATION.get(str(data.get('education')), data.get('education'))
    if education not in EDUCATION.values():
        raise ValueError('Select an education category.')
    result['education'] = education
    return result


class CHDPredictor:
    def __init__(self, model_path=MODEL_PATH, preprocessor_path=None):
        artifact = joblib.load(model_path)
        self.model = artifact['model'] if isinstance(artifact, dict) else artifact
        self.metadata = artifact.get('metadata', {}) if isinstance(artifact, dict) else {}

    def predict(self, patient_data):
        data = pd.DataFrame([validate_chd(patient_data)])
        classes = list(self.model.classes_)
        probability = float(self.model.predict_proba(data)[0][classes.index(1)])
        return {'probability':probability, 'prediction':int(probability>=.5),
                'risk_category':'High' if probability>=.2 else 'Medium' if probability>=.1 else 'Low',
                'feature_contributions':{}, 'top_risk_factors':{}, 'demo_only':True}
