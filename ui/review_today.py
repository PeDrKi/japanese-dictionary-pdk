"""
review_today.py — "🎯 Ôn tập hôm nay" entry point.

A small mode-picker dialog: shows how many cards are due for SRS review
today, then launches whichever mode (Quiz / Flashcard / Typing) the user
picks — pre-configured with "chỉ ôn thẻ đến hạn" already checked, so the
user doesn't have to remember to turn that filter on themselves every time.
"""
import customtkinter as ctk
from constants import KB_ESCAPE
from ui.flashcard import FlashcardLauncher
from ui.quiz import QuizLauncher
from ui.typing_practice import TypingLauncher


class ReviewTodayDialog(ctk.CTkToplevel):

    def __init__(self, master, card_service, deck_service, study_service):
        super().__init__(master)
        self._card_service  = card_service
        self._deck_service  = deck_service
        self._study_service = study_service
        self.title("🎯  Ôn tập hôm nay")
        self.geometry("360x340")
        self.resizable(False, False)
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy())
        self._build()

    def _build(self):
        due_count = self._card_service.due_count()

        ctk.CTkLabel(self, text="🎯", font=ctk.CTkFont(size=40)).pack(pady=(28, 4))

        if due_count == 0:
            ctk.CTkLabel(self, text="Không có thẻ nào cần ôn hôm nay!",
                         font=ctk.CTkFont(size=15, weight="bold")
                         ).pack(pady=(0, 4))
            ctk.CTkLabel(self, text="Quay lại sau, hoặc chọn ôn tự do bên dưới\n"
                                     "(bỏ chọn lọc 'chỉ thẻ đến hạn' trong màn tiếp theo).",
                         font=ctk.CTkFont(size=11),
                         text_color=("gray50", "gray55"),
                         justify="center").pack(pady=(0, 16), padx=20)
        else:
            ctk.CTkLabel(self, text=f"{due_count} thẻ cần ôn hôm nay",
                         font=ctk.CTkFont(size=16, weight="bold")
                         ).pack(pady=(0, 4))
            ctk.CTkLabel(self, text="Chọn cách bạn muốn ôn:",
                         font=ctk.CTkFont(size=11),
                         text_color=("gray50", "gray55")).pack(pady=(0, 16))

        btn_kwargs = dict(height=44, font=ctk.CTkFont(size=14))
        ctk.CTkButton(self, text="🃏  Flashcard", command=self._launch_flashcard,
                      **btn_kwargs).pack(fill="x", padx=32, pady=6)
        ctk.CTkButton(self, text="📝  Quiz trắc nghiệm", command=self._launch_quiz,
                      **btn_kwargs).pack(fill="x", padx=32, pady=6)
        ctk.CTkButton(self, text="⌨️  Luyện gõ", command=self._launch_typing,
                      **btn_kwargs).pack(fill="x", padx=32, pady=6)

        ctk.CTkButton(self, text="✕ Đóng",
                      fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
                      command=self.destroy, height=32
                      ).pack(pady=(16, 12))

    def _launch_flashcard(self):
        self.destroy()
        FlashcardLauncher(self.master, self._card_service, self._deck_service,
                           self._study_service, default_due_only=True)

    def _launch_quiz(self):
        self.destroy()
        QuizLauncher(self.master, self._card_service, self._deck_service,
                     self._study_service, default_due_only=True)

    def _launch_typing(self):
        self.destroy()
        TypingLauncher(self.master, self._card_service, self._deck_service,
                       self._study_service, default_due_only=True)
