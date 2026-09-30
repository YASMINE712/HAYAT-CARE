from utils import call_gemini_api

def run_scenario(scenario):
    risk_score = calculate_base_risk(scenario['patient'])
    patient_profile = format_patient_profile(scenario['patient'])
    environment = format_environment(scenario['house'])
    events = format_events(scenario.get('events', []))
    activity = scenario.get('activity', 'general movement')
    time = scenario.get('time', 'day')

    prompt = f"""
# Comprehensive Elderly Safety Simulation Report

## Patient Risk Profile (Score: {risk_score}/10)
{patient_profile}

## Living Environment Scan
{environment}

## Simulation Parameters
- **Activity:** {activity}
- **Time:** {time}
- **Special Conditions:** {events}

---

### 1. Risk Assessment Breakdown
- List 3-5 most critical hazards specific to this combination of patient and environment.
- Explain how each patient factor interacts with environmental elements.

### 2. Immediate Recommendations (within 48 hours)
- Top 3 priority actions to reduce fall risk.
- Environmental modifications needed within next 48 hours.

### 3. Long-term Safety Plan
- Suggested assistive technologies.
- Recommended home modifications.
- Caregiver training points.

### 4. Emergency Preparedness
- Specific precautions for the described scenario.
- Backup safety measures.

**Identify missing data and uncertainty. This is a text scenario analysis, not a physical simulation or a diagnosis.**
**Format your response using markdown with clear sections and bullet points.**
**Include estimated implementation difficulty (Easy/Medium/Hard) for each recommendation.**
"""
    return call_gemini_api(prompt)

def format_patient_profile(patient_data):
    def safe(val):
        return val if val and val != 'unknown' else 'Not specified'
    profile = []
    profile.append(f"- Mobility: {safe(patient_data.get('mobility'))}")
    profile.append(f"- Vision: {safe(patient_data.get('vision'))}")
    profile.append(f"- Cognitive: {safe(patient_data.get('cognitive'))}")
    meds = patient_data.get('medications')
    if isinstance(meds, list):
        meds_str = ', '.join(meds) if meds else 'None'
    else:
        meds_str = meds if meds else 'None'
    profile.append(f"- Medications: {meds_str}")
    profile.append(f"- Fall History: {'Yes' if patient_data.get('fall_history', False) else 'No'}")
    return "\n".join(profile)

def format_environment(house_data):
    if not house_data:
        return "- No environment data available"
    
    environment = []
    for room, objects in house_data.items():
        environment.append(f"- {room.capitalize()}: {', '.join(objects) if objects else 'Empty'}")
    return "\n".join(environment)

def format_events(events):
    return ', '.join(events) if events else 'None'

def calculate_base_risk(patient_data):
    """Calculate a basic risk score (1-10) based on patient factors"""
    if not patient_data:
        return 3
    
    score = 0
    
    # Mobility scoring
    mobility_scores = {'normal': 0, 'limited': 2, 'wheelchair': 3}
    score += mobility_scores.get(patient_data.get('mobility', 'normal'), 0)
    
    # Vision scoring
    vision_scores = {'normal': 0, 'impaired': 1, 'legally_blind': 2}
    score += vision_scores.get(patient_data.get('vision', 'normal'), 0)
    
    # Cognitive scoring
    cognitive_scores = {
        'normal': 0, 
        'mild_decline': 1, 
        'moderate_decline': 2, 
        'severe_decline': 3
    }
    score += cognitive_scores.get(patient_data.get('cognitive', 'normal'), 0)
    
    # Medications (0.5 point per medication, max 2)
    score += min(len(patient_data.get('medications', [])) * 0.5, 2)
    
    # Fall history
    if patient_data.get('fall_history', False):
        score += 2
    
    # Cap at 10
    return min(int(score) + 1, 10)  # +1 to ensure minimum risk is 1
