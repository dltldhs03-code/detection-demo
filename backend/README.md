# Jetson Nano Detection Demo Backend

This is a simple Flask backend for testing remote object detection communication.

It receives fake detection data from any PC and stores the latest result in memory.
The frontend can then read the latest result from `/api/latest`.

This demo does not use YOLO, torch, ultralytics, numpy, or opencv.

## Folder

```text
detection-demo/backend/
  main.py
  requirements.txt
  README.md
```

## API Routes

### `GET /`

Returns a message that the backend is running.

### `GET /health`

Returns:

```json
{
  "status": "ok"
}
```

### `POST /api/detection`

Receives detection data.

Example request body:

```json
{
  "class_name": "car",
  "confidence": 0.93,
  "bbox": [100, 120, 300, 400]
}
```

The server automatically adds a UTC timestamp and stores the result as the latest detection.

Example response:

```json
{
  "status": "ok",
  "data": {
    "class_name": "car",
    "confidence": 0.93,
    "bbox": [100, 120, 300, 400],
    "timestamp": "2026-05-08T12:00:00.000000+00:00"
  }
}
```

### `GET /api/latest`

Returns the latest detection result.

If no detection has been sent yet:

```json
{
  "data": null
}
```

## Run Locally

From this `backend` folder:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

The local backend will run at:

```text
http://localhost:5000
```

## Test Locally With curl

```bash
curl http://localhost:5000/health
```

```bash
curl -X POST http://localhost:5000/api/detection \
  -H "Content-Type: application/json" \
  -d '{"class_name":"car","confidence":0.93,"bbox":[100,120,300,400]}'
```

```bash
curl http://localhost:5000/api/latest
```

## Deploy to Railway

1. Push this project to GitHub.
2. Go to Railway.
3. Create a new project from your GitHub repository.
4. Set the Railway service root directory to:

```text
detection-demo/backend
```

5. Railway should install dependencies from `requirements.txt`.
6. Set the start command to:

```bash
gunicorn main:app --bind 0.0.0.0:$PORT
```

7. Deploy the service.
8. Copy your Railway public URL. It will look similar to:

```text
https://your-railway-backend-url.up.railway.app
```

## Remote Communication Flow

```text
fake detection sender PC -> Railway backend -> Vercel frontend viewer PC
```

Because Railway and Vercel are public cloud services, the sender PC and viewer PC can be on different networks.
