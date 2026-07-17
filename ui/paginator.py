import customtkinter as ctk

PAGE_SIZES = [20, 50, 100, 200, 500, 1000]
ALL_LABEL = "Tất cả"
_UNSET = object()   # distinguishes "caller passed nothing" from "caller passed None (show all)"


class Paginator(ctk.CTkFrame):
    """
    Reusable pagination bar.
    Calls on_change(page, page_size) when user navigates.
    page_size is an int, or None to mean "show all" (no LIMIT/OFFSET —
    CardService.list_cards already treats limit=None as unpaginated).
    """

    def __init__(self, master, on_change, initial_page_size=_UNSET, **kwargs):
        super().__init__(master, fg_color=("gray88", "gray20"),
                         corner_radius=0, height=36, **kwargs)
        self.on_change  = on_change
        self._page      = 1
        if initial_page_size is _UNSET:
            self._page_size = PAGE_SIZES[0]
        elif initial_page_size in PAGE_SIZES or initial_page_size is None:
            self._page_size = initial_page_size
        else:
            self._page_size = PAGE_SIZES[0]
        self._total     = 0
        self.grid_propagate(False)
        self._build()

    def _build(self):
        self.grid_columnconfigure(4, weight=1)  # spacer

        # Page size selector
        ctk.CTkLabel(self, text="Hiển thị:",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55")
                     ).grid(row=0, column=0, padx=(12,4), pady=6)

        self._size_var = ctk.StringVar(value=self._display(self._page_size))
        ctk.CTkOptionMenu(self, values=[str(s) for s in PAGE_SIZES] + [ALL_LABEL],
                          variable=self._size_var, width=80, height=26,
                          font=ctk.CTkFont(size=11),
                          command=self._on_size_change
                          ).grid(row=0, column=1, pady=6, padx=(0,8))

        # Prev button
        self._prev_btn = ctk.CTkButton(
            self, text="‹", width=28, height=26, corner_radius=5,
            fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
            font=ctk.CTkFont(size=14),
            command=self._prev)
        self._prev_btn.grid(row=0, column=2, padx=2, pady=5)

        # Page info label
        self._info_lbl = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11),
            text_color=("gray40","gray60"))
        self._info_lbl.grid(row=0, column=3, padx=8)

        # Next button
        self._next_btn = ctk.CTkButton(
            self, text="›", width=28, height=26, corner_radius=5,
            fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
            font=ctk.CTkFont(size=14),
            command=self._next)
        self._next_btn.grid(row=0, column=4, padx=2, pady=5)

        # Spacer
        ctk.CTkFrame(self, fg_color="transparent").grid(row=0, column=5, sticky="ew")

        # Jump-to-page
        ctk.CTkLabel(self, text="Đến trang:",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55")
                     ).grid(row=0, column=6, padx=(0,4))
        self._jump_var = ctk.StringVar()
        jump_entry = ctk.CTkEntry(self, textvariable=self._jump_var,
                                   width=44, height=26,
                                   font=ctk.CTkFont(size=11))
        jump_entry.grid(row=0, column=7, padx=(0,4))
        jump_entry.bind("<Return>", self._on_jump)

        # Total label
        self._total_lbl = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11),
            text_color=("gray50","gray55"))
        self._total_lbl.grid(row=0, column=8, padx=(4,12))

    # ── Public API ────────────────────────────────────────────────────────────

    def set_total(self, total: int):
        """Update total count and refresh display."""
        self._total = total
        # Clamp page to valid range
        max_page = max(1, self._total_pages())
        if self._page > max_page:
            self._page = max_page
        self._refresh()

    @property
    def page(self):
        return self._page

    @property
    def page_size(self):
        return self._page_size

    @property
    def offset(self):
        if self._page_size is None:
            return 0
        return (self._page - 1) * self._page_size

    def reset(self):
        """Go back to page 1 (call when filter changes)."""
        self._page = 1
        self._refresh()

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _display(size):
        return ALL_LABEL if size is None else str(size)

    def _total_pages(self):
        if self._page_size is None or self._total == 0:
            return 1
        return (self._total + self._page_size - 1) // self._page_size

    def _refresh(self):
        tp = self._total_pages()
        self._info_lbl.configure(text=f"  {self._page} / {tp}  ")
        self._total_lbl.configure(text=f"Tổng: {self._total}")
        self._prev_btn.configure(state="normal" if self._page > 1  else "disabled")
        self._next_btn.configure(state="normal" if self._page < tp else "disabled")

    def _prev(self):
        if self._page > 1:
            self._page -= 1
            self._refresh()
            self.on_change(self._page, self._page_size)

    def _next(self):
        if self._page < self._total_pages():
            self._page += 1
            self._refresh()
            self.on_change(self._page, self._page_size)

    def _on_size_change(self, val):
        self._page_size = None if val == ALL_LABEL else int(val)
        self._page = 1
        self._refresh()
        self.on_change(self._page, self._page_size)

    def _on_jump(self, _=None):
        try:
            p = int(self._jump_var.get())
            p = max(1, min(p, self._total_pages()))
            self._page = p
            self._jump_var.set("")
            self._refresh()
            self.on_change(self._page, self._page_size)
        except ValueError:
            self._jump_var.set("")
