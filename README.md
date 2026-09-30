# HayatCare

**An intelligent daily-care companion for older adults and caregivers.**

HayatCare brings cognitive activities, medication routines, phone motion monitoring,
and a conversational assistant into one accessible web application.

![HayatCare daily care dashboard](docs/screenshots/daily-care.png)

[View the page gallery and test results](docs/SCREENSHOTS.md).

## What you can do

- **Train your mind:** seven memory, attention, and reasoning games with five difficulty levels, hints, and adaptive level suggestions.
- **Follow your progress:** compare performance across days, view progress bars, and export your activity history.
- **Organize medication:** create prescribed schedules with reminders, dose confirmations, snooze, and optional caregiver alerts.
- **Stay connected:** use phone motion monitoring and review possible-fall events with caregiver notifications.
- **Explore your care:** manage a personal profile, talk to Eldora, and review room photos with optional object detection.

## ML, deep learning & data

| Technique | Application |
|---|---|
| Isolation Forest | Learns personal accuracy and response-time patterns from previous sessions to identify unusual recent performance. |
| Longitudinal analysis | Compares daily results at the same game and difficulty; separates assisted sessions and gives each day equal weight. |
| Supervised learning | Includes cognitive classification and cardiovascular/health modeling pipelines with preprocessing, training splits, and evaluation. |
| YOLOv8 · optional deep learning | Detects objects in room photos to support home-safety exploration. |
| Sensor time-series processing | Processes phone acceleration with temporal windows, motion thresholds, and event cooldowns. |
| Gemini integration | Powers contextual conversations with Eldora. |

Built with **Python, Flask, SQLite, scikit-learn, NumPy, pandas, JavaScript**, and optional **Ultralytics YOLO**.
The app supports everyday care and activity tracking; its insights are not medical diagnoses.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe run.py
```

Open **http://localhost:5000**. Add your service credentials to `.env` when enabling Gemini or WhatsApp.
Core activities, personal progress, and medication schedules use the local database.

## Project structure

`app.py` · web application  
`cognitive.py` / `ml/` · activities and ML pipelines  
`medications.py` / `worker.py` · schedules and reminders  
`templates/` / `static/` · responsive interface  
`tests/` · automated checks

Model weights, datasets, personal records, uploads, and credentials are excluded from Git.
Training code stays available; supply the datasets described in [setup notes](docs/SETUP.md) to rebuild optional model artifacts.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
