import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

# This demo stores only the newest detection result in memory.
# Railway may restart the server, so this value can disappear after a restart.
latest_detection = None


@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "Jetson Nano object detection demo backend is running"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/detection", methods=["POST"])
def receive_detection():
    global latest_detection

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "JSON body is required"}), 400

    required_fields = ["class_name", "confidence", "bbox"]
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Missing required field(s)",
                    "missing_fields": missing_fields,
                }
            ),
            400,
        )

    latest_detection = {
        "class_name": data["class_name"],
        "confidence": data["confidence"],
        "bbox": data["bbox"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return jsonify({"status": "ok", "data": latest_detection})


@app.route("/api/latest", methods=["GET"])
def get_latest_detection():
    return jsonify({"data": latest_detection})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
