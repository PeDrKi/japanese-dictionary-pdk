"""
ui/kanji_decomposition_dialog.py — "🧩 Phân tích bộ" popup.

Shows a kanji broken down recursively into its component parts — e.g.
暗 → 日 + 音, and since 音 is itself decomposable, 音 → 立 + 日 — using
application/decomposition_service.py. Each character's breakdown comes
from a bundled offline dataset (infrastructure/kanji_ids.py) UNLESS the
person has overridden it themselves via the "✏️ Sửa" button here, which
always wins for that character (application/decomposition_service.py's
get_override/set_override/clear_override).

Rendered as a left-to-right node graph (root on the left, its parts to
the right, connected by arrows) — this is the "1 từ gồm những bộ nào"
direction, the mirror image of ui/radical_view.py's radial graph
("1 bộ gồm những từ nào" — bộ in the center, its cards radiating out).
Clicking any node (not just the root) re-opens this same dialog for that
character, so a person can drill down and correct any level of the tree,
not just the top one.
"""
import math
import tkinter as tk
import customtkinter as ctk


class KanjiDecompositionDialog(ctk.CTkToplevel):
    def __init__(self, master, decomposition_service, character: str):
        super().__init__(master)
        self._service = decomposition_service
        self._character = character
        self.title(f"Phân tích bộ — {character}")
        self.geometry("640x520")
        self.minsize(420, 360)
        self.grab_set(); self.lift(); self.focus_force()
        self._build()

    def _build(self):
        self._node_hitboxes = []
        for child in self.winfo_children():
            child.destroy()

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 4))
        ctk.CTkLabel(header, text=f"🧩  「{self._character}」 gồm những bộ nào",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")

        has_override = self._service.get_override(self._character) is not None
        ctk.CTkButton(header, text="✏️ Sửa", width=72, height=28,
                     command=self._edit_override).pack(side="right")
        if has_override:
            ctk.CTkButton(header, text="↺ Dùng lại tự động", width=140, height=28,
                         fg_color="transparent", hover_color=("gray80", "gray30"),
                         text_color=("gray30", "gray80"),
                         command=self._reset_override).pack(side="right", padx=(0, 6))

        badge_text = "✏️ Bạn đã tự sửa bộ phận của chữ này" if has_override else "🤖 Dữ liệu tách bộ tự động"
        ctk.CTkLabel(self, text=badge_text, font=ctk.CTkFont(size=10),
                     text_color=("gray50", "gray55"), anchor="w").pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(
            self,
            text="Mỗi bộ phận được tách tiếp nếu bản thân nó cũng là một chữ có cấu tạo từ các bộ khác.\n"
                 "Bấm vào 1 vòng tròn bất kỳ để xem/sửa riêng bộ phận đó.",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
            justify="left", anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray30")).pack(fill="x", padx=16)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=4, pady=8)

        try:
            tree = self._service.decompose(self._character)
        except Exception:
            ctk.CTkLabel(body, text="Không thể phân tích ký tự này.",
                         text_color=("gray50", "gray55")).pack(pady=40)
        else:
            if not tree.children:
                ctk.CTkLabel(
                    body,
                    text=f"Không tìm thấy dữ liệu phân tách bộ cho「{self._character}」.\n"
                         "Bấm “✏️ Sửa” ở trên để tự nhập.",
                    font=ctk.CTkFont(size=12),
                    text_color=("gray50", "gray55"),
                    wraplength=300, justify="center",
                ).pack(pady=40)
            else:
                self._draw_tree_graph(body, tree)

        ctk.CTkButton(self, text="Đóng", command=self.destroy, height=34,
                      fg_color=("gray75", "gray35"),
                      text_color=("gray10", "gray90")).pack(pady=(0, 14))

    # ── editing ──────────────────────────────────────────────────────────

    def _edit_override(self):
        current = self._service.get_override(self._character)
        if current is None:
            # No override yet — prefill with the auto/current top-level
            # parts so the person edits from a sensible starting point
            # instead of a blank box.
            tree = self._service.decompose(self._character)
            current = "".join(c.character for c in tree.children if c.character)
        EditPartsDialog(self, character=self._character, current_parts=current,
                        on_save=self._save_override)

    def _save_override(self, parts: str):
        self._service.set_override(self._character, parts)
        self._build()

    def _reset_override(self):
        self._service.clear_override(self._character)
        self._build()

    def _open_for(self, character: str):
        KanjiDecompositionDialog(self.master, self._service, character)

    @staticmethod
    def _visible_children(node):
        """Flatten past anonymous grouping nodes (e.g. the "(亠 above 丷)"
        sub-group inside 立's own breakdown, which has no dictionary
        character of its own) so the graph only ever shows real
        characters as nodes."""
        result = []
        for child in node.children:
            if child.character:
                result.append(child)
            else:
                result.extend(KanjiDecompositionDialog._visible_children(child))
        return result

    def _draw_tree_graph(self, parent, root):
        """Left-to-right node graph: root at x=0, each level of parts one
        column to the right, connected by arrows — e.g. 暗 → (日, 音), and
        音 → (立, 日) one column further out. Every node is clickable."""
        is_dark      = ctk.get_appearance_mode() == "Dark"
        bg           = "#1c1c1c" if is_dark else "#fafafa"
        line_color   = "#6b6b6b" if is_dark else "#9a9a9a"
        text_color   = "#e8e8e8" if is_dark else "#222222"
        node_fill    = "#262626" if is_dark else "#ffffff"
        node_outline = "#4A90D9"
        root_outline = "#E8A33D"

        canvas = tk.Canvas(parent, bg=bg, highlightthickness=0, cursor="hand2")
        canvas.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        visible_children = self._visible_children

        def max_depth(node, depth=0):
            vc = visible_children(node)
            if not vc:
                return depth
            return max(max_depth(c, depth + 1) for c in vc)

        def count_leaves(node):
            vc = visible_children(node)
            if not vc:
                return 1
            return sum(count_leaves(c) for c in vc)

        self._node_hitboxes = []  # [(x, y, r, character)]

        def redraw(event=None):
            if not canvas.winfo_exists():
                return
            canvas.delete("all")
            w, h = canvas.winfo_width(), canvas.winfo_height()
            if w < 60 or h < 60:
                return

            node_r  = 30
            depth_n = max(max_depth(root), 1)
            leaf_n  = max(count_leaves(root), 1)
            x_step  = max((w - 2 * node_r - 40) / depth_n, 90)
            y_step  = max((h - 2 * node_r - 40) / leaf_n, 64)

            edges     = []   # (x0, y0, x1, y1)
            positions = []   # (x, y, character, is_root)
            leaf_i    = [0]

            def layout(node, depth):
                x = 20 + node_r + depth * x_step
                vc = visible_children(node)
                if not vc:
                    y = 20 + node_r + leaf_i[0] * y_step
                    leaf_i[0] += 1
                    positions.append((x, y, node.character, depth == 0))
                    return (x, y)
                child_pos = [layout(c, depth + 1) for c in vc]
                y = sum(p[1] for p in child_pos) / len(child_pos)
                for cx, cy in child_pos:
                    edges.append((x, y, cx, cy))
                positions.append((x, y, node.character, depth == 0))
                return (x, y)

            layout(root, 0)

            for x0, y0, x1, y1 in edges:
                dx, dy = x1 - x0, y1 - y0
                dist = math.hypot(dx, dy) or 1
                ux, uy = dx / dist, dy / dist
                canvas.create_line(x0 + ux * node_r, y0 + uy * node_r,
                                   x1 - ux * node_r, y1 - uy * node_r,
                                   fill=line_color, width=1.6,
                                   arrow=tk.LAST, arrowshape=(10, 12, 4))

            self._node_hitboxes = []
            for x, y, ch, is_root in positions:
                canvas.create_oval(x - node_r, y - node_r, x + node_r, y + node_r,
                                   outline=root_outline if is_root else node_outline,
                                   width=2.5 if is_root else 2, fill=node_fill)
                canvas.create_text(x, y, text=ch, fill=text_color,
                                   font=("Noto Sans JP", 16, "bold"))
                self._node_hitboxes.append((x, y, node_r, ch))

        def on_click(event):
            for x, y, r, ch in self._node_hitboxes:
                if math.hypot(event.x - x, event.y - y) <= r:
                    self._open_for(ch)
                    return

        canvas.bind("<Configure>", redraw)
        canvas.bind("<Button-1>", on_click)
        parent.after(30, redraw)


class EditPartsDialog(ctk.CTkToplevel):
    """"✏️ Sửa" — let the person type, from scratch, exactly which
    characters `character` is made of. Each character typed (spaces
    ignored) becomes one component — no IDS-operator syntax needed, since
    the graph doesn't display operators anyway."""

    def __init__(self, master, character: str, current_parts: str, on_save):
        super().__init__(master)
        self._character = character
        self._on_save = on_save
        self.title(f"Sửa bộ phận của {character}")
        self.geometry("360x260")
        self.minsize(320, 240)
        self.grab_set(); self.lift(); self.focus_force()
        self._build(current_parts)

    def _build(self, current_parts: str):
        ctk.CTkLabel(self, text=f"「{self._character}」 gồm những bộ nào?",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=20, pady=(20, 4))
        ctk.CTkLabel(
            self,
            text="Gõ liền các ký tự thành phần, mỗi ký tự là 1 bộ.\n"
                 "VD gõ “日音” nghĩa là 2 phần: 日 và 音.",
            font=ctk.CTkFont(size=11), text_color=("gray50", "gray55"),
            justify="left", anchor="w",
        ).pack(fill="x", padx=20, pady=(0, 10))

        self.entry = ctk.CTkEntry(self, font=ctk.CTkFont(family="Noto Sans JP", size=20))
        self.entry.insert(0, current_parts or "")
        self.entry.pack(fill="x", padx=20, pady=(0, 6))
        self.entry.focus_set()

        ctk.CTkLabel(self, text="Để trống rồi bấm Lưu = không có dữ liệu cho chữ này.",
                     font=ctk.CTkFont(size=10), text_color=("gray55", "gray50"),
                     anchor="w").pack(fill="x", padx=20)

        ctk.CTkButton(self, text="💾  Lưu", height=38, command=self._save
                     ).pack(fill="x", padx=20, pady=(20, 8))

    def _save(self):
        parts = "".join(self.entry.get().split())  # drop whitespace only
        parts = "".join(ch for ch in parts if ch != self._character)  # no self-reference
        self._on_save(parts)
        self.destroy()
