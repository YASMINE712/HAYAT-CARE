import joblib
import numpy as np

class HeartDiseasePredictor:
    def __init__(self):
        self.model = joblib.load("ml/heart_disease_model.pkl")  # chemin du modèle

    def predict_risk(self, features: dict) -> int:
        """
        Prend un dictionnaire de caractéristiques, retourne 0 (pas de risque) ou 1 (risque)
        """
        # Transformer le dictionnaire en tableau pour le modèle
        input_array = np.array([list(features.values())]).reshape(1, -1)
        prediction = self.model.predict(input_array)
        return prediction[0]
