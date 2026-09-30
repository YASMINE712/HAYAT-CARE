def evaluate_counting(score, attempts, duration):
    if score >= 90:
        return "Excellent counting ability"
    elif score >= 70:
        return "Good counting"
    elif score >= 50:
        return "Satisfactory"
    else:
        return "Needs improvement in basic counting"