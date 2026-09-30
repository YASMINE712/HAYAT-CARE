class SummarizerAgent:
    def __init__(self, alert_system=None):
        self.alert_system = alert_system

    def _generate_summary(self, observations=None):
        if not observations:
            return 'No monitoring observations supplied. A health or delivery status cannot be inferred.'
        prefix = 'Demonstration readings only. ' if observations.get('simulated') else ''
        return (prefix + f"Health model: {observations.get('health', 'unavailable')}. "
                f"Phone monitoring: {observations.get('fall', 'unavailable')}.")

    def run(self, observations=None):
        return self._generate_summary(observations)
