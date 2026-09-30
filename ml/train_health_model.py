"""Rebuild the health demonstration model with the installed dependency versions."""
from pathlib import Path
import json
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report


def train_health_model():
    root=Path(__file__).resolve().parents[1]
    df=pd.read_csv(root/'data/health_monitoring.csv')
    df.columns=df.columns.str.strip()
    df=df.rename(columns={'Heart Rate':'heart_rate','Blood Pressure':'blood_pressure',
                         'Glucose Levels':'glucose','Oxygen Saturation (SpO₂%)':'oxygen',
                         'Alert Triggered (Yes/No)':'alert'})
    bp=df['blood_pressure'].str.extract(r'(?P<systolic_bp>\d+)/(?P<diastolic_bp>\d+)')
    df=pd.concat([df,bp],axis=1)
    columns=['heart_rate','systolic_bp','diastolic_bp','glucose','oxygen']
    for col in columns:df[col]=pd.to_numeric(df[col],errors='coerce')
    df['alert']=df['alert'].map({'Yes':1,'No':0})
    df=df.dropna(subset=columns+['alert'])
    X_train,X_test,y_train,y_test=train_test_split(df[columns],df['alert'],test_size=.2,stratify=df['alert'],random_state=42)
    model=make_pipeline(StandardScaler(),LogisticRegression(max_iter=1000))
    model.fit(X_train,y_train)
    joblib.dump(model,root/'ml/health_pipeline.joblib')
    metadata={'clinical_validation':False,'source':'bundled health_monitoring.csv; provenance not verified',
              'train_rows':len(X_train),'holdout_rows':len(X_test),
              'classification_report':classification_report(y_test,model.predict(X_test),output_dict=True,zero_division=0)}
    (root/'ml/health_pipeline.metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print('Health demonstration model rebuilt; original legacy artifact retained.')


if __name__=='__main__':
    train_health_model()
