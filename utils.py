"""Optional vision and Gemini integrations, loaded only when used."""
import os
import re
from functools import lru_cache
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def yolo_model():
    from ultralytics import YOLO
    weights = ROOT / 'yolov8n.pt'
    if not weights.exists():
        raise RuntimeError('Local YOLO weights are missing.')
    return YOLO(str(weights))


def detect_objects_yolo_with_boxes(image_path, original_filename):
    import cv2
    image = cv2.imread(image_path)
    if image is None or image.size > 60_000_000:
        raise ValueError('Invalid or oversized image.')
    model = yolo_model()
    result = model(image, verbose=False)[0]
    detections = []
    for box in result.boxes:
        confidence = float(box.conf[0])
        if confidence <= .5:
            continue
        label = model.names[int(box.cls[0])]
        coordinates = list(map(int, box.xyxy[0].tolist()))
        detections.append({'name': label, 'box': coordinates, 'confidence': round(confidence,4)})
        x1, y1, x2, y2 = coordinates
        cv2.rectangle(image, (x1, y1), (x2, y2), (255, 165, 0), 2)
        cv2.putText(image, f'{label} {confidence:.2f}', (x1, max(20, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, .6, (255,255,255), 2)
    annotated = 'annotated_'+Path(original_filename).name
    if not cv2.imwrite(str(Path(image_path).parent / annotated), image):
        raise RuntimeError('Unable to save annotated image.')
    return detections, annotated


def call_gemini_api(prompt_text, api_key=None):
    key = api_key or os.getenv('GEMINI_API_KEY')
    model = os.getenv('GEMINI_MODEL')
    if not key or not model:
        return 'Eldora is not configured. Set GEMINI_API_KEY and GEMINI_MODEL on the server.'
    if not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        return 'Invalid Gemini model configuration.'
    try:
        response = requests.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                                 headers={'x-goog-api-key': key},
                                 json={'contents': [{'parts': [{'text': prompt_text}]}],
                                       'generationConfig': {'temperature': .3, 'maxOutputTokens': 2000}}, timeout=30)
        if not response.ok:
            return f'Eldora service unavailable (HTTP {response.status_code}). Check server model and API configuration.'
        parts = response.json()['candidates'][0]['content']['parts']
        return '\n'.join(part.get('text', '') for part in parts)
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return 'Eldora could not complete the request. Please try again later.'
