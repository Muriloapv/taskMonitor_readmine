import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import font as tkfont
import app.state as state
import app.api as api
import app.settings as settings
from app.settings import STATUS_COLORS, REFAZER_STATUSES

_tasks_window = None
_load_gen     = [0]  # cancela carregamento antigo quando a lista é atualizada


def close_tasks():
    global _tasks_window
    if _tasks_window:
        try:
            _tasks_window.destroy()
        except Exception:
            pass
        _tasks_window = None


def open_tasks():
    global _tasks_window

    if _tasks_window:
        state.tk_root.after(0, close_tasks)
        return

    def _build():
        global _tasks_window

        _tasks_window = tk.Toplevel(state.tk_root)
        win = _tasks_window
        full_name = (state.current_user.get("firstname", "") + " " + state.current_user.get("lastname", "")).strip()
        win.title(f"Listar Tarefas{' — ' + full_name if full_name else ''}")
        win.attributes("-topmost", True)
        win.configure(bg="#0f172a")
        win.resizable(True, True)
        win.protocol("WM_DELETE_WINDOW", close_tasks)
        win.bind("<Escape>", lambda e: close_tasks())

        win_w, win_h = 740, 740
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{win_w}x{win_h}+{(sw - win_w) // 2}+{(sh - win_h) // 2}")

        title_f = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        btn_f   = tkfont.Font(family="Segoe UI", size=9,  weight="bold")
        grp_f   = tkfont.Font(family="Segoe UI", size=9,  weight="bold")
        task_f  = tkfont.Font(family="Segoe UI", size=9)
        cnt_f   = tkfont.Font(family="Segoe UI", size=8,  weight="bold")

        top = tk.Frame(win, bg="#0f172a", padx=16, pady=14)
        top.pack(fill="x")
        tk.Label(top, text=f"📋  Listar Tarefas{' — ' + full_name if full_name else ''}",
                 bg="#0f172a", fg="#e2e8f0", font=title_f).pack(side="left")
        btn_refresh = tk.Button(top, text="🔄  Atualizar", font=btn_f,
                                bg="#1e40af", fg="white", relief="flat",
                                cursor="hand2", padx=12, pady=4)
        btn_refresh.pack(side="right")

        status_bar = tk.Frame(win, bg="#0f172a", padx=16, pady=4)
        status_bar.pack(fill="x")
        status_lbl = tk.Label(status_bar, text="", bg="#0f172a",
                              font=tkfont.Font(family="Segoe UI", size=9), fg="#64748b")
        status_lbl.pack(side="left")

        outer = tk.Frame(win, bg="#0f172a", padx=16, pady=8)
        outer.pack(fill="both", expand=True)
        canvas    = tk.Canvas(outer, bg="#0f172a", highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        content = tk.Frame(canvas, bg="#0f172a")
        canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        def do_load():
            _load_gen[0] += 1
            for w in content.winfo_children():
                w.destroy()
            status_lbl.config(text="Buscando tarefas...", fg="#64748b")
            win.update()

            def _fetch():
                try:
                    user_id = api.get_current_user()["id"]
                    issues  = api.get_all_issues(user_id, status_id="*")
                    state.tk_root.after(0, lambda: _render(issues))
                except Exception as e:
                    state.tk_root.after(0, lambda: status_lbl.config(text=f"Erro: {e}", fg="#ef4444"))

            threading.Thread(target=_fetch, daemon=True).start()

        def _render(issues):
            for w in content.winfo_children():
                w.destroy()

            gen = _load_gen[0]

            status_map   = settings.get_status_map()
            status_order = [k for k, v in status_map.items() if not v.startswith("__")]

            grouped  = {k: [] for k in status_order}
            unmapped = []
            for issue in issues:
                status_name = issue.get("status", {}).get("name", "")
                matched = False
                for label, mapped in status_map.items():
                    if not mapped.startswith("__") and mapped == status_name:
                        grouped[label].append(issue)
                        matched = True
                        break
                if not matched:
                    unmapped.append(issue)

            status_lbl.config(
                text=f"{len(issues)} tarefa(s)  —  clique no status para expandir  |  clique na tarefa para ver métricas",
                fg="#64748b",
            )

            # {issue_id: tk.Label} para atualizar contagem de refazer depois
            refazer_labels = {}

            def _make_group(status_label, group, color):
                if not group:
                    return

                # Frame contentor do grupo (header + tarefas)
                outer_frame = tk.Frame(content, bg="#0f172a")
                outer_frame.pack(fill="x", pady=(6, 0))

                tasks_frame = tk.Frame(outer_frame, bg="#0f172a")
                visible     = [False]  # começa recolhido

                def _toggle(tf=tasks_frame, v=visible, hdr_arrow=None):
                    if v[0]:
                        tf.pack_forget()
                        v[0] = False
                        if hdr_arrow:
                            hdr_arrow.config(text="▶")
                    else:
                        tf.pack(fill="x")
                        v[0] = True
                        if hdr_arrow:
                            hdr_arrow.config(text="▼")
                        canvas.after(50, lambda: canvas.configure(
                            scrollregion=canvas.bbox("all")))

                # Header clicável
                hdr = tk.Frame(outer_frame, bg="#1e293b", cursor="hand2")
                hdr.pack(fill="x")

                arrow = tk.Label(hdr, text="▶", bg="#1e293b", fg=color,
                                 font=grp_f, padx=6, pady=5)
                arrow.pack(side="left")
                tk.Label(hdr, text=f"{status_label}  ({len(group)})",
                         bg="#1e293b", fg=color, font=grp_f,
                         anchor="w", padx=4, pady=5).pack(side="left", fill="x", expand=True)

                toggle_fn = lambda e, tf=tasks_frame, v=visible, a=arrow: _toggle(tf, v, a)
                hdr.bind("<Button-1>",   toggle_fn)
                arrow.bind("<Button-1>", toggle_fn)
                for child in hdr.winfo_children():
                    child.bind("<Button-1>", toggle_fn)

                # Linhas de tarefas (inicialmente ocultas)
                for idx, issue in enumerate(group):
                    row_bg      = "#111827" if idx % 2 == 0 else "#0f172a"
                    issue_id    = issue.get("id")
                    issue_title = issue.get("subject", "")

                    row = tk.Frame(tasks_frame, bg=row_bg, cursor="hand2")
                    row.pack(fill="x")

                    badge = tk.Frame(row, bg=row_bg, highlightthickness=0)
                    badge.pack(side="left", padx=(8, 0), pady=6)
                    badge_lbl = tk.Label(badge, text="", bg=row_bg, fg="#ef4444", font=cnt_f)
                    badge_lbl.pack(padx=5, pady=1)
                    refazer_labels[issue_id] = (badge, badge_lbl)

                    lbl = tk.Label(
                        row, text=f"  #{issue_id}:  {issue_title}",
                        bg=row_bg, fg="#cbd5e1", font=task_f,
                        anchor="w", pady=6, padx=4,
                    )
                    lbl.pack(side="left", fill="x", expand=True)

                    def _enter(e, r=row, l=lbl, b=badge, bl=badge_lbl):
                        r.config(bg="#1e3a5f")
                        l.config(bg="#1e3a5f", fg="#ffffff")
                        if not bl.cget("text"):
                            b.config(bg="#1e3a5f")
                            bl.config(bg="#1e3a5f")

                    def _leave(e, r=row, l=lbl, b=badge, bl=badge_lbl, bg=row_bg):
                        r.config(bg=bg)
                        l.config(bg=bg, fg="#cbd5e1")
                        if not bl.cget("text"):
                            b.config(bg=bg)
                            bl.config(bg=bg)

                    def _click(e, iid=issue_id, title=issue_title):
                        from app.ui.metrics import open_metrics
                        open_metrics(iid, title)

                    for widget in (row, lbl, badge, badge_lbl):
                        widget.bind("<Enter>",    _enter)
                        widget.bind("<Leave>",    _leave)
                        widget.bind("<Button-1>", _click)

            for status_label in status_order:
                color = STATUS_COLORS.get(status_label, "#94a3b8")
                _make_group(status_label, grouped[status_label], color)

            if unmapped:
                _make_group("Outros", unmapped, "#94a3b8")

            # Carrega contagem de refazer em background
            threading.Thread(
                target=_load_refazer_counts,
                args=(issues, refazer_labels, gen),
                daemon=True,
            ).start()

        def _load_refazer_counts(issues, refazer_labels, gen):
            try:
                statuses_name  = api.get_statuses()
                statuses_by_id = {str(v): k for k, v in statuses_name.items()}
            except Exception:
                return

            def fetch_one(issue):
                iid = issue.get("id")
                try:
                    full = api.get_issue_with_journals(iid)
                    count = sum(
                        1
                        for j in full.get("journals", [])
                        for detail in j.get("details", [])
                        if detail.get("name") == "status_id"
                        and statuses_by_id.get(str(detail.get("new_value", "")), "") in REFAZER_STATUSES
                    )
                    return iid, count
                except Exception:
                    return iid, None

            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = {executor.submit(fetch_one, iss): iss for iss in issues}
                for future in as_completed(futures):
                    if _load_gen[0] != gen:
                        return
                    iid, count = future.result()
                    widgets = refazer_labels.get(iid)
                    if not widgets:
                        continue
                    badge, badge_lbl = widgets
                    row_bg = badge.master.cget("bg")

                    def _apply(b=badge, bl=badge_lbl, c=count, fallback_bg=row_bg):
                        if c:
                            b.config(bg="#2a1014", highlightthickness=1,
                                     highlightbackground="#7f1d1d", highlightcolor="#7f1d1d")
                            bl.config(text=str(c), fg="#ef4444", bg="#2a1014")
                        else:
                            b.config(bg=fallback_bg, highlightthickness=0)
                            bl.config(text="", bg=fallback_bg)

                    state.tk_root.after(0, _apply)

        btn_refresh.config(command=do_load)
        win.after(100, do_load)

    state.tk_root.after(0, _build)
