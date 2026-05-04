import threading
import tkinter as tk

from .core import (
    MORICE_NAME,
    compute_math,
    enforce_father,
    shorten_reply,
    summon_response,
    is_acknowledgement,
    extract_web_query,
    needs_web,
    extract_notes_term,
    wants_notes_search,
    wants_web_capability,
    wants_notes_summary,
    summarize_notes_hits,
    wants_unity_movement,
    wants_unity_2d,
    wants_unity_3d,
    unity_2d_movement_script,
    unity_3d_movement_script,
    wants_html_cube_movement,
    html_cube_movement_script,
    wake_up_response,
    emotional_checkin_response,
)
from .knowledge import KB_DIR, load_knowledge, retrieve_context, should_use_context, should_preload, search_notes
from .llm_client import chat
from .web_search import search_web
import os


class MoriceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{MORICE_NAME} Chat")
        self.geometry("820x560")
        self.configure(bg="#0b0b0b")
        try:
            self.attributes("-alpha", 0.97)
        except tk.TclError:
            pass

        self.history = []
        # Start awake so normal chat works immediately from the first message.
        self.awake = True
        self.last_notes_hits = []
        self.last_notes_term = ""

        self.text = tk.Text(
            self,
            wrap="word",
            state="disabled",
            bg="#000000",
            fg="#e6e6e6",
            insertbackground="#e6e6e6",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#2a2a2a",
            padx=10,
            pady=10,
            font=("Segoe UI", 11),
        )
        self.text.pack(fill="both", expand=True, padx=14, pady=(14, 8))

        input_frame = tk.Frame(self, bg="#141414", highlightthickness=1, highlightbackground="#2a2a2a")
        input_frame.pack(fill="x", padx=14, pady=(0, 14))

        self.entry = tk.Entry(
            input_frame,
            bg="#1a1a1a",
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#2a2a2a",
            highlightcolor="#3a82f7",
            font=("Segoe UI", 11),
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=8, pady=8)
        self.entry.bind("<Return>", self.on_send)

        send_btn = tk.Button(
            input_frame,
            text="Send",
            command=self.on_send,
            bg="#222222",
            fg="#f2f2f2",
            activebackground="#2a2a2a",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=6,
        )
        send_btn.pack(side="left", padx=(0, 8), pady=8)

        if should_preload():
            try:
                chunk_count = load_knowledge()
            except MemoryError:
                chunk_count = 0
            if chunk_count:
                self.append_message(MORICE_NAME, f"Loaded {chunk_count} knowledge chunks from {KB_DIR}.")
            else:
                self.append_message(MORICE_NAME, f"No knowledge files loaded from {KB_DIR}.")
        else:
            self.append_message(MORICE_NAME, "Knowledge is on-demand. Use @notes to include your files.")

    def append_message(self, author, message):
        self.text.configure(state="normal")
        self.text.insert("end", f"{author}: {message}\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def on_send(self, event=None):
        user_input = self.entry.get().strip()
        if not user_input:
            return
        self.entry.delete(0, "end")
        self.append_message("All Father", user_input)

        wake_message = wake_up_response(user_input)
        if wake_message:
            self.append_message(MORICE_NAME, wake_message)
            self.awake = True
            return

        if not self.awake:
            self.append_message(MORICE_NAME, "I am asleep. Say 'wake up son'.")
            return

        summon_message = summon_response(user_input)
        if summon_message:
            self.append_message(MORICE_NAME, summon_message)
            return

        emotional_reply = emotional_checkin_response(user_input)
        if emotional_reply:
            self.append_message(MORICE_NAME, enforce_father(emotional_reply))
            return

        if is_acknowledgement(user_input):
            self.append_message(MORICE_NAME, enforce_father("Understood."))
            return

        if wants_web_capability(user_input):
            if os.getenv("MORICE_WEB", "0") == "1":
                self.append_message(MORICE_NAME, enforce_father("Yes. Use @web <query> or ask a time-sensitive question."))
            else:
                self.append_message(MORICE_NAME, enforce_father("Web is disabled. Set MORICE_WEB=1 to enable it."))
            return

        if wants_notes_search(user_input):
            term = extract_notes_term(user_input)
            if term:
                hits = search_notes(term, max_hits=5)
                self.last_notes_hits = hits
                self.last_notes_term = term
                if hits:
                    self.append_message(MORICE_NAME, enforce_father(f"Found {len(hits)} match(es) for {term}."))
                    for hit in hits:
                        self.append_message(MORICE_NAME, f"{hit['source']}: {hit['text']}")
                else:
                    self.append_message(MORICE_NAME, enforce_father(f"No matches for {term} in notes."))
                return

        if wants_notes_summary(user_input) and self.last_notes_hits:
            summary = summarize_notes_hits(self.last_notes_hits)
            self.append_message(MORICE_NAME, enforce_father(summary))
            return

        if self.last_notes_hits:
            lowered = user_input.lower()
            if any(word in lowered for word in {"summarise", "summarize", "summary"}):
                summary = summarize_notes_hits(self.last_notes_hits)
                self.append_message(MORICE_NAME, enforce_father(summary))
                return
            if any(word in lowered for word in {"about him", "about her", "about it"}) and self.last_notes_term:
                summary = summarize_notes_hits(self.last_notes_hits)
                self.append_message(MORICE_NAME, enforce_father(summary))
                return

        if wants_unity_movement(user_input):
            if wants_unity_3d(user_input):
                script = unity_3d_movement_script()
            else:
                script = unity_2d_movement_script()
            self.append_message(MORICE_NAME, f"Father, here is the script.\n{script}")
            return

        if wants_html_cube_movement(user_input):
            self.append_message(MORICE_NAME, f"Father, here is the script.\n{html_cube_movement_script()}")
            return

        math_result = compute_math(user_input)
        if math_result is not None:
            self.append_message(MORICE_NAME, enforce_father(shorten_reply(math_result)))
            return

        context = retrieve_context(user_input) if should_use_context(user_input) else ""
        web_context = ""
        if os.getenv("MORICE_WEB", "0") == "1":
            web_query = extract_web_query(user_input) or (user_input if needs_web(user_input) else None)
            if web_query:
                web_context = search_web(web_query)
        extra_system = ""
        if context:
            extra_system = (
                "Use the following local notes when relevant. "
                "If they don't apply, ignore them.\n\n"
                f"{context}"
            )
        if web_context:
            extra_system = (extra_system + "\n\n" if extra_system else "") + (
                "Web results (may be incomplete):\n" + web_context
            )

        def worker():
            reply = chat(self.history, user_input, extra_system=extra_system)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": reply})
            self.after(0, lambda: self.append_message(MORICE_NAME, enforce_father(shorten_reply(reply))))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = MoriceApp()
    app.mainloop()
