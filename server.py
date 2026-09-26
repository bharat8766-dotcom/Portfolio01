#!/usr/bin/env python3
"""
Portfolio Backend Server & SQLite Database
Built with Python 3 Standard Library (ThreadingHTTPServer + SQLite3).
Zero external dependencies required.
"""

import os
import sys
import json
import re
import sqlite3
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Configuration
PORT = int(os.environ.get("PORT", 8000))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "portfolio.db")

# =============================================================================
# DATABASE LAYER
# =============================================================================
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the SQLite database schema."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT,
                user_agent TEXT,
                is_read INTEGER DEFAULT 0
            )
        """)
        conn.commit()
    print(f"✓ SQLite Database initialized at: {DB_FILE}")

def save_message(name, email, subject, message, ip_address="", user_agent=""):
    """Insert a new contact message into the database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (name, email, subject, message, created_at, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, email, subject, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ip_address, user_agent))
        conn.commit()
        return cursor.lastrowid

def get_all_messages():
    """Retrieve all messages ordered by newest first."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_message(message_id):
    """Delete a message by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        conn.commit()
        return cursor.rowcount > 0

# =============================================================================
# HTTP REQUEST HANDLER
# =============================================================================
class PortfolioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def _send_json(self, status_code, data):
        """Helper to send JSON response with CORS headers."""
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API: Health Check
        if path == "/api/health":
            try:
                messages = get_all_messages()
                self._send_json(200, {
                    "status": "healthy",
                    "database": "connected",
                    "database_file": DB_FILE,
                    "total_messages": len(messages),
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                self._send_json(500, {"status": "error", "error": str(e)})
            return

        # API: Get Messages (Admin API)
        if path == "/api/messages":
            try:
                messages = get_all_messages()
                self._send_json(200, {
                    "status": "success",
                    "count": len(messages),
                    "messages": messages
                })
            except Exception as e:
                self._send_json(500, {"status": "error", "error": str(e)})
            return

        # Admin View Route
        if path == "/admin":
            admin_file = os.path.join(BASE_DIR, "admin.html")
            if os.path.exists(admin_file):
                self.path = "/admin.html"

        # Serve static files (index.html, profile.jpg, resume, etc.)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API: Submit Contact Form
        if path == "/api/contact":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length == 0:
                    self._send_json(400, {"status": "error", "message": "Empty request body"})
                    return

                raw_body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(raw_body)

                name = str(data.get("name", "")).strip()
                email = str(data.get("email", "")).strip()
                subject = str(data.get("subject", "")).strip()
                message = str(data.get("message", "")).strip()

                # Validation
                if len(name) < 2:
                    self._send_json(400, {"status": "error", "message": "Name must be at least 2 characters long."})
                    return

                email_regex = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
                if not re.match(email_regex, email):
                    self._send_json(400, {"status": "error", "message": "Please provide a valid email address."})
                    return

                if len(subject) < 2:
                    self._send_json(400, {"status": "error", "message": "Please provide a subject."})
                    return

                if len(message) < 5:
                    self._send_json(400, {"status": "error", "message": "Message must be at least 5 characters long."})
                    return

                # Client metadata
                client_ip = self.headers.get("X-Forwarded-For", self.client_address[0])
                user_agent = self.headers.get("User-Agent", "Unknown")

                # Store in SQLite database
                msg_id = save_message(name, email, subject, message, client_ip, user_agent)

                print(f"[NEW MESSAGE] ID: {msg_id} from {name} <{email}>: '{subject}'")

                self._send_json(200, {
                    "status": "success",
                    "message": "Thank you! Your message has been safely received and stored.",
                    "id": msg_id,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            except json.JSONDecodeError:
                self._send_json(400, {"status": "error", "message": "Invalid JSON format."})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": f"Server error: {str(e)}"})
            return

        # API: Delete Message
        if path == "/api/delete-message":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(raw_body)
                msg_id = data.get("id")
                if not msg_id:
                    self._send_json(400, {"status": "error", "message": "Message ID required"})
                    return

                success = delete_message(int(msg_id))
                if success:
                    self._send_json(200, {"status": "success", "message": f"Message {msg_id} deleted."})
                else:
                    self._send_json(404, {"status": "error", "message": "Message not found."})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        self._send_json(404, {"status": "error", "message": "Endpoint not found"})

# =============================================================================
# SERVER ENTRYPOINT
# =============================================================================
def run():
    init_db()
    server_address = ("", PORT)
    httpd = ThreadingHTTPServer(server_address, PortfolioHandler)
    print("=" * 60)
    print(f"🚀 Bharat's Portfolio Backend Server is Running!")
    print(f"📍 URL:           http://localhost:{PORT}")
    print(f"📊 Admin Portal:  http://localhost:{PORT}/admin")
    print(f"🗄️  Database:      {DB_FILE}")
    print(f"🔌 API Endpoint:  POST http://localhost:{PORT}/api/contact")
    print("=" * 60)
    print("Press Ctrl+C to stop the server.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server gracefully stopped.")
        sys.exit(0)

if __name__ == "__main__":
    run()
