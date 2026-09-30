def evaluate_sequence(score, attempts, duration):
    if score >= 75:
        return "Strong sequence recall"
    elif score >= 50:
        return "Acceptable sequence memory"
    else:
        return "Impaired sequence processing"