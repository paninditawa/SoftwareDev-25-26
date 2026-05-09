"""
Accessible chat panel for customtkinter.
Includes keyboard navigation, screen reader announcements, and message updates.
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from launcher.services.chat_service import ChatService
from launcher.services.speech import SpeechManager
from launcher.ui.theme import (
    APP_ACCENT,
    APP_BG,
    APP_BORDER,
    APP_BUTTON_TEXT,
    APP_MUTED,
    APP_PANEL,
    APP_PANEL_ALT,
    APP_TEXT,
    _font,
)


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
            text="Community Chat",
            font=_font(24, True),
            text_color=APP_TEXT,
        )
        title.pack(pady=(12, 6), padx=14, anchor="w")

        subtitle = ctk.CTkLabel(
            self,
            text="A space for players to talk strategy and say hello.",
            font=_font(13),
            text_color=APP_MUTED,
            wraplength=640,
            justify="left",
        )
        subtitle.pack(pady=(0, 10), padx=14, anchor="w")

        # Messages display area (read-only text widget for accessibility)
        self.messages_frame = ctk.CTkFrame(
            self,
            fg_color=APP_PANEL_ALT,
            corner_radius=18,
            border_width=2,
            border_color=APP_BORDER,
        )
        self.messages_frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        # Scrollable messages container
        self.messages_canvas = ctk.CTkCanvas(
            self.messages_frame,
            bg=APP_PANEL_ALT,
            highlightthickness=0,
            height=260,
        )
        self.messages_canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)

        scrollbar = ctk.CTkScrollbar(
            self.messages_frame,
            command=self.messages_canvas.yview,
        )
        scrollbar.pack(side="right", fill="y")
        self.messages_canvas.configure(yscrollcommand=scrollbar.set)

        # Inner frame for messages
        self.messages_inner = ctk.CTkFrame(self.messages_canvas, fg_color=APP_PANEL_ALT)
        self.messages_canvas_window = self.messages_canvas.create_window(
            0, 0, window=self.messages_inner, anchor="nw"
        )
        self.messages_inner.bind(
            "<Configure>",
            lambda e: self.messages_canvas.configure(scrollregion=self.messages_canvas.bbox("all")),
        )
        self.messages_canvas.bind("<Configure>", self._resize_message_area)

        # Keyboard shortcut hint
        hint = ctk.CTkLabel(
            self,
            text="Tab to message input. Type message and press Enter to send. Press Ctrl+Q to close window. Press Ctrl+R to read chat messages.",
            font=_font(11),
            text_color=APP_MUTED,
            wraplength=660,
            justify="left",
            fg_color=APP_PANEL,
            corner_radius=14,
            padx=14,
            pady=10,
        )
        hint.pack(fill="x", pady=(0, 10), padx=14, anchor="w")

        # Message input frame
        input_frame = ctk.CTkFrame(
            self,
            fg_color=APP_PANEL,
            corner_radius=18,
            border_width=2,
            border_color=APP_BORDER,
        )
        input_frame.pack(fill="x", padx=14, pady=(0, 14))

        self.input_field = ctk.CTkEntry(
            input_frame,
            placeholder_text="Type a message...",
            font=_font(15),
            height=46,
        )
        self.input_field.pack(side="left", fill="both", expand=True, padx=(12, 8), pady=12)
        self.input_field.bind("<Return>", self._on_send_message)
        self.input_field.bind("<Control-r>", lambda e: self._read_new_messages())  # Read new messages
        self.input_field.bind("<space>", self._on_entry_space)
        self._bind_entry_key_feedback(self.input_field)

        self.send_btn = ctk.CTkButton(
            input_frame,
            text="Send",
            command=self._on_send_message,
            width=110,
            height=46,
            font=_font(15, True),
            text_color=APP_BUTTON_TEXT,
        )
        self.send_btn.pack(side="left", padx=(0, 12), pady=12)

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
            empty_state = ctk.CTkLabel(
                self.messages_inner,
                text="No messages yet. Start the conversation or wait for others to join.",
                font=_font(12),
                text_color=APP_TEXT,
                fg_color=APP_PANEL,
                corner_radius=14,
                padx=14,
                pady=12,
                wraplength=560,
                justify="left",
            )
            empty_state.pack(anchor="w", padx=8, pady=8, fill="x")
            self.last_message_ids.clear()
        else:
            for msg in messages:
                msg_id = msg.get("id")
                if msg_id and msg_id not in self.last_message_ids:
                    new_message_count += 1

                username = msg.get("username", "Unknown")
                content = msg.get("content", "")
                is_own = msg.get("user_id") == self.user_id

                bubble = ctk.CTkFrame(
                    self.messages_inner,
                    fg_color=APP_PANEL if is_own else APP_BG,
                    corner_radius=16,
                    border_width=1,
                    border_color=APP_ACCENT if is_own else APP_BORDER,
                )
                bubble.pack(anchor="w", padx=8, pady=6, fill="x")

                speaker = ctk.CTkLabel(
                    bubble,
                    text=username,
                    font=_font(13, True),
                    text_color=APP_ACCENT if is_own else APP_TEXT,
                    anchor="w",
                )
                speaker.pack(anchor="w", padx=12, pady=(10, 2))

                msg_label = ctk.CTkLabel(
                    bubble,
                    text=content,
                    font=_font(13),
                    text_color=APP_TEXT,
                    wraplength=560,
                    justify="left",
                    anchor="w",
                )
                msg_label.pack(anchor="w", padx=12, pady=(0, 10), fill="x")

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

    def _resize_message_area(self, event) -> None:
        """Keep the inner message column aligned with the canvas width."""
        width = max(200, event.width - 6)
        self.messages_canvas.itemconfigure(self.messages_canvas_window, width=width)

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
                    "'": "apostrophe", ",": "comma", " ": "space",
                }
                spoken = char_names.get(event.char, event.char)
                self.speech_manager.announce(spoken, interrupt=True, force=True)
        entry.bind("<Key>", _on_key, add="+")

    def _on_entry_space(self, event) -> str:
        """Handle spacebar inside the chat input without bubbling to the main app."""
        entry = event.widget
        try:
            if entry.selection_present():
                entry.delete("sel.first", "sel.last")
        except Exception:
            pass
        entry.insert(tk.INSERT, " ")
        self.speech_manager.announce("space", interrupt=True, force=True)
        return "break"

    def _read_new_messages(self) -> None:
        """Read out the current chat messages."""
        messages = []
        for widget in self.messages_inner.winfo_children():
            if isinstance(widget, ctk.CTkLabel):
                text = widget.cget("text")
                if text:
                    messages.append(text)
                continue

            if isinstance(widget, ctk.CTkFrame):
                speaker = ""
                content_parts = []
                for child in widget.winfo_children():
                    if isinstance(child, ctk.CTkLabel):
                        text = child.cget("text")
                        if text:
                            if not speaker:
                                speaker = text
                            else:
                                content_parts.append(text)
                if speaker:
                    content = " ".join(content_parts).strip()
                    messages.append(f"{speaker}: {content}" if content else speaker)
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
