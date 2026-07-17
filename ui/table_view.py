"""
table_view.py — Main table area orchestrator.
Composes: Toolbar, Treeview, CardDetail, Paginator, BulkBar, undo toast.
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from database.models import DBError
from infrastructure.csv_handler import export_csv, import_csv, get_csv_template_path
from infrastructure.anki_export import export_apkg
from ui.card_form import CardForm
from ui.quick_add_dialog import QuickAddDialog
from ui.card_detail import CardDetail
from ui.trash_view import TrashView
from ui.paginator import Paginator, PAGE_SIZES
from ui.toolbar import Toolbar
from ui.bulk_actions import BulkBar
from ui.undo_toast import UndoToast
from constants import (
    TYPE_LABELS, KB_DELETE, KB_SELECT_ALL,
    SETTING_COL_WIDTHS, SETTING_DETAIL_PANEL, SETTING_PAGE_SIZE,
)
from infrastructure import settings
from domain.table_helpers import sort_cards, clamp_column_widths
import logging
import os

logger = logging.getLogger(__name__)

# ── Column definitions ────────────────────────────────────────────────────────
COLUMNS = [
    ("id",           "ID",        45,  False),
    ("type",         "Loại",      55,  True),
    ("character",    "Ký tự",     90,  True),
    ("reading_on",   "On-yomi",   100, True),
    ("reading_kun",  "Kun-yomi",  110, True),
    ("reading_kana", "Kana",      100, True),
    ("reading_hanviet", "Hán Việt", 100, True),
    ("romaji",       "Romaji",    100, True),
    ("meaning_vi",   "Nghĩa VN",  160, True),
    ("jlpt_level",   "JLPT",      50,  True),
    ("status",       "Status",    80,  True),
    ("is_favorite",  "★",         35,  True),
    ("source",       "Nguồn",     100, True),
    ("created_at",   "Ngày thêm", 95,  True),
]


class TableView(ctk.CTkFrame):
    def __init__(self, master, card_service, deck_service, **kwargs):
        super().__init__(master, corner_radius=0, **kwargs)
        self._card_service   = card_service
        self._deck_service   = deck_service
        self._filter        = ("all", None)
        self._cards         = []
        self._sort_col      = None
        self._sort_asc      = True
        self._detail_visible= settings.get(SETTING_DETAIL_PANEL, True)
        self._search_after_id = None
        self._build()
        self.load_cards()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(2, weight=1)  # treeview row
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # ── Toolbar (row 0) ──
        self._toolbar = Toolbar(
            self,
            on_search        = self._on_search,
            on_filter_change = self._on_filter_ui_change,
            on_add           = self._add_card,
            on_quick_add     = self._open_quick_add,
            on_import        = self._import_csv,
            on_export        = self._export_csv,
            on_export_anki   = self._export_anki,
            on_template      = self._download_template,
            on_toggle_detail = self._toggle_detail,
            on_toggle_trash  = self._open_trash,
        )
        self._toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")

        # ── Advanced filter panel (row 1, hidden by default) ──
        self._adv_bar = self._toolbar.build_advanced_panel(self)

        # ── Treeview (row 2, column 0) ──
        tree_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self._style = ttk.Style()
        self._apply_style()

        col_ids = [c[0] for c in COLUMNS]
        self.tree = ttk.Treeview(tree_frame, columns=col_ids,
                                  show="headings", selectmode="extended",
                                  style="JP.Treeview")

        # Restore or set default column widths (clamped — a corrupted/edited
        # settings.json shouldn't be able to produce an unusable table)
        saved_widths = clamp_column_widths(settings.get(SETTING_COL_WIDTHS, {}), COLUMNS)
        for cid, heading, default_w, stretch in COLUMNS:
            w = saved_widths.get(cid, default_w)
            self.tree.heading(cid, text=heading,
                              command=lambda c=cid: self._sort(c))
            self.tree.column(cid, width=w, minwidth=30,
                             stretch=tk.YES if stretch else tk.NO,
                             anchor="center")
        self.tree.column("meaning_vi",  anchor="w")
        self.tree.column("reading_kun", anchor="w")
        self.tree.column("reading_on",  anchor="center")
        self.tree.column("reading_kana",anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self._vsb_set = vsb.set   # cache reference for _populate optimization
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Bindings
        self.tree.bind("<<TreeviewSelect>>",  self._on_select)
        self.tree.bind("<Double-1>",          lambda _: self._edit_selected())
        self.tree.bind("<Button-3>",          self._right_click)
        self.tree.bind(KB_DELETE,             lambda _: self._delete_selected())
        self.tree.bind(KB_SELECT_ALL,         self._select_all)
        self.tree.bind("<ButtonRelease-1>",   self._on_col_resize)

        # Dự phòng chuyển trang bằng bàn phím — vẫn dùng được dù thanh phân
        # trang bên dưới có bị khuất/che (vd cửa sổ tràn ra ngoài màn hình).
        self.tree.bind("<Prior>", lambda _: self._paginator_key_prev())  # PageUp
        self.tree.bind("<Next>",  lambda _: self._paginator_key_next())  # PageDown

        # Context menu
        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="✏️  Sửa",              command=self._edit_selected)
        self._menu.add_command(label="⭐  Toggle yêu thích", command=self._toggle_fav)
        self._menu.add_separator()
        self._menu.add_command(label="🗑️  Xóa",              command=self._delete_selected)

        # ── Detail panel (row 2, column 1) ──
        self._detail = CardDetail(
            self,
            self._deck_service,
            on_edit        = self._edit_card,
            on_delete      = self._delete_card,
            on_toggle_fav  = self._toggle_fav_card,
            fg_color       = ("gray93","gray17"),
        )
        if self._detail_visible:
            self._detail.grid(row=2, column=1, sticky="nsew")
        self._toolbar.set_detail_btn_text(self._detail_visible)

        # ── Status bar (row 3) ──
        self._statusbar = ctk.CTkLabel(
            self, text="", height=24, anchor="w",
            fg_color=("gray88","gray20"),
            font=ctk.CTkFont(size=11), corner_radius=0)
        self._statusbar.grid(row=3, column=0, columnspan=2, sticky="ew")

        # ── Paginator (row 4) ──
        self._paginator = Paginator(
            self, on_change=self._on_page_change,
            initial_page_size=settings.get(SETTING_PAGE_SIZE, PAGE_SIZES[0]))
        self._paginator.grid(row=4, column=0, columnspan=2, sticky="ew")

        # ── Bulk bar (row 5, hidden until multi-select) ──
        self._bulk_bar = BulkBar(self, self._card_service, self._deck_service,
                                  on_done=lambda: (self.load_cards(), self._notify_sidebar()))
        self._bulk_bar.set_ids_fn(self._bulk_selected_ids)

    def _apply_style(self):
        dark = ctk.get_appearance_mode() == "Dark"
        bg   = "#1e2130" if dark else "#f5f5f5"
        fg   = "#e8eaf0" if dark else "#1a1a2e"
        sel  = "#3d4f7c" if dark else "#cce0ff"
        head = "#161927" if dark else "#dde0e8"
        even = "#252840" if dark else "#f0f4ff"
        self._style.theme_use("clam")
        self._style.configure("JP.Treeview",
            background=bg, foreground=fg, fieldbackground=bg,
            rowheight=30, font=("Segoe UI", 11), borderwidth=0)
        self._style.configure("JP.Treeview.Heading",
            background=head, foreground=fg,
            font=("Segoe UI", 11, "bold"), relief="flat")
        self._style.map("JP.Treeview",
            background=[("selected", sel)],
            foreground=[("selected", fg)])
        if hasattr(self, "tree"):
            self.tree.tag_configure("odd",  background=bg)
            self.tree.tag_configure("even", background=even)
            self.tree.tag_configure("fav",  foreground="#F0B429")

    # ── Filter / Search ───────────────────────────────────────────────────────

    def set_filter(self, filter_val):
        self._filter = filter_val
        self._toolbar.reset_filters()
        self._paginator.reset()
        self.load_cards()

    def _on_search(self, _text):
        """Debounced — called by Toolbar on every keystroke."""
        if self._search_after_id:
            try: self.after_cancel(self._search_after_id)
            except Exception: pass
        self._paginator.reset()
        self._search_after_id = self.after(300, lambda: (self.load_cards() if self.winfo_exists() else None))

    def _on_filter_ui_change(self):
        self._paginator.reset()
        self.load_cards()

    def _on_page_change(self, _page, size):
        settings.set(SETTING_PAGE_SIZE, size)
        self.load_cards()

    def _paginator_key_prev(self):
        self._paginator._prev()

    def _paginator_key_next(self):
        self._paginator._next()

    # ── Data loading ──────────────────────────────────────────────────────────

    def load_cards(self):
        try:
            self._load_inner()
        except DBError as e:
            logger.error(f"load_cards failed: {e}")
            messagebox.showerror("Lỗi database", str(e))

    def _load_inner(self):
        kind, val    = self._filter
        tb           = self._toolbar
        search       = tb.search or None
        jlpt         = tb.jlpt
        status       = "new" if kind == "new_status" else tb.status
        adv_type     = None if kind == "type" else tb.adv_type
        effective_type = val if kind == "type" else adv_type
        fav_only     = tb.adv_fav_only or (kind == "favorite")
        ex_filter    = tb.adv_example
        source_q     = tb.adv_source

        kw = dict(
            search        = search,
            jlpt_filter   = jlpt,
            status_filter = status,
            type_filter   = effective_type,
            favorite_only = fav_only,
            deck_id       = val if kind == "deck" else None,
        )

        needs_post = ex_filter != "Tất cả" or bool(source_q)

        if needs_post:
            all_cards = self._card_service.list_cards(**kw)
            if ex_filter == "Có ví dụ":
                all_cards = [c for c in all_cards if c.get("example_jp")]
            elif ex_filter == "Chưa có ví dụ":
                all_cards = [c for c in all_cards if not c.get("example_jp")]
            if source_q:
                all_cards = [c for c in all_cards
                             if source_q in (c.get("source") or "").lower()]
            total = len(all_cards)
            self._paginator.set_total(total)
            off  = self._paginator.offset
            size = self._paginator.page_size
            self._cards = all_cards[off:] if size is None else all_cards[off: off + size]
        else:
            total = self._card_service.count(**kw)
            self._paginator.set_total(total)
            self._cards = self._card_service.list_cards(
                **kw, limit=self._paginator.page_size,
                offset=self._paginator.offset)

        self._populate()
        self._detail.clear()

    def _populate(self):
        # Temporarily detach the tree's yscrollcommand to avoid
        # scroll callback overhead during bulk insert
        self.tree.configure(yscrollcommand=lambda *a: None)

        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)

        insert  = self.tree.insert
        tlabels = TYPE_LABELS
        for i, c in enumerate(self._cards):
            tags = ("even",) if i % 2 == 0 else ("odd",)
            if c.get("is_favorite"):
                tags = tags + ("fav",)
            t = c["type"]
            insert("", "end", iid=str(c["id"]), tags=tags, values=(
                c["id"],
                tlabels.get(t, t),
                c["character"],
                c.get("reading_on")   or "",
                c.get("reading_kun")  or "",
                c.get("reading_kana") or "",
                c.get("reading_hanviet") or "",
                c.get("romaji")       or "",
                c.get("meaning_vi")   or "",
                c.get("jlpt_level")   or "",
                c.get("status")       or "",
                "★" if c.get("is_favorite") else "",
                c.get("source")       or "",
                (c.get("created_at") or "")[:10],
            ))

        # Restore scrollbar binding
        self.tree.configure(yscrollcommand=self._vsb_set)

        pg = self._paginator
        self._statusbar.configure(
            text=f"   Trang {pg.page}/{pg._total_pages()} — {pg._total} thẻ")

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_select(self, _=None):
        sel = self.tree.selection()
        if len(sel) > 1:
            self._bulk_bar.update_count(len(sel))
            self._bulk_bar.grid(row=5, column=0, columnspan=2, sticky="ew")
            self._detail.clear()
        else:
            self._bulk_bar.grid_remove()
            card = self._selected_card()
            if card:
                self._detail.load_card(card)
            else:
                self._detail.clear()

    def _select_all(self, _=None):
        self.tree.selection_set(self.tree.get_children())

    def _selected_card(self):
        sel = self.tree.selection()
        if not sel:
            return None
        cid = int(sel[0])
        return next((c for c in self._cards if c["id"] == cid), None)

    def _bulk_selected_ids(self):
        return [int(iid) for iid in self.tree.selection()]

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _add_card(self):
        def save(data):
            try:
                self._card_service.add(data)
                self.load_cards()
                self._notify_sidebar()
            except DBError as e:
                messagebox.showerror("Lỗi", str(e))
        CardForm(self, self._card_service, on_save=save)

    def _open_quick_add(self):
        QuickAddDialog(self, self._card_service,
                       on_done=lambda: (self.load_cards(), self._notify_sidebar()))

    def _edit_selected(self):
        card = self._selected_card()
        if card:
            self._edit_card(card)

    def _edit_card(self, card):
        def save(data):
            try:
                self._card_service.update(card["id"], data)
                self.load_cards()
                updated = self._card_service.get(card["id"])
                if updated:
                    self._detail.load_card(updated)
            except DBError as e:
                messagebox.showerror("Lỗi", str(e))
        CardForm(self, self._card_service, on_save=save, card=card)

    def _delete_selected(self):
        card = self._selected_card()
        if card:
            self._delete_card(card)

    def _delete_card(self, card):
        if messagebox.askyesno("Xóa thẻ",
                f"Chuyển «{card['character']}» vào thùng rác?\nBạn có thể khôi phục sau."):
            try:
                self._card_service.soft_delete(card["id"])
                logger.info(f"Soft deleted card id={card['id']}")
                self._detail.clear()
                self.load_cards()
                self._notify_sidebar()
                self._show_undo_toast(card)
            except DBError as e:
                messagebox.showerror("Lỗi", str(e))

    def _toggle_fav(self):
        card = self._selected_card()
        if card:
            self._toggle_fav_card(card)

    def _toggle_fav_card(self, card):
        try:
            self._card_service.toggle_favorite(card["id"])
            self.load_cards()
            updated = self._card_service.get(card["id"])
            if updated:
                self._detail.load_card(updated)
        except DBError as e:
            messagebox.showerror("Lỗi", str(e))

    def _right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self._menu.tk_popup(event.x_root, event.y_root)

    # ── Sorting ───────────────────────────────────────────────────────────────

    def _sort(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            # Reset previous column heading
            if self._sort_col:
                self._reset_heading(self._sort_col)
            self._sort_col = col
            self._sort_asc = True

        self._cards = sort_cards(self._cards, col, ascending=self._sort_asc)

        self._update_sort_heading(col)
        self._populate()

    def _update_sort_heading(self, col: str):
        """Add ↑ or ↓ indicator to the sorted column heading."""
        indicator = " ↑" if self._sort_asc else " ↓"
        # Find original heading text
        for cid, heading, *_ in COLUMNS:
            if cid == col:
                self.tree.heading(col, text=heading + indicator)
            elif cid == self._sort_col and cid != col:
                self.tree.heading(cid, text=heading)

    def _reset_heading(self, col: str):
        """Remove sort indicator from a column heading."""
        for cid, heading, *_ in COLUMNS:
            if cid == col:
                self.tree.heading(col, text=heading)
                break

    # ── Column resize persistence ─────────────────────────────────────────────

    def _on_col_resize(self, _event=None):
        """Save column widths whenever user resizes a column."""
        if not hasattr(self, "tree"):
            return
        widths = {cid: self.tree.column(cid, "width") for cid, *_ in COLUMNS}
        settings.set(SETTING_COL_WIDTHS, widths)

    # ── CSV ───────────────────────────────────────────────────────────────────

    def _import_csv(self):
        path = filedialog.askopenfilename(
            title="Chọn file CSV", filetypes=[("CSV","*.csv"),("All","*.*")])
        if not path:
            return
        rows, errors = import_csv(path)
        if errors:
            msg = "\n".join(f"Dòng {r}: {m}" for r,m in errors[:10])
            if not messagebox.askyesno("Có lỗi",
                    f"{len(errors)} dòng lỗi:\n{msg}\n\nVẫn import {len(rows)} dòng hợp lệ?"):
                return
        for row in rows:
            self._card_service.add(row)
        self.load_cards()
        self._notify_sidebar()
        messagebox.showinfo("Import xong", f"Đã import {len(rows)} thẻ.")

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            title="Lưu CSV", defaultextension=".csv",
            filetypes=[("CSV","*.csv")])
        if not path:
            return
        n = export_csv(self._cards, path)
        messagebox.showinfo("Export xong", f"Đã export {n} thẻ.")

    def _download_template(self):
        folder = filedialog.askdirectory(title="Chọn thư mục lưu template")
        if not folder:
            return
        path = get_csv_template_path(folder)
        messagebox.showinfo("Template", f"Đã lưu:\n{path}")

    # ── Trash / Undo ──────────────────────────────────────────────────────────

    def _open_trash(self):
        TrashView(self, self._card_service, on_restore=lambda: (self.load_cards(), self._notify_sidebar()))

    def _show_undo_toast(self, card: dict):
        UndoToast.show(
            self,
            message=f"🗑️  Đã chuyển «{card['character']}» vào thùng rác",
            on_undo=lambda cid=card["id"]: self._undo_delete(cid)
        )

    def _undo_delete(self, card_id: int):
        try:
            self._card_service.restore(card_id)
            self.load_cards()
            self._notify_sidebar()
        except DBError as e:
            messagebox.showerror("Lỗi", str(e))

    # ── Detail panel toggle ───────────────────────────────────────────────────

    def _toggle_detail(self):
        self._detail_visible = not self._detail_visible
        settings.set(SETTING_DETAIL_PANEL, self._detail_visible)
        if self._detail_visible:
            self._detail.grid(row=2, column=1, sticky="nsew")
        else:
            self._detail.grid_remove()
        self._toolbar.set_detail_btn_text(self._detail_visible)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _focus_search(self):
        self._toolbar.focus_search()

    def _export_anki(self):
        """Export current cards to Anki .apkg file."""
        if not self._cards:
            messagebox.showinfo("Anki Export", "Không có thẻ để export.")
            return
        path = filedialog.asksaveasfilename(
            title="Lưu file Anki",
            defaultextension=".apkg",
            filetypes=[("Anki Package", "*.apkg"), ("All", "*.*")])
        if not path:
            return
        deck_name = os.path.splitext(os.path.basename(path))[0]
        count, err = export_apkg(self._cards, deck_name, path)
        if err:
            messagebox.showerror("Lỗi Anki Export", err)
        else:
            messagebox.showinfo("Export xong",
                f"Đã export {count} thẻ sang Anki:\n"
                f"{os.path.basename(path)}\n\n"
                f"Mở Anki → File → Import để nhập vào.")

    def _notify_sidebar(self):
        root = self.winfo_toplevel()
        if hasattr(root, "sidebar"):
            root.sidebar.refresh_stats()
            root.sidebar.refresh_decks()

    def refresh_theme(self):
        self._apply_style()
        self._populate()
