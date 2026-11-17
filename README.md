# File Relay

A lightweight, room-based file-sharing web application built with **Python (Flask)** and **Vanilla JavaScript**. Users can upload a file to generate a unique shareable room link and download it directly in the browser with real-time metadata previews.

## Features

- **Room-Based Sharing:** Generates unique room IDs (e.g., `p_8816DWs_0`) for isolated file transfers.
- **Metadata Previews:** Displays the filename and formatted file size before downloading via a dedicated `/status/<room_id>` JSON endpoint.
- **Direct Streamed Downloads:** Uses `Content-Disposition` headers for native browser downloads without loading large files into JavaScript memory.
- **Typed API Responses:** Validates and serializes room status payloads using Pydantic models.

## Tech Stack

- **Backend:** Python, Flask, Pydantic
- **Frontend:** HTML5, CSS3, Vanilla JavaScript (`fetch` API)

## Project Structure

```text
fileshare/
├── fileshare.py        # Flask backend, room tracking, upload/status/download routes
├── static/             # Frontend JS and CSS assets
├── templates/          # HTML views (upload & receive pages)
└── README.md
