class AlertLevel:
    INFO = "INFO"
    WARNING = "WARNING"
    ALERT = "ALERT"
    EMERGENCY = "EMERGENCY"

class AlertSystem:
    def __init__(self):
        self.alerts = []

    def send_alert(self, message, level=AlertLevel.INFO):
        alert = f"[{level}] {message}"
        self.alerts.append(alert)
        print(alert)  # You can later log it, email it, or show it in UI
