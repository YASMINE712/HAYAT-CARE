"""Explicit dependency injection; missing monitors are reported as unavailable."""
from ml.health_monitor import HealthMonitor
from ml.summarizer_agent import SummarizerAgent


class Orchestrator:
    def __init__(self, patient, house=None, health_model=None, safety_monitor=None,
                 reminder_agent=None, chd_predictor=None):
        self.patient, self.house = patient, house
        self.health_monitor = HealthMonitor(patient, health_model) if health_model is not None else None
        self.safety_monitor = safety_monitor
        self.reminder_agent = reminder_agent
        self.chd_predictor = chd_predictor

    def run_all_agents(self, motion=None, chd_data=None):
        health = self.health_monitor.run() if self.health_monitor else None
        fall = self.safety_monitor.run(real_data=motion) if self.safety_monitor else None
        if self.reminder_agent:
            self.reminder_agent.run()
        chd = self.chd_predictor.predict(chd_data) if self.chd_predictor and chd_data else None
        observations = {'health': 'Unavailable' if health is None else ('High' if health else 'Normal'),
                        'fall': self.safety_monitor.last_label if self.safety_monitor else 'No sensor data',
                        'simulated': True}
        return {'health': health, 'fall': fall, 'chd': chd,
                'summary': SummarizerAgent().run(observations)}
