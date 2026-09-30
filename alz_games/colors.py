def evaluate_color(score, attempts, duration):
    if score >= 80 and duration <= 30:
        return "Excellent color reflex"
    elif score >= 60:
        return "Good color recognition"
    elif score >= 40:
        return "Moderate response"
    else:
        return "Weak color decision"