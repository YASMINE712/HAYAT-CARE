"""Legacy model adapter. Phone readings use the separately tested phone detector."""
from pathlib import Path
import numpy as np


class SafetyMonitor:
    def __init__(self, model_path=None, sequence_length=30, model=None):
        if model is None:
            from tensorflow.keras.models import load_model
            model = load_model(model_path or Path(__file__).parent / 'safety_model.h5')
        self.model = model
        self.sequence_length = sequence_length
        self.feature_names = ['AccX', 'AccY', 'AccZ', 'GyrX', 'GyrY', 'GyrZ', 'EulerX', 'EulerY', 'EulerZ']
        self.history = []
        self.last_label = 'No sensor data'

    def run(self, real_data=None, simulate=False, digital_twin=None):
        if simulate and digital_twin is not None:
            real_data = digital_twin.simulate_motion_reading()
        if real_data is None:
            self.history.clear()
            self.last_label = 'No sensor data'
            return None
        try:
            values = [float(real_data[key]) for key in self.feature_names]
            if not np.isfinite(values).all():
                raise ValueError('Invalid motion values')
        except (KeyError, ValueError, TypeError):
            self.history.clear()
            self.last_label = 'Invalid sensor data'
            return None
        self.history.append(values)
        self.history = self.history[-self.sequence_length:]
        if len(self.history) < self.sequence_length:
            self.last_label = 'Collecting sensor readings'
            return None
        try:
            output = np.asarray(self.model.predict(np.array([self.history]), verbose=0))
            if output.size != 1 or not np.isfinite(output).all():
                raise ValueError('Expected a binary model output')
            probability = float(output.ravel()[0])
            if not 0 <= probability <= 1:
                raise ValueError('Invalid model probability')
            prediction = int(probability > .5)
            self.last_label = 'Possible fall' if prediction else 'No fall pattern detected'
            if simulate:
                self.last_label = 'Simulated: '+self.last_label
            return prediction
        except Exception:
            self.last_label = 'Fall model unavailable'
            return None
