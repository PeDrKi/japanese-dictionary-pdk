"""
ui/radical_view.py — "🧩 Bộ thủ" tab.

Unlike ui/kanji_decomposition_dialog.py (which *explains* a kanji's
structure from the bundled IDS dataset), radicals here are entirely
user-managed: the person creates their own bộ list and decides — by
dragging cards onto a bộ — which cards belong to it. Nothing is
auto-generated from domain/kanji_decomposition.py.

Layout:
  - Left panel: the user's bộ list (add/edit/delete, drag to reorder).
    Each row is also a drop target for cards dragged from the right panel.
  - Right panel, top: detail for the selected bộ — "tra cứu 1 bộ gồm
    nhiều từ thuộc bộ đó" — its assigned cards, each removable.
  - Right panel, bottom: a searchable pool of all cards, draggable onto
    a bộ on the left to assign them.

Drag-and-drop has no native CustomTkinter widget, so it's done by hand:
press-and-hold past a small pixel threshold spawns a small borderless
"ghost" Toplevel that follows the cursor; release looks up whatever
widget is under the cursor and walks up its parent chain looking for a
marker attribute (`_radical_id` on bộ rows) to know what was dropped on.
"""
import math
import tkinter as tk
import customtkinter as ctk
from ui.tooltip import Tooltip

DRAG_THRESHOLD_PX = 6


def _make_draggable(widget, get_payload, on_drop, on_click=None):
    """Wire up press/drag/release on `widget`.

    get_payload() -> dict describing what's being dragged (used for the
    ghost label text and passed to on_drop).
    on_drop(payload, target_widget) is called with whatever widget the
    cursor was over on release (target_widget may be None).
    on_click() is called instead, if the mouse never moved past the drag
    threshold — i.e. this was just a click, not a drag.
    """
    state = {"ghost": None, "start": None}

    def start(event):
        state["start"] = (event.x_root, event.y_root)
        state["ghost"] = None

    def motion(event):
        if state["start"] is None:
            return
        dx = event.x_root - state["start"][0]
        dy = event.y_root - state["start"][1]
        if state["ghost"] is None and (abs(dx) > DRAG_THRESHOLD_PX or abs(dy) > DRAG_THRESHOLD_PX):
            payload = get_payload()
            ghost = ctk.CTkToplevel(widget)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            try:
                ghost.attributes("-alpha", 0.85)
            except Exception:
                pass
            ctk.CTkLabel(ghost, text=payload.get("label", "?"),
                         font=ctk.CTkFont(size=16, weight="bold"),
                         fg_color=("gray85", "gray25"), corner_radius=6
                         ).pack(padx=10, pady=4)
            state["ghost"] = ghost
            state["payload"] = payload
        if state["ghost"] is not None:
            state["ghost"].geometry(f"+{event.x_root + 12}+{event.y_root + 12}")

    def release(event):
        ghost = state["ghost"]
        state["ghost"] = None
        start = state["start"]
        state["start"] = None
        if ghost is None:
            if start is not None and on_click:
                on_click()
            return
        ghost.destroy()
        root = widget.winfo_toplevel()
        target = root.winfo_containing(event.x_root, event.y_root)
        on_drop(state["payload"], target)

    widget.bind("<ButtonPress-1>", start, add="+")
    widget.bind("<B1-Motion>", motion, add="+")
    widget.bind("<ButtonRelease-1>", release, add="+")


def _find_marker(widget, attr, max_levels=8):
    """Walk up from `widget` looking for an ancestor (or itself) carrying
    attribute `attr`. Needed because the cursor usually lands on some
    inner label/frame, not the row we tagged."""
    w = widget
    for _ in range(max_levels):
        if w is None:
            return None
        if hasattr(w, attr):
            return getattr(w, attr)
        w = getattr(w, "master", None)
    return None


class RadicalView(ctk.CTkFrame):
    def __init__(self, master, card_service, radical_service, **kwargs):
        super().__init__(master, corner_radius=0, **kwargs)
        self._card_service     = card_service
        self._radical_service  = radical_service
        self._selected_id      = None
        self._search_var       = ctk.StringVar()
        self._build()

    # ── layout ───────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Left: bộ thủ list ──
        left = ctk.CTkFrame(self, width=270, corner_radius=0, fg_color=("gray92", "gray14"))
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(left, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(14, 2))
        ctk.CTkLabel(header, text="🧩 Bộ thủ của bạn",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="+ Thêm bộ", width=90, height=28,
                      command=self._add_radical).pack(side="right")

        ctk.CTkLabel(left, text="Kéo thẻ từ danh sách bên phải vào\n"
                                 "1 bộ để gán. Kéo ⠿ để sắp xếp lại.",
                     font=ctk.CTkFont(size=10), text_color=("gray45", "gray60"),
                     justify="left", anchor="w").grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        self._radical_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._radical_list.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 10))

        # ── Right: selected-bộ detail + card pool ──
        right = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(3, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._detail_frame = ctk.CTkFrame(right, fg_color=("gray90", "gray17"), corner_radius=8)
        self._detail_frame.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))

        ctk.CTkFrame(right, height=1, fg_color=("gray80", "gray28")).grid(
            row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        search_row = ctk.CTkFrame(right, fg_color="transparent")
        search_row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))
        ctk.CTkLabel(search_row, text="Tất cả thẻ — kéo vào 1 bộ bên trái để gán:",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        entry = ctk.CTkEntry(search_row, textvariable=self._search_var,
                             placeholder_text="🔍 Tìm...", width=180)
        entry.pack(side="right")
        self._search_var.trace_add("write", lambda *_: self._render_pool())

        self._pool_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self._pool_scroll.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 14))

        self.refresh()

    # ── data loading / rendering ────────────────────────────────────────────

    def refresh(self):
        self._radicals = self._radical_service.list_radicals()
        if self._selected_id not in {r["id"] for r in self._radicals}:
            self._selected_id = None
        self._render_radicals()
        self._render_detail()
        self._render_pool()

    def _render_radicals(self):
        for child in self._radical_list.winfo_children():
            child.destroy()

        if not self._radicals:
            ctk.CTkLabel(self._radical_list,
                         text="Chưa có bộ nào.\nBấm “+ Thêm bộ” để bắt đầu.",
                         font=ctk.CTkFont(size=11), text_color=("gray50", "gray55"),
                         justify="center").pack(pady=30)
            return

        for r in self._radicals:
            selected = (r["id"] == self._selected_id)
            row = ctk.CTkFrame(
                self._radical_list, corner_radius=6,
                fg_color=("gray100", "gray24") if selected else ("gray96", "gray19"),
                border_width=2 if selected else 0,
                border_color=r.get("color") or "#4A90D9",
            )
            row.pack(fill="x", pady=3, padx=2)
            row._radical_id = r["id"]  # drop-target / reorder-target marker

            handle = ctk.CTkLabel(row, text="⠿", font=ctk.CTkFont(size=14),
                                  text_color=("gray55", "gray55"), width=18, cursor="fleur")
            handle.grid(row=0, column=0, rowspan=2, padx=(6, 0), pady=6)

            glyph = ctk.CTkLabel(row, text=r["character"],
                                 font=ctk.CTkFont(family="Noto Sans JP", size=22, weight="bold"),
                                 text_color=r.get("color") or None, width=36)
            glyph.grid(row=0, column=1, rowspan=2, padx=(4, 8), pady=6)

            name = r.get("name") or "(chưa đặt tên)"
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.grid(row=0, column=2, sticky="ew", pady=(6, 0))
            row.grid_columnconfigure(2, weight=1)
            ctk.CTkLabel(info, text=name, font=ctk.CTkFont(size=12),
                         anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=f"{r.get('card_count', 0)} thẻ",
                         font=ctk.CTkFont(size=10), text_color=("gray50", "gray55"),
                         anchor="w").grid(row=1, column=2, sticky="w", padx=0, pady=(0, 6))

            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.grid(row=0, column=3, rowspan=2, padx=6)
            ctk.CTkButton(btns, text="✏️", width=26, height=26, fg_color="transparent",
                         hover_color=("gray85", "gray30"),
                         command=lambda r=r: self._edit_radical(r)).pack(side="left")
            ctk.CTkButton(btns, text="🗑️", width=26, height=26, fg_color="transparent",
                         hover_color=("gray85", "gray30"),
                         command=lambda r=r: self._delete_radical(r)).pack(side="left")

            # Clicking anywhere on the row (except the buttons) selects it;
            # dragging ⠿ (or the glyph/name area) reorders the bộ list itself.
            _make_draggable(
                row,
                get_payload=lambda r=r: {"kind": "radical", "id": r["id"], "label": r["character"]},
                on_drop=self._on_radical_dropped,
                on_click=lambda r=r: self._select_radical(r["id"]),
            )
            for w in (glyph, info, handle):
                _make_draggable(
                    w,
                    get_payload=lambda r=r: {"kind": "radical", "id": r["id"], "label": r["character"]},
                    on_drop=self._on_radical_dropped,
                    on_click=lambda r=r: self._select_radical(r["id"]),
                )

    def _render_detail(self):
        for child in self._detail_frame.winfo_children():
            child.destroy()

        if self._selected_id is None:
            ctk.CTkLabel(self._detail_frame,
                         text="Chọn 1 bộ bên trái để xem các từ thuộc bộ đó.",
                         font=ctk.CTkFont(size=12), text_color=("gray50", "gray55"),
                         anchor="w").pack(fill="x", padx=14, pady=14)
            return

        radical = next((r for r in self._radicals if r["id"] == self._selected_id), None)
        if radical is None:
            return
        cards = self._radical_service.get_cards_for_radical(self._selected_id)

        title = ctk.CTkLabel(
            self._detail_frame,
            text=f"「{radical['character']}」 {radical.get('name') or ''} — {len(cards)} thẻ",
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
        title.pack(fill="x", padx=14, pady=(12, 6))

        if not cards:
            ctk.CTkLabel(self._detail_frame,
                         text="Chưa có thẻ nào trong bộ này — kéo thẻ từ danh sách bên dưới vào bộ này.",
                         font=ctk.CTkFont(size=11), text_color=("gray50", "gray55"),
                         anchor="w").pack(fill="x", padx=14, pady=(0, 12))
            return

        ctk.CTkLabel(self._detail_frame, text="Bấm vào 1 thẻ trong sơ đồ để gỡ khỏi bộ.",
                     font=ctk.CTkFont(size=10), text_color=("gray50", "gray55"),
                     anchor="w").pack(fill="x", padx=14, pady=(0, 4))
        self._draw_radial_graph(self._detail_frame, radical, cards)

    def _draw_radial_graph(self, parent, radical: dict, cards: list):
        """Center node = the bộ itself; surrounding nodes = each card that
        contains it, with an arrow pointing outward — the layout the user
        asked for (see the reference screenshot: 雨 in the middle, 電/雲/雪
        radiating out from it)."""
        is_dark    = ctk.get_appearance_mode() == "Dark"
        bg         = "#1c1c1c" if is_dark else "#fafafa"
        line_color = "#6b6b6b" if is_dark else "#9a9a9a"
        text_color = "#e8e8e8" if is_dark else "#222222"
        node_fill  = "#262626" if is_dark else "#ffffff"

        canvas = tk.Canvas(parent, bg=bg, highlightthickness=0, height=280)
        canvas.pack(fill="both", expand=True, padx=10, pady=(0, 12))

        node_palette = ["#E8A33D", "#4A90D9", "#4ECB85", "#E85D5D",
                        "#9B7FE8", "#4ECDC4", "#FF6B9D"]
        self._graph_nodes = []  # [(x, y, radius, card_id)] for click hit-testing

        def redraw(event=None):
            if not canvas.winfo_exists():
                return
            canvas.delete("all")
            w, h = canvas.winfo_width(), canvas.winfo_height()
            if w < 40 or h < 40:
                return
            cx, cy = w // 2, h // 2
            center_r = 30
            node_r   = 26
            ring_r   = max(min(w, h) // 2 - node_r - 12, 70)

            self._graph_nodes = []
            n = len(cards)
            for i, c in enumerate(cards):
                angle = (2 * math.pi * i / n) - math.pi / 2  # start at 12 o'clock, clockwise
                x = cx + ring_r * math.cos(angle)
                y = cy + ring_r * math.sin(angle)
                color = node_palette[i % len(node_palette)]

                dx, dy = x - cx, y - cy
                dist = math.hypot(dx, dy) or 1
                ux, uy = dx / dist, dy / dist
                x0, y0 = cx + ux * center_r, cy + uy * center_r
                x1, y1 = x - ux * node_r, y - uy * node_r
                canvas.create_line(x0, y0, x1, y1, fill=line_color, width=1.6,
                                   arrow=tk.LAST, arrowshape=(10, 12, 4))
                canvas.create_oval(x - node_r, y - node_r, x + node_r, y + node_r,
                                   outline=color, width=2, fill=node_fill)
                canvas.create_text(x, y, text=c["character"], fill=text_color,
                                   font=("Noto Sans JP", 15, "bold"))
                self._graph_nodes.append((x, y, node_r, c["id"]))

            # center node drawn last so its arrows tuck underneath it
            canvas.create_oval(cx - center_r, cy - center_r, cx + center_r, cy + center_r,
                               outline=radical.get("color") or "#4A90D9", width=2.5, fill=node_fill)
            canvas.create_text(cx, cy, text=radical["character"], fill=text_color,
                               font=("Noto Sans JP", 19, "bold"))

        def on_click(event):
            for x, y, r, card_id in self._graph_nodes:
                if math.hypot(event.x - x, event.y - y) <= r:
                    self._remove_card(card_id)
                    return

        canvas.bind("<Configure>", redraw)
        canvas.bind("<Button-1>", on_click)
        parent.after(30, redraw)

    def _render_pool(self):
        for child in self._pool_scroll.winfo_children():
            child.destroy()

        query = self._search_var.get().strip()
        cards = self._card_service.list_cards(search=query) if query else self._card_service.list_cards()

        if not cards:
            ctk.CTkLabel(self._pool_scroll, text="Không có thẻ nào.",
                         font=ctk.CTkFont(size=11), text_color=("gray50", "gray55")).pack(pady=20)
            return

        wrap = ctk.CTkFrame(self._pool_scroll, fg_color="transparent")
        wrap.pack(fill="both", expand=True)
        row_frame = None
        for i, c in enumerate(cards):
            if i % 6 == 0:
                row_frame = ctk.CTkFrame(wrap, fg_color="transparent")
                row_frame.pack(fill="x")
            chip = ctk.CTkFrame(row_frame, fg_color=("gray95", "gray20"), corner_radius=8,
                                cursor="hand2")
            chip.pack(side="left", padx=5, pady=5)
            ctk.CTkLabel(chip, text=c["character"],
                         font=ctk.CTkFont(family="Noto Sans JP", size=20, weight="bold")
                         ).pack(padx=10, pady=4)
            ctk.CTkLabel(chip, text=(c.get("meaning_vi") or "")[:14],
                         font=ctk.CTkFont(size=9), text_color=("gray50", "gray55")
                         ).pack(padx=6, pady=(0, 4))
            Tooltip(chip, "Kéo vào 1 bộ bên trái để gán")
            _make_draggable(
                chip,
                get_payload=lambda c=c: {"kind": "card", "id": c["id"], "label": c["character"]},
                on_drop=self._on_card_dropped,
            )
            for grandchild in chip.winfo_children():
                _make_draggable(
                    grandchild,
                    get_payload=lambda c=c: {"kind": "card", "id": c["id"], "label": c["character"]},
                    on_drop=self._on_card_dropped,
                )

    # ── drag/drop handling ──────────────────────────────────────────────────

    def _on_card_dropped(self, payload, target_widget):
        if payload.get("kind") != "card" or target_widget is None:
            return
        radical_id = _find_marker(target_widget, "_radical_id")
        if radical_id is None:
            return
        self._radical_service.add_card(radical_id, payload["id"])
        self._selected_id = radical_id
        self.refresh()

    def _on_radical_dropped(self, payload, target_widget):
        if payload.get("kind") != "radical" or target_widget is None:
            return
        target_id = _find_marker(target_widget, "_radical_id")
        if target_id is None or target_id == payload["id"]:
            return
        ids = [r["id"] for r in self._radicals]
        ids.remove(payload["id"])
        target_pos = ids.index(target_id)
        ids.insert(target_pos, payload["id"])
        self._radical_service.reorder(ids)
        self.refresh()

    # ── actions ──────────────────────────────────────────────────────────────

    def _select_radical(self, radical_id):
        self._selected_id = radical_id
        self._render_radicals()
        self._render_detail()

    def _remove_card(self, card_id):
        if self._selected_id is None:
            return
        self._radical_service.remove_card(self._selected_id, card_id)
        self.refresh()

    def _add_radical(self):
        RadicalDialog(self, on_save=self._create_radical)

    def _create_radical(self, character, name, color):
        new_id = self._radical_service.add(character, name, color)
        self._selected_id = new_id
        self.refresh()

    def _edit_radical(self, r: dict):
        RadicalDialog(self, on_save=lambda ch, nm, co: self._update_radical(r["id"], ch, nm, co),
                      initial=r)

    def _update_radical(self, radical_id, character, name, color):
        self._radical_service.update(radical_id, character, name, color)
        self.refresh()

    def _delete_radical(self, r: dict):
        from tkinter import messagebox
        if messagebox.askyesno(
            "Xóa bộ",
            f"Xóa bộ 「{r['character']}」? Các thẻ đã gán sẽ không bị xóa, "
            "chỉ gỡ khỏi bộ này."):
            self._radical_service.delete(r["id"])
            if self._selected_id == r["id"]:
                self._selected_id = None
            self.refresh()


class RadicalDialog(ctk.CTkToplevel):
    """Add/edit a bộ. `initial`, if given, prefills for editing."""
    COLORS = ["#4ECDC4", "#F0B429", "#E85D5D", "#9B7FE8", "#4ECB85", "#4A90D9", "#FF6B9D"]

    def __init__(self, master, on_save, initial: dict = None):
        super().__init__(master)
        self.on_save = on_save
        self._initial = initial or {}
        self.title("Sửa bộ" if initial else "Thêm bộ mới")
        self.geometry("340x300")
        self.minsize(320, 280)
        self.grab_set(); self.lift(); self.focus_force()
        self._build()

    def _build(self):
        p = {"padx": 20, "pady": 6}
        ctk.CTkLabel(self, text="Ký tự bộ *", font=ctk.CTkFont(weight="bold")).pack(anchor="w", **p)
        self.char_entry = ctk.CTkEntry(self, placeholder_text="VD: 日")
        self.char_entry.insert(0, self._initial.get("character", ""))
        self.char_entry.pack(fill="x", **p)

        ctk.CTkLabel(self, text="Tên / ý nghĩa").pack(anchor="w", **p)
        self.name_entry = ctk.CTkEntry(self, placeholder_text="VD: bộ Nhật (mặt trời)")
        self.name_entry.insert(0, self._initial.get("name", ""))
        self.name_entry.pack(fill="x", **p)

        ctk.CTkLabel(self, text="Màu sắc").pack(anchor="w", **p)
        color_f = ctk.CTkFrame(self, fg_color="transparent")
        color_f.pack(fill="x", padx=20)
        self.color_var = ctk.StringVar(value=self._initial.get("color") or self.COLORS[0])
        for c in self.COLORS:
            ctk.CTkRadioButton(color_f, text="●", variable=self.color_var,
                               value=c, text_color=c, width=32).pack(side="left", padx=1)

        ctk.CTkButton(self, text="💾  Lưu", command=self._save,
                      height=38).pack(fill="x", padx=20, pady=(20, 8))

    def _save(self):
        character = self.char_entry.get().strip()
        if character:
            self.on_save(character, self.name_entry.get().strip(), self.color_var.get())
            self.destroy()
