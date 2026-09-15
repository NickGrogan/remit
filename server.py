"""
REMIT Insider — Flask Server
Serves the frontend and exposes REST + SSE endpoints for real-time alerts.
"""

import atexit
import json
import logging
import os
import time
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, send_from_directory

from worker import RemitWorker

# ── Setup ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("remit.server")

app = Flask(__name__, static_folder="static", static_url_path="/static")
worker = RemitWorker()


# ── Static routes ───────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── API routes ──────────────────────────────────────

@app.route("/api/alerts")
def api_alerts():
    """Return latest parsed alerts as JSON."""
    alerts = worker.get_alerts(limit=150)
    return jsonify({"alerts": alerts, "count": len(alerts)})


@app.route("/api/stats")
def api_stats():
    """Return summary statistics."""
    stats = worker.get_stats()
    return jsonify(stats)


@app.route("/api/alerts/stream")
def api_alerts_stream():
    """Server-Sent Events stream for real-time updates."""

    def generate():
        last_count = 0
        while True:
            alerts = worker.get_alerts(limit=50)
            current_count = len(alerts)
            stats = worker.get_stats()

            # Send update
            payload = json.dumps({
                "alerts": alerts[:20],  # Latest 20 for SSE
                "stats": stats,
            })
            yield f"data: {payload}\n\n"
            time.sleep(10)  # Push every 10 seconds

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Boot worker at import time (works with both gunicorn and direct run) ──

worker.start()
atexit.register(worker.stop)


# ── Direct run (local development) ─────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 REMIT Insider starting on port {port}...")
    try:
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("Server shut down.")
