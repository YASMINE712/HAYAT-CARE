# HayatCare

Flask elderly-care prototype with phone motion monitoring, persistent reminders,
cognitive games, a Gemini assistant, optional room object detection, and research
health models. The maintained application is Flask. The files under `pages/`
are compatibility links from the earlier Streamlit prototype.

## Start on this computer

The repaired `.venv` uses Python 3.12. The older `venv` directory is retained but
points to a Python installation that no longer exists.

Open PowerShell in this project folder and run:

```powershell
.\.venv\Scripts\python.exe run.py
```

Open http://localhost:5000. `run.py` starts both the web server and the scheduling
worker. `python app.py` also starts both. Keep the process and computer running
for scheduled reminders and pending fall alerts. Closing the browser does not
stop the scheduler; stopping the server does.

For a new machine with Python 3.12 installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m ml.alzheimer_model
.\.venv\Scripts\python.exe -m ml.train_chd_model
.\.venv\Scripts\python.exe -m ml.train_health_model
.\.venv\Scripts\python.exe run.py
```

The application uses `data/hayatcare.sqlite3`. Existing users are imported from
`data/users.csv` on startup. Their passwords are hashed in SQLite and in that
legacy CSV; usernames/passwords remain usable. Duplicate legacy usernames import
the first account. Legacy datasets, model files, and game-result CSVs are retained.
New assessment results are stored in SQLite per account and assessment; old CSV
results remain in their original file and are not mixed into a new assessment.
Old browser-only reminders must be recreated in the account reminder screen.

## Phone fall monitoring

1. Serve this application through a **trusted HTTPS address** reachable by the
   phone, using a TLS reverse proxy. Keep the Python server on localhost behind
   that proxy. Set `COOKIE_SECURE=1` in `.env` when using HTTPS. Plain HTTP to a
   laptop's LAN IP is not sufficient for phone sensor permission.
2. Open that address on the older adult's Android phone or iPhone and sign in.
3. Open **Phone fall monitoring**, optionally enable caregiver messages, and tap
   **Start monitoring**. Grant motion permission if the browser asks.
4. Carry the phone securely on the body, with the page visible and phone unlocked.
   The page requests a screen wake lock when available. Browser/device support
   varies. If readings stop or no sensors are available, the UI reports it.
5. A possible fall starts a **20-second cancellation countdown**. Tap **I'm okay**
   to cancel before the deadline, or explicitly request a caregiver alert now.
6. Review actual events and provider acceptance status under **Fall event history**.

The implementation uses acceleration **including gravity**, in m/s², sampled at
approximately 10 Hz. The heuristic looks for acceleration below 3 m/s², an impact
above 25 m/s² within 1.5 seconds, then about 2 seconds of stillness within 6 seconds.
It rejects stale, malformed, out-of-order, and replayed samples and resets after
sensor gaps. Server-side state is per account; starting another phone supersedes
the previous phone connection. A 60-second detector cooldown limits repeated
events in a continuous monitoring session.

**This is experimental, not a validated fall alarm.** Dropping the phone can
trigger it; some falls will be missed. Do not test by deliberately falling.
Background tabs, navigation, phone locking, network loss, or revoked permission
can interrupt monitoring. The page stops on hiding and the server marks missing
heartbeats inactive. A pending countdown already recorded on the server continues
even if the page closes; cancellation must reach the server before the deadline.
The heuristic has only been tested with synthetic traces, not physical falls.

Reliable monitoring with the phone locked requires a separately developed native
Android/iOS application and on-device validation. The bundled legacy LSTM is kept
separate because its original sensor units, sampling, and preprocessing were not
documented well enough to apply it to phone readings safely.

Browser API references:
- [Motion permissions](https://developer.mozilla.org/en-US/docs/Web/API/DeviceMotionEvent/requestPermission_static)
- [Acceleration including gravity](https://developer.mozilla.org/en-US/docs/Web/API/DeviceMotionEvent/accelerationIncludingGravity)

## External services

Use `.env.example` as the settings reference. Do not overwrite an existing `.env`
with empty example values.

- **Gemini:** set `GEMINI_API_KEY` and a `GEMINI_MODEL` currently enabled for your
  Google project. The app uses REST `generateContent` and passes the actual user
  question. Patient information included in a request is sent to Google when
  the user submits a question or requests a scenario report.
- **WhatsApp:** set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and
  `TWILIO_WHATSAPP_FROM`, and save an E.164 caregiver number in **Edit profile**.
  A Twilio sandbox requires the recipient to join it. Production WhatsApp sender,
  recipient opt-in, and template/session requirements must be configured with
  Twilio. For messages outside the customer-service window, set
  `TWILIO_WHATSAPP_CONTENT_SID` to an approved template containing one variable,
  `{{1}}`, into which the alert text is inserted, and configure
  `TWILIO_MESSAGING_SERVICE_SID` for that sender. Without the template setting, the app
  sends a free-form message, which may be rejected outside the allowed session.
  See [Twilio's sandbox guide](https://www.twilio.com/docs/whatsapp/quickstart) and
  [template-message requirements](https://www.twilio.com/docs/whatsapp/tutorial/send-whatsapp-notification-messages-templates).
- **Room photos:** install `requirements-vision.txt` for YOLO/OpenCV. The bundled
  `yolov8n.pt` remains the weights file. This optional heavy dependency set was not
  installed or exercised during the core repair. Uploaded images are private to
  their account; filenames are generated by the server.

Credentials previously embedded in source have been removed. **Revoke/rotate the
old Gemini and Twilio credentials in their provider consoles**, then place new
values in `.env`. Source cleanup cannot revoke an already-exposed credential.

Automatic messaging is opt-in. The worker claims a message once in SQLite before
contacting Twilio to reduce duplicates across workers. `queued` means provider
acceptance, not delivery to the caregiver. Failed/unconfigured/uncertain delivery
is shown honestly. If a process crashes during sending, the status can remain
`sending`; inspect Twilio before retrying because acceptance may have occurred.
There is no automatic retry after an ambiguous outcome. No real messages were
sent during the repair tests.

## Models and data boundaries

### Brain activities and personal progress

Open **Menu → Brain activities**. Seven games now have five levels (Gentle to
Advanced), five rounds per session, large controls, hints, pause, and optional
read-aloud instructions. Two strong unassisted sessions suggest a harder level;
two low sessions suggest an easier one. Users can choose any level themselves.
Completed sessions persist per account. Earlier game protocols and synthetic
training records are excluded from this new baseline.

**My progress** compares the same game and level across calendar days. Assisted
sessions remain visible but do not enter unassisted comparisons. Each day has
equal weight. Trends require six days spanning at least a week; two of the last
three days must differ from the earlier median by at least 15 percentage points
to report improving or lower recent performance. These are descriptive prototype
thresholds, not clinically validated measures of forgetting.

`ml/cognitive_progress.py` fits an actual Isolation Forest to the user's earlier
accuracy and response times after 12 baseline days plus three recent days exist
at that game and level. The scaler and model fit only the earlier observations.
No fabricated personal history is used. ML highlights unusual performance, not
dementia. Deep learning was not added: there is no suitable validated longitudinal
training dataset here. Download the personal history from the progress page.

### Medication programs

Open **Menu → Medication program** and copy the prescribed name, dose, instructions,
dates, weekdays, times, and timezone. Programs support up to eight daily times,
editing, pausing reminders, a printable page, self-reported taken/skipped records,
and ten-minute alert snoozes. Pausing reminders does not change a prescription.
Past records retain their original medication details when a program changes.

The persistent worker generates dose occurrences and handles due reminders while
the server runs. Keep the computer awake. An open signed-in page displays due
alerts; browser notifications require explicit browser permission and an open
page. Optional caregiver WhatsApp reminders/follow-ups require the profile contact
and configured Twilio credentials. Delivery status is displayed; provider acceptance
does not establish delivery. No prescription or caregiver messaging is enabled
automatically. An unconfirmed dose is not proof of a missed dose, and an overdue
follow-up never recommends an extra dose. Follow clinician/pharmacist advice for
missed doses.

Times follow each program's timezone: a missing DST time shifts forward by the
clock change, and a repeated time creates one occurrence. Snoozing changes the
alert time, not the prescription or confirmation window. Review timezone changes
with a clinician when traveling. The screen shows the past seven days and upcoming
week; older records remain in SQLite.

Educational references: [NIA memory changes](https://www.nia.nih.gov/health/memory-loss-and-forgetfulness/memory-forgetfulness-and-aging-whats-normal-and-whats-not)
and [NIA medication safety](https://www.nia.nih.gov/health/medicines-and-medication-management/taking-medicines-safely-you-age).

### Retained research demonstrations

- `ml/alz_model.joblib`: a rebuilt random forest on the bundled **synthetic**
  cognitive dataset. Training/inference use normalized accuracy consistently;
  a single user is never split across train and holdout. The scaler is fitted on
  training data only. Multiclass evaluation and model metadata are saved. Complete
  the legacy assessment to see the demonstration category. The new activities
  do not use this synthetic disease classifier. Missing
  results/models do not produce fabricated scores or confidence values.
- `ml/chd_pipeline.joblib`: a rebuilt research CHD pipeline. Candidate selection
  uses cross-validation on the training split; the holdout is evaluated only after
  selection. The UI requires entered measurements/history, not random sex,
  smoking status, or fabricated patient characteristics.
- `ml/health_pipeline.joblib`: rebuilt health demonstration pipeline using the
  installed library version. Dashboard vital signs remain explicitly **simulated**.
- `ml/*.metadata.json`: dataset provenance notes, split sizes, and development
  evaluation. These metrics are not clinical validation. Source provenance for
  the CHD and health datasets has not been verified.

Original `.pkl`/`.h5` files are retained. There is no live heart-rate, blood-pressure,
glucose, or oxygen sensor integration. The phone supplies motion data only. No
model in this repository establishes a clinical diagnosis or treatment decision.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Tests use temporary databases and fake messaging senders, never real caregivers.
The updated suite passes 48 automated tests. The earlier environment repair also
passed `pip check`.
Coverage includes sensor gaps and invalid data, detector state across requests,
cancellation/timeout, duplicate worker claims, account isolation, password
migration, CSRF, timezone-aware recurring reminders, assessment saving, model
inference, Eldora question forwarding, and page rendering.

The interface was also exercised in a mobile-sized Edge browser with synthetic
motion events: readings → server detection → countdown → cancellation → persisted
history, plus reminder creation, profile editing, and game-page navigation.
New mobile-browser checks cover all seven adaptive game interfaces, a completed
session, pause/hint controls, personal progress, and medication creation, editing,
and pause/resume. New automated checks cover dose deduplication, late confirmations,
snooze, timezone transitions, account isolation, server scoring, history persistence,
and longitudinal/ML baseline requirements.
Physical Android/iPhone sensors, real WhatsApp delivery, Gemini responses, and
optional YOLO inference still require integration testing with configured services.

## Deployment notes

This remains a development prototype. Use trusted HTTPS before phone access.
Protect the SQLite database, `.env`, datasets, and upload folder with appropriate
host permissions and backups. They are not encrypted at rest. Patient data is held
server-side; the browser receives only an opaque HttpOnly session cookie. User
mutations require a CSRF token, and upload paths are account-specific. Additional
production operations, abuse controls, monitoring, and mobile/clinical validation
remain outside the scope of this repair.
