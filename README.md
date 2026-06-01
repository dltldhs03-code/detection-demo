# Detection Demo

CCTV 영상을 YOLO PC에서 분석하고, Railway 백엔드와 Vercel 프론트엔드를 통해 외부 인터넷에서 확인하는 대시보드입니다.

## Structure

```text
main/backend   Railway Flask backend
main/frontend  Vercel Next.js frontend
main/utils     YOLO PC detection pipeline
main/main.py   YOLO PC local runner
main/roi       ROI JSON files
```

## Deploy

Railway root directory:

```text
main/backend
```

Vercel root directory:

```text
main/frontend
```

Vercel environment variables:

```env
NEXT_PUBLIC_API_URL=https://your-railway-backend.up.railway.app
NEXT_PUBLIC_SHOW_OVERLAY=0
```

Railway environment variables:

```env
ITS_API_KEY=your_its_api_key
```

YOLO PC environment variables:

```env
ITS_API_KEY=your_its_api_key
DETECTION_BACKEND_URL=https://your-railway-backend.up.railway.app
DETECTION_TRANSPORT=websocket
DETECTION_WS_HTTP_FALLBACK=1
DETECTION_FRAME_WIDTH=960
DETECTION_JPEG_QUALITY=45
DETECTION_SEND_INTERVAL=0.12
DETECTION_CONTROL_ENABLED=1
```

Run YOLO PC:

```bash
cd main
python main.py --use-roi
```

`*.pt` model weights are intentionally not committed. Put `pruned.pt` in `main/` on the YOLO PC before running.
