"""Experimental phone heuristic, separate from the uncalibrated legacy LSTM.

Input: acceleration INCLUDING gravity, m/s², sampled at about 10 Hz.
A low-gravity phase followed by impact and sustained stillness is a POSSIBLE
fall, never a diagnosis. Dropping a phone can produce the same pattern.
"""
import math


class PhoneFallDetector:
    def __init__(self, state=None):
        self.state = state or {'phase': 'idle', 'last_ts': 0, 'cooldown': 0}

    def feed(self, sample):
        ts = sample['t']
        values = [sample[k] for k in ('x', 'y', 'z', 't')]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise ValueError('Motion samples must contain finite numbers.')
        if any(abs(sample[k]) > 200 for k in ('x', 'y', 'z')):
            raise ValueError('Acceleration outside supported range.')
        s = self.state
        if ts <= s['last_ts']:
            raise ValueError('Motion timestamps must increase.')
        gap = ts - s['last_ts']
        if gap > 1500:
            s['phase'] = 'idle'
        s['last_ts'] = ts
        magnitude = math.sqrt(sum(sample[k] ** 2 for k in ('x', 'y', 'z')))
        s['magnitude'] = round(magnitude, 2)
        if ts < s.get('cooldown', 0):
            return None
        if s['phase'] == 'idle':
            if magnitude < 3:
                s.update(phase='falling', started=ts)
        elif s['phase'] == 'falling':
            if ts - s['started'] > 1500:
                s['phase'] = 'idle'
            elif magnitude > 25:
                s.update(phase='impact', impact=ts, peak=magnitude, still_since=None,
                         previous=[sample[k] for k in ('x', 'y', 'z')])
        elif s['phase'] == 'impact':
            vector = [sample[k] for k in ('x', 'y', 'z')]
            delta = math.sqrt(sum((a-b)**2 for a, b in zip(vector, s['previous'])))
            s['previous'] = vector
            s['peak'] = max(s['peak'], magnitude)
            if ts - s['impact'] > 6000:
                s['phase'] = 'idle'
            elif abs(magnitude - 9.81) < 2 and delta < 1.5:
                if s['still_since'] is None:
                    s['still_since'] = ts
                elif ts - s['still_since'] >= 2000:
                    evidence = {'peak_m_s2': round(s['peak'], 2), 'still_ms': ts-s['still_since'],
                                'method': 'phone_heuristic_v1', 'sample_time': ts}
                    s.update(phase='idle', cooldown=ts+60000)
                    return evidence
            else:
                s['still_since'] = None
        return None
