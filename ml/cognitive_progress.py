"""Within-person longitudinal comparison and genuinely fitted anomaly detection.

No disease labels, no cross-level comparison, no inference from one low score.
"""
from datetime import date
from functools import lru_cache
import math
import statistics


def analyze_series(daily):
    result={'trend':'Building baseline','change_points':None,'message':'Complete unassisted sessions on at least six different days over a week at this level.',
            'ml_status':'Collecting history','ml_message':'Personal ML needs 12 baseline days plus 3 recent days at the same game and level.'}
    if len(daily)<6 or (date.fromisoformat(daily[-1]['date'])-date.fromisoformat(daily[0]['date'])).days<7:return result
    baseline=daily[:-3];recent=daily[-3:]
    base=statistics.median(row['accuracy'] for row in baseline)
    current=statistics.median(row['accuracy'] for row in recent)
    delta=current-base
    result['change_points']=round(delta*100,1)
    lower=sum(row['accuracy']<=base-.15 for row in recent)>=2
    higher=sum(row['accuracy']>=base+.15 for row in recent)>=2
    result['trend']='Lower recently' if lower else 'Improving' if higher else 'Similar / mixed'
    result['message']=(f'The median of your latest three days is {current:.0%}, compared with {base:.0%} across {len(baseline)} earlier days at this level. '
                       'This describes game performance, not a diagnosis. Tiredness, practice, mood, vision, and interruptions can affect scores.')
    if len(baseline)>=12:
        training=tuple((row['accuracy'],math.log1p(max(0,row['response_ms']))) for row in baseline[-90:])
        testing=tuple((row['accuracy'],math.log1p(max(0,row['response_ms']))) for row in recent)
        outliers=personal_outliers(training,testing)
        result['ml_status']='Unusual recent performance' if sum(outliers)>=2 else 'No repeated unusual pattern'
        result['ml_message']=(f'Compared with {len(training)} earlier days, {sum(outliers)} of your last 3 days showed an unusual pattern. '
                              'Your accuracy and response time help us understand your usual performance. These results are not a medical diagnosis.')
    return result


@lru_cache(maxsize=128)
def personal_outliers(training,testing):
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    scaler=StandardScaler().fit(training)
    model=IsolationForest(n_estimators=100,contamination='auto',random_state=42,n_jobs=1)
    model.fit(scaler.transform(training))
    return tuple(bool(value==-1) for value in model.predict(scaler.transform(testing)))
