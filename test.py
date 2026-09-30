import numpy as np
import pandas as pd
from faker import Faker
from datetime import datetime, timedelta
from scipy.stats import skewnorm

class AlzheimerDataGenerator:
    def __init__(self, num_users=100, sessions_per_user=15, random_seed=42):
        np.random.seed(random_seed)
        self.faker = Faker()
        self.games = ['memory', 'memory_numbers', 'color', 'drag_shapes', 'stroop', 'count', 'sequence']
        self.num_users = num_users
        self.sessions_per_user = sessions_per_user
        
    def _generate_performance_curve(self, n, baseline, trend, volatility):
        """Generate realistic performance trajectory"""
        x = np.arange(n)
        trend_line = x * trend
        noise = np.random.normal(0, volatility, n)
        performance = baseline + trend_line + noise
        return np.clip(performance, 0, 1)
    
    def _generate_user_metrics(self, user_id, is_high_risk):
        """Generate all sessions for one user"""
        sessions = []
        
        # Base characteristics based on risk
        if is_high_risk:
            baseline = {
                'memory': 0.4, 'memory_numbers': 0.35, 'color': 0.5,
                'drag_shapes': 0.45, 'stroop': 0.3, 'count': 0.5, 'sequence': 0.4
            }
            trends = np.random.uniform(-0.02, 0.01, len(self.games))  # Mostly declining
            error_rate = 0.6
            reaction_time = 80
        else:
            baseline = {
                'memory': 0.8, 'memory_numbers': 0.75, 'color': 0.85,
                'drag_shapes': 0.8, 'stroop': 0.7, 'count': 0.9, 'sequence': 0.75
            }
            trends = np.random.uniform(-0.005, 0.005, len(self.games))  # Stable
            error_rate = 0.2
            reaction_time = 35
        
        # Generate session data for each game type
        for game_idx, game in enumerate(self.games):
            n_sessions = max(1, int(self.sessions_per_user * skewnorm.rvs(5, loc=0.7, scale=0.2)))
            
            scores = self._generate_performance_curve(
                n_sessions,
                baseline[game],
                trends[game_idx],
                volatility=0.05 if not is_high_risk else 0.1
            )
            
            for i in range(n_sessions):
                session_date = datetime.now() - timedelta(days=(n_sessions - i) * np.random.uniform(1, 3))
                
                sessions.append({
                    'user_id': user_id,
                    'game': game,
                    'score': scores[i],
                    'attempts': int(np.random.choice([5,6,7,8,9,10,12,15], p=[0.05,0.1,0.15,0.2,0.2,0.15,0.1,0.05])),
                    'duration': reaction_time + np.random.uniform(-10, 15),
                    'accuracy': np.clip(1 - error_rate + np.random.normal(0, 0.1), 0.1, 1),
                    'timestamp': session_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'label': int(is_high_risk)
                })
        
        return sessions
    
    def generate(self):
        """Generate complete dataset"""
        data = []
        user_ids = [f"user_{1000 + i}" for i in range(self.num_users)]
        high_risk_users = set(np.random.choice(user_ids, int(self.num_users * 0.25), replace=False))
        
        for user_id in user_ids:
            user_sessions = self._generate_user_metrics(user_id, user_id in high_risk_users)
            data.extend(user_sessions)
        
        df = pd.DataFrame(data)
        
        # Add some missing data (5% of records) to simulate real-world data
        mask = np.random.choice([True, False], size=df.shape, p=[0.05, 0.95])
        df = df.mask(mask)
        
        return df.sort_values(['user_id', 'timestamp']).reset_index(drop=True)

# Usage example
if __name__ == "__main__":
    generator = AlzheimerDataGenerator(num_users=150, sessions_per_user=20)
    synthetic_data = generator.generate()
    
    # Save to CSV
    synthetic_data.to_csv('enhanced_alzheimer_data.csv', index=False)
    
    print(f"Generated {len(synthetic_data)} records")
    print("Risk distribution:")
    print(synthetic_data.groupby('user_id')['label'].first().value_counts())
    
    print("\nSample data:")
    print(synthetic_data.sample(10))