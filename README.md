# Detection Demo

Remote CCTV monitoring demo for Railway and Vercel.

## Structure

```text
backend/   Flask backend for Railway
frontend/  Next.js frontend for Vercel
```

The YOLO PC sends annotated JPEG frames and status values to the Railway backend. The frontend reads video from `/frame.jpg` and status/chart values from `/api/status` and `/ws/viewer`.

## Railway

Recommended root directory:

```text
backend
```

Environment variables:

```env
ITS_API_KEY=your_its_api_key
```

If Railway is configured with the repository root instead of `backend`, the root `railway.json` and `requirements.txt` are also included.

## Vercel

Root directory:

```text
frontend
```

Environment variables:

```env
NEXT_PUBLIC_API_URL=https://your-railway-backend.up.railway.app
NEXT_PUBLIC_SHOW_OVERLAY=0
NEXT_PUBLIC_FRAME_REFRESH_MS=600
```

Set `NEXT_PUBLIC_SHOW_OVERLAY=1` only if you want the browser to draw the old ROI/bbox overlay on top of the annotated MJPEG stream.
