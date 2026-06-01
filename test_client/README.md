# Fake Detection Test Client

This folder contains a simple Python script for sending fake object detection results to the Railway backend.

This simulates the future Jetson Nano sender.

No YOLO, torch, ultralytics, numpy, or opencv is used.

## Folder

```text
detection-demo/test_client/
  send_fake_detection.py
  send_yolo_detection.py
  README.md
```

## How It Works

The script sends random detection data:

- random `class_name` from `car`, `bus`, `truck`
- random `confidence` between `0.5` and `0.99`
- random `bbox` values

The backend adds the timestamp automatically.

## Install Dependency

From this `test_client` folder:

```bash
pip install requests
```

## Edit the Backend URL

Open `send_fake_detection.py` and edit this line:

```python
BACKEND_URL = "https://your-railway-backend-url.up.railway.app"
```

For local testing:

```python
BACKEND_URL = "http://localhost:5000"
```

For Railway:

```python
BACKEND_URL = "https://your-railway-backend-url.up.railway.app"
```

Do not add a trailing slash at the end of the URL.

## Send Fake Data

```bash
python send_fake_detection.py
```

Example output:

```text
Sending fake detection:
{'class_name': 'car', 'confidence': 0.82, 'bbox': [33, 91, 202, 244]}
Server status code: 200
Server response:
{'data': {'bbox': [33, 91, 202, 244], 'class_name': 'car', 'confidence': 0.82, 'timestamp': '2026-05-08T12:00:00.000000+00:00'}, 'status': 'ok'}
```

## curl Examples

### Local Backend

Health check:

```bash
curl http://localhost:5000/health
```

Send detection:

```bash
curl -X POST http://localhost:5000/api/detection \
  -H "Content-Type: application/json" \
  -d '{"class_name":"car","confidence":0.93,"bbox":[100,120,300,400]}'
```

Read latest detection:

```bash
curl http://localhost:5000/api/latest
```

### Railway Backend

Replace the URL with your real Railway backend URL:

```bash
curl https://your-railway-backend-url.up.railway.app/health
```

```bash
curl -X POST https://your-railway-backend-url.up.railway.app/api/detection \
  -H "Content-Type: application/json" \
  -d '{"class_name":"bus","confidence":0.88,"bbox":[50,80,260,360]}'
```

```bash
curl https://your-railway-backend-url.up.railway.app/api/latest
```

## Full Demo Flow

1. Deploy the Flask backend to Railway.
2. Deploy the Next.js frontend to Vercel.
3. Set Vercel environment variable:

```text
NEXT_PUBLIC_API_URL=https://your-railway-backend-url.up.railway.app
```

4. Run this test client from any PC.
5. Open the Vercel frontend from any other PC.

The browser should update with the latest fake detection result every 1 second.

## YOLO Sender From Another Laptop

Use `send_yolo_detection.py` when another laptop should act like the future Jetson Nano.

Install dependencies on the sender laptop only:

```bash
pip install requests opencv-python ultralytics
```

Run with a webcam:

```bash
python send_yolo_detection.py \
  --backend-url https://detection-demo-production.up.railway.app \
  --model yolov8n.pt \
  --source 0 \
  --interval 1.0
```

Run with a video file:

```bash
python send_yolo_detection.py \
  --backend-url https://detection-demo-production.up.railway.app \
  --model yolov8n.pt \
  --source ./sample.mp4 \
  --interval 1.0
```

Run with a custom trained model:

```bash
python send_yolo_detection.py \
  --backend-url https://detection-demo-production.up.railway.app \
  --model /path/to/best.pt \
  --source 0 \
  --device cpu
```

The script sends:

- `class_name`
- `confidence`
- `bbox`
- annotated JPEG frame

The Vercel dashboard displays the latest annotated frame when one is available.
