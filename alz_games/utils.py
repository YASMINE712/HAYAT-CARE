def normalize_score(score, max_score=100):
    return round((score / max_score) * 100, 2)

def time_penalty_adjustment(duration, threshold=60):
    if duration <= threshold:
        return 0
    return min(10, (duration - threshold) * 0.1)