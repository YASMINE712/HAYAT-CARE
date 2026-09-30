import numpy as np
import random

class ElderlyDigitalTwin:
    def __init__(self, name, age, conditions=None):
        self.name = name
        self.age = age
        self.conditions = conditions or []

        # Initialize vitals with default values
        self.vitals = {
            "heart_rate": 75,
            "temperature": 36.6,
            "systolic_bp": 120,
            "diastolic_bp": 80,
            "glucose": 110,
            "oxygen": 98
        }

        # Initialize activity log and scenario log
        self.activity_log = []
        self.scenario_log = []

        # Initialize new variables (can be extended with more variables as needed)
        self.new_variables = {
            "BMI": 25,
            "cholesterol": 200,
            "sugar_level": 110,
            "stress_level": 0.5
        }

    def simulate_vitals(self, stress=0.5):
        """Simulate vital sign changes based on stress."""
        self.vitals["heart_rate"] = int(np.clip(75 + stress*40 + np.random.normal(0, 5), 60, 160))
        self.vitals["temperature"] = round(np.clip(36.5 + stress*2 + np.random.normal(0, 0.3), 35, 40), 1)
        self.vitals["systolic_bp"] = int(np.clip(120 + stress*40 + np.random.normal(0, 8), 100, 200))
        self.vitals["diastolic_bp"] = int(np.clip(80 + stress*20 + np.random.normal(0, 5), 60, 130))
        self.vitals["glucose"] = int(np.clip(110 + stress*30 + np.random.normal(0, 10), 60, 200))
        self.vitals["oxygen"] = int(np.clip(98 - stress*10 + np.random.normal(0, 1), 85, 100))

        # Update new variables based on stress and vitals
        self.new_variables["BMI"] = round(25 + (self.vitals["glucose"]-100)/50 + np.random.normal(0, 3), 1)
        self.new_variables["cholesterol"] = int(np.clip(200 + (self.vitals["heart_rate"]-75)/5 + np.random.normal(0, 20), 150, 300))
        self.new_variables["sugar_level"] = self.vitals["glucose"]
        self.new_variables["stress_level"] = stress

    def run_scenario(self, label, stress=0.9):
        """Simulate a scenario, updating vitals and logging the event."""
        self.simulate_vitals(stress)
        self.activity_log.append(label)
        self.scenario_log.append({
            "scenario": label,
            "vitals": self.vitals.copy(),
            "new_variables": self.new_variables.copy()
        })

    def get_chd_risk_data(self):
        """Generate the data needed for CHD risk prediction."""
        return {
            'male': np.random.choice([0, 1]),
            'age': self.age,
            'education': np.random.choice(['1', '2', '3', '4']),
            'currentSmoker': np.random.choice([0, 1], p=[0.7, 0.3]),
            'cigsPerDay': np.random.randint(0, 20),
            'BPMeds': np.random.choice([0, 1], p=[0.8, 0.2]),
            'prevalentStroke': 1 if "stroke" in self.conditions else 0,
            'prevalentHyp': 1 if "hypertension" in self.conditions else 0,
            'diabetes': 1 if "diabetes" in self.conditions else 0,
            'totChol': int(np.clip(200 + (self.vitals["heart_rate"]-75)/5 + np.random.normal(0, 20), 150, 300)),
            'sysBP': self.vitals["systolic_bp"],
            'diaBP': self.vitals["diastolic_bp"],
            'BMI': round(25 + (self.vitals["glucose"]-100)/50 + np.random.normal(0, 3), 1),
            'heartRate': self.vitals["heart_rate"],
            'glucose': self.vitals["glucose"]
        }

    def get_monitoring_reading(self):
        """Retrieve the latest monitoring data (vitals and new variables), ensuring all required keys."""
        # Ensure all keys expected by explanation functions exist
        required_keys = [
            "systolic_bp", "diastolic_bp", "heart_rate",
            "temperature", "glucose", "oxygen"
        ]
        for key in required_keys:
            if key not in self.vitals:
                self.vitals[key] = 0

        for key in ["BMI", "cholesterol", "sugar_level", "stress_level"]:
            if key not in self.new_variables:
                self.new_variables[key] = 0

        return {
            "heart_rate": self.vitals["heart_rate"],
            "systolic_bp": self.vitals["systolic_bp"],
            "diastolic_bp": self.vitals["diastolic_bp"],
            "temperature": self.vitals["temperature"],
            "glucose": self.vitals["glucose"],
            "oxygen": self.vitals["oxygen"],
            "BMI": self.new_variables["BMI"],
            "cholesterol": self.new_variables["cholesterol"],
            "sugar_level": self.new_variables["sugar_level"],
            "stress_level": self.new_variables["stress_level"]
        }

    def export_summary(self):
        """Export a detailed summary of the patient’s current state."""
        return {
            "name": self.name,
            "age": self.age,
            "conditions": self.conditions,
            "vitals": self.vitals,
            "new_variables": self.new_variables,
            "last_activity": self.activity_log[-1] if self.activity_log else None
        }
    def simulate_motion_reading(self):
        """ Simulate motion sensor data for testing (Acc, Gyr, Euler angles).
        """
        return {
            "AccX": np.random.normal(0, 0.5),
            "AccY": np.random.normal(0, 0.5),
            "AccZ": np.random.normal(9.8, 0.5),  
            "GyrX": np.random.normal(0, 0.1),
            "GyrY": np.random.normal(0, 0.1),
            "GyrZ": np.random.normal(0, 0.1),
            "EulerX": np.random.normal(0, 1),
            "EulerY": np.random.normal(0, 1),
            "EulerZ": np.random.normal(0, 1),
        }
