def explain_health_risk(vitals, prediction):
    if prediction == 0:
        return "Aucun risque immédiat détecté selon les signes vitaux actuels."

    reasons = []
    if vitals.get("systolic_bp", 0) > 140:
        reasons.append("hypertension")
    if vitals.get("heart_rate", 0) > 100:
        reasons.append("tachycardie")
    if vitals.get("glucose", 0) > 180:
        reasons.append("hyperglycémie")
    if vitals.get("oxygen", 100) < 90:
        reasons.append("hypoxie")
    if vitals.get("temperature", 36.6) > 38:
        reasons.append("fièvre")

    if reasons:
        return "Risque immédiat dû à : " + ", ".join(reasons)
    else:
        return "Risque immédiat détecté sans cause évidente dans les données."

def explain_chd_risk(pred, context):
    prob = pred.get("probability", 0.0)
    category = pred.get("risk_category", "Inconnu")
    reasons = []

    age = context.get("age", 0)
    systolic = context.get("vitals", {}).get("systolic", 0)
    glucose = context.get("vitals", {}).get("glucose", 0)

    if age > 60:
        reasons.append("âge avancé")
    if systolic > 140:
        reasons.append("pression artérielle élevée")
    if glucose > 150:
        reasons.append("glycémie élevée")

    return f"Risque {category} ({round(prob * 100, 1)}%) dû à : " + ", ".join(reasons)

def explain_fall_risk(label, vitals):
    reasons = []

    if vitals.get("systolic_bp", 999) < 100:
        reasons.append("hypotension")
    if vitals.get("heart_rate", 999) < 60:
        reasons.append("bradycardie")
    if vitals.get("oxygen", 100) < 92:
        reasons.append("hypoxie")
    if vitals.get("temperature", 36.6) > 38:
        reasons.append("état fébrile")

    explanation = "Fall detected. Possibles causes : " + ", ".join(reasons) if reasons else "Fall detected. Aucune anomalie critique détectée."
    return explanation