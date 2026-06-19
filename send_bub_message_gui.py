"""Small Tk GUI to post a message to a Discord channel via the bot token.
Dev/ops helper, not part of the production bot runtime."""

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from urllib import error, request


def _ensure_runtime_python() -> None:
    try:
        import dotenv  # noqa: F401
    except ModuleNotFoundError:
        venv_python = Path(__file__).resolve().parent / ".venv" / "Scripts" / "python.exe"
        if venv_python.is_file():
            raise SystemExit(subprocess.call([str(venv_python), *sys.argv]))
        raise SystemExit(
            "Missing dependency: python-dotenv. "
            "Run: python -m venv .venv && .\\.venv\\Scripts\\pip install -r requirements.txt"
        )


_ensure_runtime_python()
from dotenv import load_dotenv


DEFAULT_CHANNEL_ID = 1345474577316319265
DISCORD_API_BASE = "https://discord.com/api/v10"
MAX_MESSAGE_LENGTH = 2000


def load_token():
    env_path = Path(__file__).with_name(".env")
    load_dotenv(env_path)
    token = (os.getenv("DISCORD_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing from .env")
    return token


def post_message(token, channel_id, content, reply_message_id=None):
    payload_data = {"content": content}
    if reply_message_id:
        payload_data["message_reference"] = {
            "channel_id": str(channel_id),
            "message_id": str(reply_message_id),
            "fail_if_not_exists": True,
        }
    payload = json.dumps(payload_data).encode("utf-8")
    req = request.Request(
        f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "bub-message-gui/1.0",
        },
    )
    with request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


class BubMessageApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Send Bub Message")
        self.root.geometry("700x420")
        self.root.minsize(520, 320)

        self.token = load_token()
        self.sending = False
        self.channel_id_var = tk.StringVar(value=str(DEFAULT_CHANNEL_ID))
        self.status_var = tk.StringVar(
            value=f"Ready to send as Bub to channel {DEFAULT_CHANNEL_ID}."
        )

        frame = tk.Frame(root, padx=12, pady=12)
        frame.pack(fill="both", expand=True)

        title = tk.Label(
            frame,
            text="Send a one-off Bub message",
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        )
        title.pack(fill="x")

        channel_frame = tk.Frame(frame)
        channel_frame.pack(fill="x", pady=(4, 10))

        channel_label = tk.Label(channel_frame, text="Target channel id:")
        channel_label.pack(side="left")

        self.channel_entry = tk.Entry(
            channel_frame,
            textvariable=self.channel_id_var,
            font=("Consolas", 10),
        )
        self.channel_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        reply_frame = tk.Frame(frame)
        reply_frame.pack(fill="x", pady=(0, 10))

        reply_label = tk.Label(reply_frame, text="Reply to message id (optional):")
        reply_label.pack(side="left")

        self.reply_id_var = tk.StringVar()
        self.reply_entry = tk.Entry(reply_frame, textvariable=self.reply_id_var, font=("Consolas", 10))
        self.reply_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.text = tk.Text(frame, wrap="word", font=("Consolas", 11), height=14)
        self.text.pack(fill="both", expand=True)
        self.text.focus_set()

        controls = tk.Frame(frame)
        controls.pack(fill="x", pady=(10, 0))

        self.count_label = tk.Label(controls, text="0 / 2000")
        self.count_label.pack(side="left")

        self.send_button = tk.Button(
            controls,
            text="Send",
            width=12,
            command=self.on_send_clicked,
        )
        self.send_button.pack(side="right")

        self.clear_button = tk.Button(
            controls,
            text="Clear",
            width=12,
            command=self.clear_text,
        )
        self.clear_button.pack(side="right", padx=(0, 8))

        status = tk.Label(
            frame,
            textvariable=self.status_var,
            anchor="w",
            justify="left",
            wraplength=650,
        )
        status.pack(fill="x", pady=(10, 0))

        self.text.bind("<KeyRelease>", self.update_count)
        self.root.bind("<Control-Return>", self.on_ctrl_enter)
        self.update_count()

    def clear_text(self):
        if self.sending:
            return
        self.channel_id_var.set(str(DEFAULT_CHANNEL_ID))
        self.reply_id_var.set("")
        self.text.delete("1.0", "end")
        self.update_count()
        self.status_var.set(f"Ready to send as Bub to channel {self.channel_id_var.get().strip()}.")

    def get_content(self):
        return self.text.get("1.0", "end").rstrip("\n")

    def update_count(self, event=None):
        length = len(self.get_content())
        self.count_label.config(text=f"{length} / {MAX_MESSAGE_LENGTH}")

    def on_ctrl_enter(self, event):
        self.on_send_clicked()
        return "break"

    def set_sending(self, sending):
        self.sending = sending
        state = "disabled" if sending else "normal"
        self.send_button.config(state=state)
        self.clear_button.config(state=state)
        self.text.config(state=state)

    def on_send_clicked(self):
        if self.sending:
            return

        content = self.get_content().strip()
        if not content:
            messagebox.showwarning("No message", "Enter a message first.")
            return
        if len(content) > MAX_MESSAGE_LENGTH:
            messagebox.showwarning(
                "Message too long",
                f"Discord messages must be {MAX_MESSAGE_LENGTH} characters or less.",
            )
            return

        channel_id = self.channel_id_var.get().strip()
        if not channel_id or not channel_id.isdigit():
            messagebox.showwarning(
                "Invalid channel id",
                "Target channel id must be numeric.",
            )
            return

        reply_message_id = self.reply_id_var.get().strip()
        if reply_message_id and not reply_message_id.isdigit():
            messagebox.showwarning(
                "Invalid message id",
                "Reply message id must be numeric if you provide one.",
            )
            return

        self.set_sending(True)
        self.status_var.set(f"Sending to channel {channel_id}...")
        thread = threading.Thread(
            target=self.send_in_background,
            args=(channel_id, content, reply_message_id or None),
            daemon=True,
        )
        thread.start()

    def send_in_background(self, channel_id, content, reply_message_id):
        try:
            response = post_message(
                self.token,
                channel_id,
                content,
                reply_message_id=reply_message_id,
            )
            message_id = response.get("id", "unknown")
            self.root.after(0, self.on_send_success, channel_id, message_id, reply_message_id)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self.root.after(0, self.on_send_error, f"HTTP {exc.code}: {body}")
        except Exception as exc:
            self.root.after(0, self.on_send_error, str(exc))

    def on_send_success(self, channel_id, message_id, reply_message_id):
        self.set_sending(False)
        if reply_message_id:
            self.status_var.set(
                f"Sent to channel {channel_id} as a reply to {reply_message_id}. Discord message id: {message_id}"
            )
        else:
            self.status_var.set(f"Sent to channel {channel_id}. Discord message id: {message_id}")

    def on_send_error(self, error_text):
        self.set_sending(False)
        self.status_var.set(f"Send failed: {error_text}")
        messagebox.showerror("Send failed", error_text)


def main():
    root = tk.Tk()
    app = BubMessageApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
