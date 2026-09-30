import pandas as pd

class HealthMonitor:
    def __init__(self, twin, model):
        self.twin = twin
        self.model = model

    def run(self):
        vitals = self.twin.get_monitoring_reading()

        # Préparation des données pour le modèle (avec bonne clé systolic_bp)
        data = pd.DataFrame([{
            "heart_rate": vitals.get("heart_rate", 0),
            "systolic_bp": vitals.get("systolic_bp", 0),
            "diastolic_bp": vitals.get("diastolic_bp", 0),
            "glucose": vitals.get("glucose", 0),
            "oxygen": vitals.get("oxygen", 0)
        }])

        prediction = self.model.predict(data)[0]
        return prediction
