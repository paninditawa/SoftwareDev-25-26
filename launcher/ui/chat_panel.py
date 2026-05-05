"""
Accessible chat panel for customtkinter.
Includes keyboard navigation, screen reader announcements, and message updates.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from launcher.services.chat_service import ChatService
from launcher.services.speech import SpeechManager
from launcher.ui.theme import APP_BG, APP_PANEL, APP_TEXT, APP_ACCENT, _font


class ChatPanel(ctk.CTkFrame):
    """Accessible chat UI with real-time updates via polling."""

    def __init__(
        self,
        parent: tk.Widget,
        chat_service: ChatService,
        speech_manager: SpeechManager,
        user_id: str,
        username: str,
        game_type: str = "general",
        **kwargs,
    ):
        super().__init__(parent, fg_color=APP_BG, **kwargs)
        self.chat_service = chat_service
        self.speech_manager = speech_manager
        self.user_id = user_id
        self.username = username
        self.game_type = game_type
        self.last_message_ids: set[str] = set()
        self.polling_id = None
        self._build_ui()
        self._start_polling()

    def _build_ui(self) -> None:
        """Build the chat UI layout."""
        # Title with screen reader label
        title = ctk.CTkLabel(
            self,
            text="Chat",
            font=_font(20, "bold"),
            text_color=APP_TEXT,
        )
        title.pack(pady=10, padx=10, anchor="w")

        # Messages display area (read-only text widget for accessibility)
        self.messages_frame = ctk.CTkFrame(self, fg_color=APP_PANEL)
        self.messages_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Scrollable messages container
        self.messages_canvas = ctk.CTkCanvas(
            self.messages_frame,
            bg=APP_PANEL,
            highlightthickness=0,
            height=200,
        )
        self.messages_canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ctk.CTkScrollbar(
            self.messages_frame,
            command=self.messages_canvas.yview,
        )
        scrollbar.pack(side="right", fill="y")
        self.messages_canvas.configure(yscrollcommand=scrollbar.set)

        # Inner frame for messages
        self.messages_inner = ctk.CTkFrame(self.messages_canvas, fg_color=APP_PANEL)
        self.messages_canvas_window = self.messages_canvas.create_window(
            0, 0, window=self.messages_inner, anchor="nw"
        )
        self.messages_inner.bind(
            "<Configure>",
            lambda e: self.messages_canvas.configure(scrollregion=self.messages_canvas.bbox("all")),
        )

        # Keyboard shortcut hint
        hint = ctk.CTkLabel(
            self,
            text="Tab to message input. Type message and press Enter to send. Press Ctrl+Q to close window. Press Ctrl+R to read chat messages.",
            font=_font(10),
            text_color=APP_TEXT,
            wraplength=300,
        )
        hint.pack(pady=5, padx=10, anchor="w")

        # Message input frame
        input_frame = ctk.CTkFrame(self, fg_color=APP_BG)
        input_frame.pack(fill="x", padx=10, pady=10)

        self.input_field = ctk.CTkEntry(
            input_frame,
            placeholder_text="Type a message...",
            font=_font(12),
        )
        self.input_field.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.input_field.bind("<Return>", self._on_send_message)
        self.input_field.bind("<Control-r>", lambda e: self._read_new_messages())  # Read new messages
        self._bind_entry_key_feedback(self.input_field)

        send_btn = ctk.CTkButton(
            input_frame,
            text="Send",
            command=self._on_send_message,
            width=80,
        )
        send_btn.pack(side="left")

    def _on_send_message(self, event=None) -> str:
        """Handle message send."""
        message = self.input_field.get().strip()
        if not message:
            self.speech_manager.announce("Message empty. Please type a message.")
            return "break"

        try:
            self.chat_service.send_message(
                self.user_id, self.username, message, self.game_type
            )
            self.input_field.delete(0, tk.END)
            self.speech_manager.announce(
                f"Message sent: {message}", interrupt=False, force=True
            )
            # Immediately poll for messages to show the sent message
            self._poll_messages()
        except RuntimeError as e:
            self.speech_manager.announce(f"Error sending message: {str(e)}")

        return "break"

    def _start_polling(self) -> None:
        """Start polling for new messages."""
        self._poll_messages()

    def _poll_messages(self) -> None:
        """Poll for new messages periodically."""
        try:
            messages = self.chat_service.get_messages(
                self.game_type, limit=50, since_minutes=120
            )
            self._display_messages(messages)
        except Exception as exc:
            print(f"[chat] polling error: {exc}")

        # Poll every 2 seconds
        self.polling_id = self.after(2000, self._poll_messages)

    def _display_messages(self, messages: list[dict]) -> None:
        """Display messages in the UI."""
        # Clear old messages
        for widget in self.messages_inner.winfo_children():
            widget.destroy()

        new_message_count = 0
        if not messages:
            ctk.CTkLabel(
                self.messages_inner,
                text="No messages yet. Start the conversation or wait for others to join.",
                font=_font(11),
                text_color=APP_TEXT,
                wraplength=250,
                justify="left",
            ).pack(anchor="w", padx=5, pady=3, fill="x")
            self.last_message_ids.clear()
        else:
            for msg in messages:
                msg_id = msg.get("id")
                if msg_id and msg_id not in self.last_message_ids:
                    new_message_count += 1

                username = msg.get("username", "Unknown")
                content = msg.get("content", "")
                is_own = msg.get("user_id") == self.user_id

                # Create message widget
                msg_label = ctk.CTkLabel(
                    self.messages_inner,
                    text=f"{username}: {content}",
                    font=_font(11),
                    text_color=APP_ACCENT if is_own else APP_TEXT,
                    wraplength=250,
                    justify="left",
                )
                msg_label.pack(anchor="w", padx=5, pady=3, fill="x")

            self.last_message_ids = {msg.get("id") for msg in messages if msg.get("id")}

        # Announce new messages
        if new_message_count > 0:
            if new_message_count == 1:
                self.speech_manager.announce(
                    f"1 new message in chat", interrupt=False, force=True
                )
            else:
                self.speech_manager.announce(
                    f"{new_message_count} new messages in chat",
                    interrupt=False,
                    force=True,
                )

        # Auto-scroll to bottom
        self.messages_canvas.yview_moveto(1.0)

    def destroy(self) -> None:
        """Clean up polling when panel is destroyed."""
        if self.polling_id:
            self.after_cancel(self.polling_id)
        super().destroy()

    def _bind_entry_key_feedback(self, entry: ctk.CTkEntry) -> None:
        """Speak each character as it is typed (screen-reader-style feedback)."""
        def _on_key(event) -> None:
            keysym = event.keysym
            if keysym == "BackSpace":
                self.speech_manager.announce("backspace", interrupt=True, force=True)
            elif (
                event.char
                and event.char.isprintable()
                and not keysym.startswith(("Control", "Alt", "Shift", "caps_lock"))
            ):
                char_names = {
                    ".": "dot", "@": "at", "-": "dash", "_": "underscore",
                    "!": "exclamation", "#": "hash", "$": "dollar",
                    "%": "percent", "&": "and", "+": "plus", "=": "equals",
                    " ": "space",
                }
                spoken = char_names.get(event.char, event.char)
                self.speech_manager.announce(spoken, interrupt=True, force=True)
        entry.bind("<Key>", _on_key, add="+")

    def _read_new_messages(self) -> None:
        """Read out the current chat messages."""
        messages = []
        for widget in self.messages_inner.winfo_children():
            if isinstance(widget, ctk.CTkLabel):
                text = widget.cget("text")
                if text:
                    messages.append(text)
        if messages:
            self.speech_manager.announce("Chat messages: " + ". ".join(messages), interrupt=True, force=True)
        else:
            self.speech_manager.announce("No messages in chat yet.", interrupt=True, force=True)

    def _return_to_navigation(self) -> None:
        """Return focus to the main navigation."""
        current = self
        while current.master:
            current = current.master
            if hasattr(current, '_focus_navigation'):
                current._focus_navigation()
                return
        # Fallback to toplevel
        toplevel = self.winfo_toplevel()
        if hasattr(toplevel, '_focus_navigation'):
            toplevel._focus_navigation()