def evaluate_shapes(score, attempts, duration):
    if score >= 85:
        return "Excellent shape recognition"
    elif score >= 65:
        return "Good shape understanding"
    elif score >= 45:
        return "Moderate visual cognition"
    else:
        return "Visual pattern recognition difficulty"