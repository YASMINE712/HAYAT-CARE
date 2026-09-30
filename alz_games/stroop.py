def evaluate_stroop(score, attempts, duration):
    if score >= 85 and duration <= 30:
        return "Excellent cognitive flexibility"
    elif score >= 65:
        return "Good selective attention"
    elif score >= 45:
        return "Moderate attention control"
    else:
        return "Possible executive function impairment"