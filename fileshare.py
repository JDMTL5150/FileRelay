#!/usr/bin/env python3
import os
import queue
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from flask import Flask, Response, abort, request, send_from_directory
from flask_cors import CORS
from pydantic import BaseModel
from werkzeug.exceptions import HTTPException

CHUNK_SIZE = 65536

@dataclass
class Room:
    filename: str
    size: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    receiver_connected: bool = False
    sender_connected: bool = False
    chunks: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=16))
    done: threading.Event = field(default_factory=threading.Event)

# Server room tracker (requires single-process multi-threaded Gunicorn)
room_tracker: dict[str, Room] = {}
lock = threading.Lock()

app = Flask(__name__, static_folder="public", static_url_path="")

# Allow Cloudflare Pages frontend (set ALLOWED_ORIGINS env var on Render, or default to "*")
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
CORS(app, resources={r"/*": {"origins": allowed_origins}})


def print_response(payload: dict):
    print(f"ROOM Created: {payload.get('room_id', 'Null')}")
    print(payload)


def create_room(payload: dict) -> dict:
    filename = str(payload.get("filename") or "").strip()
    if not filename:
        return {"success": False, "errmsg": "A valid filename is required.", "room_id": None}

    # Prevent header injection in Content-Disposition
    safe_filename = os.path.basename(filename).replace('"', "'")

    size = payload.get("size")
    if size is not None and (not isinstance(size, int) or size <= 0):
        return {"success": False, "errmsg": "size must be a positive integer.", "room_id": None}

    with lock:
        room_id = secrets.token_urlsafe(8)
        while room_id in room_tracker:
            room_id = secrets.token_urlsafe(8)
        room_tracker[room_id] = Room(filename=safe_filename, size=size)
    return {"success": True, "errmsg": "", "room_id": room_id}


def remove_room(room_id: str):
    with lock:
        room = room_tracker.pop(room_id, None)
    if room is not None:
        room.done.set()


def validate_room(room_id: str) -> dict:
    with lock:
        room = room_tracker.get(room_id)
        if room is None:
            return {"code": 404, "room": None}
        return {"code": 200, "room": room}


@app.get("/")
def home():
    return send_from_directory("public", "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}, 200


@app.post("/upload")
def receive_upload() -> dict:
    payload = request.get_json(silent=True) or {}
    roomstat = create_room(payload)
    print_response(roomstat)
    return roomstat


@app.post("/send/<room_id>")
def send_file_bytes(room_id: str) -> dict:
    valid = validate_room(room_id=room_id)
    if valid["code"] != 200:
        abort(valid["code"])
    room = valid["room"]

    with lock:
        if room.sender_connected:
            abort(409)
        room.sender_connected = True

    try:
        # Note: Render caps HTTP request duration at ~100s on free tier
        deadline = time.monotonic() + 90
        available = wait_for_receiver(room, deadline=deadline)
        if not available:
            abort(408)

        stream(room=room)
    except HTTPException:
        raise
    except Exception as ex:
        print(f"send failed: {ex}")
        abort(500)
    finally:
        room.sender_connected = False
        remove_room(room_id)

    return {"success": True}


def wait_for_receiver(room: Room, deadline: float) -> bool:
    while not room.receiver_connected and not room.done.is_set():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.2)
    return room.receiver_connected


def stream(room: Room):
    try:
        while chunk := request.stream.read(CHUNK_SIZE):
            if room.done.is_set():
                abort(410)
            room.chunks.put(chunk, timeout=30)
        room.chunks.put(None)
    except queue.Full:
        abort(504)
    except Exception as e:
        print(str(e))
        abort(410)


@app.get("/receive/<room_id>")
def serve_download_page(room_id: str):
    return send_from_directory("public", "download.html")


class DownloadStatusObj(BaseModel):
    success: bool
    filename: str
    size: int


@app.get("/status/<room_id>")
def serve_download_status(room_id: str):
    with lock:
        room = room_tracker.get(room_id)

    if room is None:
        data = DownloadStatusObj(success=False, filename="", size=-1)
    else:
        data = DownloadStatusObj(
            success=True,
            filename=room.filename,
            size=room.size if room.size is not None else -1,
        )
    return Response(data.model_dump_json(), mimetype="application/json")


@app.get("/download/<room_id>")
def serve_requested_file(room_id: str):
    valid = validate_room(room_id=room_id)
    if valid["code"] != 200:
        abort(valid["code"])
    room = valid["room"]

    with lock:
        if room.receiver_connected:
            abort(409)
        room.receiver_connected = True

    def stream_data():
        try:
            while True:
                chunk = room.chunks.get(timeout=30)
                if chunk is None:
                    break
                yield chunk
        finally:
            remove_room(room_id)

    return Response(
        stream_data(),
        mimetype="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{room.filename}"',
            "X-Accel-Buffering": "no",  # Prevents reverse proxies from buffering the live stream
        },
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)