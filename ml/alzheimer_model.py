"""Cognitive GAME demonstration classifier. Bundled data is not clinical evidence."""
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / 'ml/alz_model.joblib'


class AlzheimerModel:
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=150, max_depth=10, min_samples_split=5,
                                            class_weight='balanced', random_state=42)
        self.scaler = StandardScaler()
        self.features = ['memory_score', 'reaction_time', 'error_rate', 'sequence_accuracy',
                         'color_recognition', 'stroop_effect', 'attempts_per_minute',
                         'pattern_recognition', 'number_recall', 'quiz_score', 'quiz_accuracy']
        self.metadata = {'clinical_validation': False, 'data_source': 'bundled synthetic demonstration data',
                         'feature_version': 2}

    def prepare_data(self, raw_data):
        df = raw_data.copy()
        required = {'user_id', 'game', 'score', 'duration', 'attempts', 'accuracy'}
        if not required.issubset(df.columns):
            raise ValueError('Game data is missing required columns.')
        for col in ['score', 'duration', 'attempts', 'accuracy']:
            df[col] = pd.to_numeric(df[col], errors='raise')
            if not np.isfinite(df[col]).all() or (df[col] < 0).any():
                raise ValueError('Game data contains invalid numbers.')
        if (df['accuracy'] > 1).any():
            raise ValueError('Accuracy must be between zero and one.')
        df['game'] = df['game'].str.replace('-', '_')
        rows = []
        for user, group in df.groupby('user_id'):
            # Game point systems differ. Use normalized accuracy for both training and inference.
            scores = group.groupby('game')['accuracy'].mean().to_dict()
            rows.append({'user_id': user, 'memory_score': scores.get('memory', 0),
                         'reaction_time': group['duration'].mean(),
                         'error_rate': 1-group['accuracy'].mean(),
                         'sequence_accuracy': scores.get('sequence', 0),
                         'color_recognition': scores.get('color', 0),
                         'stroop_effect': scores.get('stroop', 0),
                         'attempts_per_minute': group['attempts'].sum()/max(1, group['duration'].sum()/60),
                         'pattern_recognition': scores.get('drag_shapes', 0),
                         'number_recall': scores.get('memory_numbers', 0),
                         'quiz_score': scores.get('quiz', 0), 'quiz_accuracy': scores.get('quiz', 0)})
        return pd.DataFrame(rows)

    def train(self, X, y):
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.2, stratify=y, random_state=42)
        self.model.fit(self.scaler.fit_transform(X_train), y_train)
        predictions = self.model.predict(self.scaler.transform(X_test))
        self.metadata['evaluation'] = {
            'accuracy': float(accuracy_score(y_test, predictions)),
            'classification_report': classification_report(y_test, predictions, output_dict=True, zero_division=0),
            'confusion_matrix': confusion_matrix(y_test, predictions).tolist(),
            'train_users': len(X_train), 'test_users': len(X_test)}
        return self

    def predict(self, user_data):
        X = pd.DataFrame([{f: user_data.get(f, 0) for f in self.features}])
        if not np.isfinite(X.to_numpy(dtype=float)).all():
            raise ValueError('Invalid cognitive features.')
        probabilities = self.model.predict_proba(self.scaler.transform(X))[0]
        index = int(np.argmax(probabilities))
        label = int(self.model.classes_[index])
        return {'risk_level': {0: 'Low', 1: 'Medium', 2: 'High'}.get(label, 'Unknown'),
                'probability': float(probabilities[index]), 'demo_only': True,
                'key_factors': {'memory': user_data.get('memory_score', 0),
                                'processing_speed': user_data.get('reaction_time', 0),
                                'error_rate': user_data.get('error_rate', 0)}}

    def save(self, filepath=MODEL_PATH):
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({'model': self.model, 'scaler': self.scaler, 'features': self.features,
                     'metadata': self.metadata}, filepath)
        filepath.with_suffix('.metadata.json').write_text(json.dumps(self.metadata, indent=2), encoding='utf-8')

    @classmethod
    def load(cls, filepath=MODEL_PATH):
        if not Path(filepath).exists():
            raise FileNotFoundError('Run python -m ml.alzheimer_model to build the demonstration model.')
        data = joblib.load(filepath)
        if data.get('metadata', {}).get('feature_version') != 2:
            raise ValueError('Retrain the model with the current feature pipeline.')
        model = cls()
        model.model, model.scaler = data['model'], data['scaler']
        model.features, model.metadata = data['features'], data['metadata']
        return model


def train_new_model(csv_path=None, save_path=MODEL_PATH):
    path = Path(csv_path) if csv_path else ROOT / 'data/balanced_alzheimer_data.csv'
    df = pd.read_csv(path)
    if 'label' not in df or df.groupby('user_id')['label'].nunique().max() != 1:
        raise ValueError('Each user must have one consistent label; labels will not be fabricated.')
    model = AlzheimerModel()
    features = model.prepare_data(df)
    labels = df.groupby('user_id')['label'].first().reindex(features['user_id']).astype(int)
    if not set(labels.unique()).issubset({0, 1, 2}) or labels.nunique() < 2:
        raise ValueError('Expected at least two risk classes labelled 0, 1, or 2.')
    model.metadata['training_file'] = path.name
    model.train(features[model.features], labels.to_numpy())
    model.save(save_path)
    return True, 'Demonstration model saved. This model is not clinically validated.'


if __name__ == '__main__':
    print(train_new_model()[1])
