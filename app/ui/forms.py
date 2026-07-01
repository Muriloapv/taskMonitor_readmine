import threading
import tkinter as tk
from tkinter import font as tkfont
import app.state as state
import app.api as api
from app.settings import STATUS_COLORS, CONFLICT_STATUSES, APPROVED_STATUSES
from app.ui.utils import get_status_color

_verify_window = None


def close_verify():
    global _verify_window
    if _verify_window:
        try:
            _verify_window.destroy()
        except Exception:
            pass
        _verify_window = None


def open_verify():
    global _verify_window

    if _verify_window:
        state.tk_root.after(0, close_verify)
        return

    def _build():
        global _verify_window

        _verify_window = tk.Toplevel(state.tk_root)
        win = _verify_window
        full_name = (state.current_user.get("firstname", "") + " " + state.current_user.get("lastname", "")).strip()
        win.title(f"Verificar Tarefas por Unit/Form{' — ' + full_name if full_name else ''}")
        win.attributes("-topmost", True)
        win.configure(bg="#0f172a")
        win.resizable(True, True)
        win.protocol("WM_DELETE_WINDOW", close_verify)

        win_w, win_h = 740, 740
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{win_w}x{win_h}+{(sw - win_w) // 2}+{(sh - win_h) // 2}")

        title_f  = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        header_f = tkfont.Font(family="Segoe UI", size=9,  weight="bold")
        small_f  = tkfont.Font(family="Segoe UI", size=9)
        btn_f    = tkfont.Font(family="Segoe UI", size=9,  weight="bold")

        top = tk.Frame(win, bg="#0f172a", padx=16, pady=14)
        top.pack(fill="x")
        tk.Label(top, text=f"🔍  Units / Forms com tarefas{' — ' + full_name if full_name else ''}",
                 bg="#0f172a", fg="#e2e8f0", font=title_f).pack(side="left")
        btn_refresh = tk.Button(top, text="🔄  Atualizar", font=btn_f,
                                bg="#1e40af", fg="white", relief="flat",
                                cursor="hand2", padx=12, pady=4)
        btn_refresh.pack(side="right")

        status_bar = tk.Frame(win, bg="#0f172a", padx=16, pady=4)
        status_bar.pack(fill="x")
        status_lbl = tk.Label(status_bar, text="", bg="#0f172a",
                              font=tkfont.Font(family="Segoe UI", size=10, weight="bold"))
        status_lbl.pack(side="left")
        loading_lbl = tk.Label(status_bar, text="", bg="#0f172a",
                               font=tkfont.Font(family="Segoe UI", size=9), fg="#64748b")
        loading_lbl.pack(side="right")

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
            for w in content.winfo_children():
                w.destroy()
            status_lbl.config(text="🔄  Buscando tarefas...", fg="#94a3b8")
            loading_lbl.config(text="")
            win.update()

            def _fetch():
                try:
                    user_id    = api.get_current_user()["id"]
                    all_issues = api.get_all_issues(user_id)
                    state.tk_root.after(0, lambda: _render(all_issues))
                except Exception as e:
                    state.tk_root.after(0, lambda: status_lbl.config(text=f"❌  Erro: {e}", fg="#ef4444"))

            threading.Thread(target=_fetch, daemon=True).start()

        def _render(all_issues):
            for w in content.winfo_children():
                w.destroy()

            form_map = {}
            for issue in all_issues:
                cf = next((f for f in issue.get("custom_fields", []) if f["id"] == 8), None)
                if not cf or not cf.get("value", "").strip():
                    continue
                forms = [f.strip() for f in cf["value"].split("\n") if f.strip()]
                for form in forms:
                    form_map.setdefault(form, []).append(issue)

            if not form_map:
                status_lbl.config(text="Nenhuma tarefa com Unit/Form encontrada.", fg="#ef4444")
                return

            def sort_key(item):
                _, iss = item
                statuses  = [i.get("status", {}).get("name", "") for i in iss]
                has_conf  = any(s in CONFLICT_STATUSES for s in statuses)
                return (0 if has_conf else 1, item[0])

            sorted_forms = sorted(form_map.items(), key=sort_key)
            total_lib    = sum(1 for _, iss in sorted_forms
                               if all(i.get("status", {}).get("name", "") in APPROVED_STATUSES for i in iss))
            total_conf   = len(sorted_forms) - total_lib

            status_lbl.config(
                text=f"📦  {len(sorted_forms)} forms  |  ✅ {total_lib} liberados  |  ⚠️ {total_conf} com conflito",
                fg="#e2e8f0",
            )
            loading_lbl.config(text=f"{len(all_issues)} tarefas carregadas")

            for form_name, form_issues in sorted_forms:
                statuses  = [i.get("status", {}).get("name", "") for i in form_issues]
                all_appr  = all(s in APPROVED_STATUSES for s in statuses)
                has_conf  = any(s in CONFLICT_STATUSES for s in statuses)

                if all_appr:
                    badge_text, badge_color, header_bg = "✅  Liberada",             "#22c55e", "#052e16"
                elif has_conf:
                    badge_text, badge_color, header_bg = "⚠️  Conflito de tarefas", "#ef4444", "#2d0a0a"
                else:
                    badge_text, badge_color, header_bg = "🔵  Em progresso",        "#3b82f6", "#0c1a2e"

                card = tk.Frame(content, bg="#111827")
                card.pack(fill="x", pady=(0, 6))

                ch = tk.Frame(card, bg=header_bg, padx=10, pady=6)
                ch.pack(fill="x")
                tk.Label(ch, text=form_name, bg=header_bg, fg="#e2e8f0",
                         font=header_f, anchor="w").pack(side="left", fill="x", expand=True)
                tk.Label(ch, text=badge_text, bg=header_bg, fg=badge_color,
                         font=header_f).pack(side="right")

                for idx, issue in enumerate(form_issues):
                    row_bg      = "#111827" if idx % 2 == 0 else "#0f172a"
                    status_name = issue.get("status", {}).get("name", "—")
                    s_color     = get_status_color(status_name)
                    updated     = issue.get("updated_on", "")[:16].replace("T", " ")

                    row = tk.Frame(card, bg=row_bg, padx=10, pady=3)
                    row.pack(fill="x")
                    tk.Label(row, text=f"#{issue.get('id')}",
                             bg=row_bg, fg="#64748b", font=small_f, width=7, anchor="w").pack(side="left")
                    tk.Label(row, text=issue.get("subject", "")[:70],
                             bg=row_bg, fg="#cbd5e1", font=small_f, anchor="w").pack(side="left", fill="x", expand=True)
                    tk.Label(row, text=updated,
                             bg=row_bg, fg="#475569", font=small_f, width=17, anchor="e").pack(side="right")
                    tk.Label(row, text=status_name,
                             bg=row_bg, fg=s_color, font=small_f, width=24, anchor="e").pack(side="right")

        btn_refresh.config(command=do_load)
        win.after(100, do_load)

    state.tk_root.after(0, _build)
