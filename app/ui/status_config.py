import threading
import tkinter as tk
from tkinter import font as tkfont
import app.state as state
import app.api as api
import app.settings as settings

_window = None


def close_status_config():
    global _window
    if _window:
        try:
            _window.destroy()
        except Exception:
            pass
        _window = None


def open_status_config():
    global _window

    if _window:
        state.tk_root.after(0, close_status_config)
        return

    def _build():
        global _window

        win = tk.Toplevel(state.tk_root)
        _window = win
        win.title("Configurar Status")
        win.attributes("-topmost", True)
        win.configure(bg="#0f172a")
        win.resizable(True, True)
        win.protocol("WM_DELETE_WINDOW", close_status_config)
        win.bind("<Escape>", lambda e: close_status_config())

        win_w, win_h = 740, 740
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{win_w}x{win_h}+{(sw - win_w) // 2}+{(sh - win_h) // 2}")

        title_f = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        sub_f   = tkfont.Font(family="Segoe UI", size=9)
        lbl_f   = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        entry_f = tkfont.Font(family="Segoe UI", size=9)
        btn_f   = tkfont.Font(family="Segoe UI", size=9, weight="bold")

        hdr = tk.Frame(win, bg="#0f172a", padx=16, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙️  Configurar Status", bg="#0f172a",
                 fg="#e2e8f0", font=title_f).pack(anchor="w")
        tk.Label(hdr, text="Ajuste o nome exato de cada status no seu Redmine "
                            "sem precisar editar codigo ou recompilar o app.",
                 bg="#0f172a", fg="#64748b", font=sub_f,
                 wraplength=520, justify="left").pack(anchor="w", pady=(2, 0))
        tk.Frame(win, bg="#1e3a5f", height=1).pack(fill="x", padx=16)

        outer = tk.Frame(win, bg="#0f172a", padx=16, pady=10)
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

        current_map = settings.get_status_map()
        labels = [k for k, v in current_map.items() if not v.startswith("__")]

        entries = {}
        for idx, label in enumerate(labels):
            row_bg = "#111827" if idx % 2 == 0 else "#0f172a"
            row = tk.Frame(content, bg=row_bg, pady=6, padx=6)
            row.pack(fill="x")
            tk.Label(row, text=label, bg=row_bg, fg="#cbd5e1", font=lbl_f,
                     width=26, anchor="w").pack(side="left")
            var = tk.StringVar(value=current_map[label])
            ent = tk.Entry(row, textvariable=var, font=entry_f, bg="#1e293b",
                            fg="#e2e8f0", insertbackground="#e2e8f0", relief="flat")
            ent.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=3)
            entries[label] = (var, ent)

        status_lbl = tk.Label(win, text="", bg="#0f172a", fg="#64748b",
                               font=sub_f, anchor="w", justify="left", wraplength=520)
        status_lbl.pack(fill="x", padx=16)

        def _validate():
            status_lbl.config(text="Verificando nomes no Redmine...", fg="#64748b")

            def _fetch():
                try:
                    real_names = set(api.get_statuses().keys())
                    state.tk_root.after(0, lambda: _apply_validation(real_names))
                except Exception as e:
                    state.tk_root.after(0, lambda: status_lbl.config(
                        text=f"Erro ao validar: {e}", fg="#ef4444"))

            def _apply_validation(real_names):
                invalid = 0
                for var, ent in entries.values():
                    if var.get().strip() in real_names:
                        ent.config(bg="#1e293b")
                    else:
                        ent.config(bg="#3b0a0a")
                        invalid += 1
                if invalid:
                    status_lbl.config(
                        text=f"{invalid} status nao encontrados no Redmine (campo em vermelho).",
                        fg="#ef4444")
                else:
                    status_lbl.config(text="Todos os nomes batem com o Redmine.", fg="#22c55e")

            threading.Thread(target=_fetch, daemon=True).start()

        def _save():
            mapping = {label: var.get().strip() for label, (var, ent) in entries.items()}
            if any(not v for v in mapping.values()):
                status_lbl.config(text="Nenhum campo pode ficar vazio.", fg="#ef4444")
                return
            settings.save_status_map(mapping)
            status_lbl.config(
                text="Salvo. Sera aplicado na proxima atualizacao automatica (ou clique em 'Atualizar agora' na bandeja).",
                fg="#22c55e")

        def _restore_defaults():
            settings.reset_status_map()
            close_status_config()
            open_status_config()

        btns = tk.Frame(win, bg="#0f172a", padx=16, pady=12)
        btns.pack(fill="x")
        tk.Button(btns, text="Verificar nomes", font=btn_f, bg="#1e293b", fg="#cbd5e1",
                  relief="flat", cursor="hand2", padx=12, pady=5,
                  command=_validate).pack(side="left")
        tk.Button(btns, text="Restaurar padrao", font=btn_f, bg="#1e293b", fg="#cbd5e1",
                  relief="flat", cursor="hand2", padx=12, pady=5,
                  command=_restore_defaults).pack(side="left", padx=(8, 0))
        tk.Button(btns, text="Salvar", font=btn_f, bg="#1e40af", fg="white",
                  relief="flat", cursor="hand2", padx=16, pady=5,
                  command=_save).pack(side="right")

        esc_hint = tk.Label(win, text="ESC para fechar", bg="#0f172a", fg="#334155",
                            font=tkfont.Font(family="Segoe UI", size=8))
        esc_hint.pack(side="bottom", pady=4)

    state.tk_root.after(0, _build)
