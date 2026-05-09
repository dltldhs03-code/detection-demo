cd ~/capstone/detection-demo

git add backend/main.py frontend/app/page.js frontend/app/globals.css frontend/package.json test_client/send_fake_detection.py test_client/send_yolo_detection.py test_client/README.md
git commit -m "Use YOLO frame upload instead of CCTV stream playback"
git push
