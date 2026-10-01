# HayatCare in pictures

Screenshots captured from the running application using a separate demo account.
The medication example is illustrative. No personal patient records are shown.

## Welcome & sign-in

![Welcome page](screenshots/welcome.png)

![Sign-in page](screenshots/sign-in.png)

## Daily care

![Daily care tools](screenshots/daily-care.png)

## Brain activities

![Seven brain activities and difficulty indicators](screenshots/brain-activities.png)

![Count and find activity in progress](screenshots/game-in-action.png)

## Personal progress

The new demo account shows the starting view; performance history builds as activities are completed.

![Personal progress starting view](screenshots/progress.png)

## Medication program

![Medication schedule with daily record progress](screenshots/medication-program.png)

## Mobile view

<img src="screenshots/mobile-activities.png" alt="Brain activities on a mobile-sized screen" width="390">

## YOLO deep-learning detection

The image below shows **YOLOv8n running through HayatCare's upload-and-analyze flow**.
The input is an existing demonstration image in the project, not a patient upload.
Boxes and confidence scores come from the model's actual predictions, using a
confidence threshold above 50%. The pretrained model recognizes object classes;
these labels are not a complete home-safety assessment.

![Actual YOLO detection inside HayatCare](screenshots/yolo-detection.png)

[View the detected classes, bounding boxes, and confidence scores](screenshots/yolo-results.json).

## Supervised ML example

The cardiovascular pipeline was run with illustrative measurements entered through
the app. This screenshot shows the model's actual output for those demo inputs,
not a real person's health assessment.

![Cardiovascular model output for demo inputs](screenshots/heart-model-demo.png)

## Automated tests

**49 tests passed**, including a real YOLO upload-and-inference test. The image below renders the captured output of the Python test runner.
Coverage includes activity scoring, personal progress, medication schedules, reminders,
phone motion events, authentication, and account isolation.

![Captured automated test output](screenshots/automated-tests.png)

[Read the original text output](screenshots/test-results.txt).
