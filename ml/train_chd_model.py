"""Train using CV on training users; reserve the holdout for final evaluation."""
import json
from pathlib import Path
import joblib
import pandas as pd
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import average_precision_score, roc_auc_score
from ml.chd_predictor import NUMERIC, FLAGS, EDUCATION, MODEL_PATH


def train_chd_model():
    path = Path(__file__).resolve().parents[1] / 'data/chd_data.csv'
    df = pd.read_csv(path)
    df['education'] = df['education'].map(lambda x: EDUCATION.get(str(int(x))) if pd.notna(x) else np.nan)
    X, y = df[NUMERIC+FLAGS+['education']], df['TenYearCHD']
    X_train, X_test, y_train, y_test = train_test_split(X, y, stratify=y, test_size=.2, random_state=42)
    candidates = {'logistic':LogisticRegression(class_weight='balanced',max_iter=1500),
                  'random_forest':RandomForestClassifier(n_estimators=150,max_depth=8,class_weight='balanced',random_state=42)}
    scores, best_model, best_score = {}, None, -1
    for name, estimator in candidates.items():
        preprocess = ColumnTransformer([
            ('numeric',Pipeline([('fill',SimpleImputer(strategy='median')),('scale',StandardScaler())]),NUMERIC),
            ('categorical',Pipeline([('fill',SimpleImputer(strategy='most_frequent')),
                                     ('encode',OneHotEncoder(handle_unknown='ignore'))]),FLAGS+['education'])])
        pipeline = Pipeline([('preprocessor',preprocess),('classifier',estimator)])
        score = float(cross_val_score(pipeline,X_train,y_train,
                      cv=StratifiedKFold(n_splits=3,shuffle=True,random_state=42),scoring='average_precision').mean())
        scores[name] = score
        if score > best_score:
            best_model, best_score = pipeline, score
    best_model.fit(X_train,y_train)
    probabilities = best_model.predict_proba(X_test)[:,list(best_model.classes_).index(1)]
    metadata = {'clinical_validation':False,'source':'bundled chd_data.csv; provenance not verified',
                'training_rows':len(X_train),'holdout_rows':len(X_test),'cv_average_precision':scores,
                'holdout_average_precision':float(average_precision_score(y_test,probabilities)),
                'holdout_roc_auc':float(roc_auc_score(y_test,probabilities))}
    joblib.dump({'model':best_model,'metadata':metadata},MODEL_PATH)
    MODEL_PATH.with_suffix('.metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print('CHD research model saved; clinical validation is not established.')


if __name__=='__main__':
    train_chd_model()
