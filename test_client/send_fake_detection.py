import random
import requests


# Edit this URL after deploying the backend to Railway.
# For local testing, use: "http://localhost:5000"
BACKEND_URL = "https://detection-demo-production.up.railway.app"



def make_fake_detection():
    x1 = random.randint(0, 300)
    y1 = random.randint(0, 240)
    width = random.randint(40, 220)
    height = random.randint(40, 220)

    return {
        "class_name": random.choice(["car", "bus", "truck"]),
        "confidence": round(random.uniform(0.5, 0.99), 2),
        "bbox": [x1, y1, x1 + width, y1 + height],
    }


def main():
    detection = make_fake_detection()
    url = f"{BACKEND_URL}/api/detection"

    print("Sending fake detection:")
    print(detection)

    response = requests.post(url, json=detection, timeout=10)

    print("Server status code:", response.status_code)
    print("Server response:")
    print(response.json())


if __name__ == "__main__":
    main()
