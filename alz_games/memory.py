def evaluate_memory(score, attempts, duration):
    if score >= 80 and attempts <= 10:
        return "Excellent memory"
    elif score >= 60:
        return "Good memory"
    elif score >= 40:
        return "Average memory"
    else:
        return "Possible memory decline"