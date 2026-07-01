import threading
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime, timezone
import app.state as state
import app.api as api
from app.settings import STATUS_COLORS, METRICS_STATUSES, REFAZER_STATUSES, APPROVED_STATUSES

_current_window = None


def _parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _format_duration(seconds):
    if seconds <= 0:
        return "—"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min" if minutes > 0 else "< 1 min"
    hours = int(seconds // 3600)
    days  = hours // 24
    if days == 0:
        return f"{hours}h {int((seconds % 3600) // 60)}min"
    months = days // 30
    if months == 0:
        return f"{days}d {hours % 24}h"
    rem_days = days % 30
    return f"{months}mes {rem_days}d" if rem_days else f"{months} mes"


def _compute_metrics(issue, statuses_by_id):
    created_on     = _parse_dt(issue["created_on"])
    current_status = issue["status"]["name"]
    now            = datetime.now(timezone.utc)

    changes = []
    for j in sorted(issue.get("journals", []), key=lambda x: x["created_on"]):
        for detail in j.get("details", []):
            if detail.get("name") == "status_id":
                changes.append({
                    "dt":  _parse_dt(j["created_on"]),
                    "old": statuses_by_id.get(str(detail.get("old_value", "")), "?"),
                    "new": statuses_by_id.get(str(detail.get("new_value", "")), "?"),
                })

    if not changes:
        segments = [{"status": current_status, "start": created_on, "end": now}]
    else:
        segments = [{"status": changes[0]["old"], "start": created_on, "end": changes[0]["dt"]}]
        for i, ch in enumerate(changes):
            end = changes[i + 1]["dt"] if i + 1 < len(changes) else now
            segments.append({"status": ch["new"], "start": ch["dt"], "end": end})

    time_per    = {}
    entries_per = {}
    for seg in segments:
        name     = seg["status"]
        duration = (seg["end"] - seg["start"]).total_seconds()
        time_per[name]    = time_per.get(name, 0) + max(duration, 0)
        entries_per[name] = entries_per.get(name, 0) + 1

    refazer_count = sum(1 for ch in changes if ch["new"] in REFAZER_STATUSES)

    last_approval_dt = None
    for ch in changes:
        if ch["new"] in APPROVED_STATUSES:
            last_approval_dt = ch["dt"]

    # Soma de todos os segmentos = tempo total decorrido (criação → agora)
    # Coerente com a soma visual das linhas da tabela
    total_ate_aprovacao = (
        (last_approval_dt - created_on).total_seconds()
        if last_approval_dt is not None else None
    )

    _STATUSES_ATE_TESTAR = {"Analisar", "Fazer", "Fazendo", "Refazer", "Refazendo"}
    total_ate_testar = sum(time_per.get(s, 0) for s in _STATUSES_ATE_TESTAR)

    _STATUSES_PARADO = {"Fazer", "Testar", "Testando", "Refazer"}
    total_parado = sum(time_per.get(s, 0) for s in _STATUSES_PARADO)

    _STATUSES_TOTAL = {
        "Analisar", "Fazer", "Fazendo", "Testar", "Testando",
        "Refazer", "Refazendo", "Aprovado (subir Units)",
    }
    total_geral = sum(time_per.get(s, 0) for s in _STATUSES_TOTAL)

    return time_per, entries_per, refazer_count, current_status, total_ate_aprovacao, total_ate_testar, total_parado, total_geral


def _close_current():
    global _current_window
    if _current_window:
        try:
            _current_window.destroy()
        except Exception:
            pass
        _current_window = None


def open_metrics(issue_id, issue_title=""):
    global _current_window
    _close_current()

    def _build():
        global _current_window

        win = tk.Toplevel(state.tk_root)
        _current_window = win
        win.title(f"#{issue_id} — Métricas")
        win.attributes("-topmost", True)
        win.configure(bg="#0f172a")
        win.resizable(True, True)
        win.protocol("WM_DELETE_WINDOW", _close_current)
        win.bind("<Escape>", lambda e: _close_current())

        win_w, win_h = 740, 740
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{win_w}x{win_h}+{(sw - win_w) // 2}+{(sh - win_h) // 2}")

        id_f     = tkfont.Font(family="Segoe UI", size=9)
        title_f  = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        header_f = tkfont.Font(family="Segoe UI", size=9,  weight="bold")
        value_f  = tkfont.Font(family="Segoe UI", size=9)
        badge_f  = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        badge_lf = tkfont.Font(family="Segoe UI", size=8)
        cur_f    = tkfont.Font(family="Segoe UI", size=15, weight="bold")
        load_f   = tkfont.Font(family="Segoe UI", size=10)

        hdr = tk.Frame(win, bg="#0f172a", padx=16, pady=14)
        hdr.pack(fill="x")

        hdr_left = tk.Frame(hdr, bg="#0f172a")
        hdr_left.pack(side="left", fill="x", expand=True)
        tk.Label(hdr_left, text=f"#{issue_id}", bg="#0f172a", fg="#475569", font=id_f).pack(anchor="w")
        display_title = issue_title if issue_title else f"Tarefa #{issue_id}"
        tk.Label(hdr_left, text=display_title, bg="#0f172a", fg="#e2e8f0",
                 font=title_f, wraplength=340, justify="left").pack(anchor="w")

        btn_hist_f = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        btn_hist = tk.Button(hdr, text="📋 Histórico\n    Refazer",
                             bg="#1e293b", fg="#94a3b8", font=btn_hist_f,
                             relief="flat", cursor="hand2", padx=10, pady=6)
        btn_hist.pack(side="right", anchor="ne")

        tk.Frame(win, bg="#1e3a5f", height=1).pack(fill="x", padx=16)

        esc_hint = tk.Label(win, text="ESC para fechar", bg="#0f172a", fg="#334155",
                            font=tkfont.Font(family="Segoe UI", size=8))
        esc_hint.pack(side="bottom", pady=4)

        footer = tk.Frame(win, bg="#0f172a", padx=16, pady=0)
        footer.pack(side="bottom", fill="x")

        content = tk.Frame(win, bg="#0f172a", padx=16, pady=12)
        content.pack(fill="both", expand=True)

        loading = tk.Label(content, text="Carregando métricas...", bg="#0f172a",
                           fg="#64748b", font=load_f)
        loading.pack(pady=30)

        def _open_history():
            hist = tk.Toplevel(win)
            hist.title(f"#{issue_id} — Histórico Refazer")
            hist.attributes("-topmost", True)
            hist.configure(bg="#0f172a")
            hist.resizable(True, True)
            hw, hh = 740, 740
            hist.geometry(f"{hw}x{hh}+{(sw - hw) // 2}+{(sh - hh) // 2}")

            htitle_f = tkfont.Font(family="Segoe UI", size=11, weight="bold")
            hsub_f   = tkfont.Font(family="Segoe UI", size=9)
            hbold_f  = tkfont.Font(family="Segoe UI", size=9,  weight="bold")

            th = tk.Frame(hist, bg="#0f172a", padx=16, pady=12)
            th.pack(fill="x")
            tk.Label(th, text=f"Histórico Refazer — #{issue_id}",
                     bg="#0f172a", fg="#e2e8f0", font=htitle_f).pack(anchor="w")
            tk.Frame(hist, bg="#1e3a5f", height=1).pack(fill="x", padx=16)

            outer_h   = tk.Frame(hist, bg="#0f172a", padx=16, pady=8)
            outer_h.pack(fill="both", expand=True)
            canvas_h  = tk.Canvas(outer_h, bg="#0f172a", highlightthickness=0)
            scrollbar_h = tk.Scrollbar(outer_h, orient="vertical", command=canvas_h.yview)
            canvas_h.configure(yscrollcommand=scrollbar_h.set)
            scrollbar_h.pack(side="right", fill="y")
            canvas_h.pack(side="left", fill="both", expand=True)
            items_f = tk.Frame(canvas_h, bg="#0f172a")
            canvas_h.create_window((0, 0), window=items_f, anchor="nw")
            items_f.bind("<Configure>", lambda e: canvas_h.configure(scrollregion=canvas_h.bbox("all")))
            canvas_h.bind_all("<MouseWheel>", lambda e: canvas_h.yview_scroll(-1 * (e.delta // 120), "units"))

            loading_h = tk.Label(items_f, text="Carregando...", bg="#0f172a",
                                 fg="#64748b", font=hsub_f)
            loading_h.pack(pady=20)

            _cache = [None]

            def _fetch_history():
                try:
                    issue_data     = api.get_issue_with_journals(issue_id)
                    statuses_name  = api.get_statuses()
                    statuses_by_id = {str(v): k for k, v in statuses_name.items()}
                    journals_sorted = sorted(issue_data.get("journals", []), key=lambda x: x["created_on"])

                    def _status_new(j):
                        for d in j.get("details", []):
                            if d.get("name") == "status_id":
                                return statuses_by_id.get(str(d.get("new_value", "")), "")
                        return ""

                    def _cf_value(j):
                        # Retorna o valor de qualquer custom field não-vazio no journal
                        for d in j.get("details", []):
                            if d.get("property") == "cf":
                                v = str(d.get("new_value") or "").strip()
                                if v:
                                    return v
                        return ""

                    # Indices onde status → Refazer (padrão clássico)
                    refazer_indices = [
                        i for i, j in enumerate(journals_sorted)
                        if _status_new(j) in REFAZER_STATUSES
                    ]
                    # Indices onde status → Testando + custom field atualizado
                    # (padrão alternativo: QA documenta o motivo ao retomar os testes)
                    testando_cf_indices = [
                        i for i, j in enumerate(journals_sorted)
                        if _status_new(j) == "Testando" and _cf_value(j)
                    ]

                    # Testando+cf que já terão um Refazer próximo (≤5 journals) não são
                    # adicionados como entrada própria — o Refazer busca o motivo backward
                    standalone_cf = []
                    for ci in testando_cf_indices:
                        next_ri = next((ri for ri in refazer_indices if ri > ci), None)
                        if next_ri is None or (next_ri - ci) > 5:
                            standalone_cf.append(ci)

                    all_indices = sorted(set(refazer_indices) | set(standalone_cf))

                    entries = []
                    for i in all_indices:
                        j = journals_sorted[i]
                        notes = j.get("notes", "").strip()

                        # Tenta custom field do próprio journal
                        if not notes:
                            notes = _cf_value(j)

                        # Busca até 5 journals anteriores por cf ou nota
                        if not notes:
                            for pi in range(i - 1, max(i - 6, -1), -1):
                                pj = journals_sorted[pi]
                                notes = _cf_value(pj) or pj.get("notes", "").strip()
                                if notes:
                                    break

                        # Se ainda vazio, tenta o próximo journal (sem mudança de status)
                        if not notes and i + 1 < len(journals_sorted):
                            nxt = journals_sorted[i + 1]
                            if not any(d.get("name") == "status_id" for d in nxt.get("details", [])):
                                notes = nxt.get("notes", "").strip()

                        entries.append({
                            "date":  j["created_on"],
                            "user":  j.get("user", {}).get("name", "Desconhecido"),
                            "notes": notes,
                        })

                    _cache[0] = entries
                    state.tk_root.after(0, lambda: _render_history(entries))
                except Exception as e:
                    state.tk_root.after(0, lambda: loading_h.config(text=f"Erro: {e}", fg="#ef4444"))

            def _render_history(entries):
                loading_h.destroy()
                if not entries:
                    tk.Label(items_f, text="Nenhum Refazer encontrado no histórico.",
                             bg="#0f172a", fg="#475569", font=hsub_f).pack(pady=20)
                    return
                for idx, entry in enumerate(entries):
                    dt_str = _parse_dt(entry["date"]).strftime("%d/%m/%Y %H:%M")
                    row_bg = "#111827" if idx % 2 == 0 else "#0f172a"
                    card = tk.Frame(items_f, bg=row_bg, pady=8, padx=10)
                    card.pack(fill="x", pady=(0, 2))

                    top_row = tk.Frame(card, bg=row_bg)
                    top_row.pack(fill="x")
                    tk.Label(top_row, text=f"Refazer #{idx + 1}",
                             bg=row_bg, fg="#ef4444", font=hbold_f).pack(side="left")
                    tk.Label(top_row, text=dt_str,
                             bg=row_bg, fg="#475569", font=hsub_f).pack(side="right")

                    tk.Label(card, text=f"👤  {entry['user']}",
                             bg=row_bg, fg="#94a3b8", font=hsub_f, anchor="w").pack(fill="x", pady=(3, 0))

                    note_text  = entry["notes"] if entry["notes"] else "— sem comentário —"
                    note_color = "#cbd5e1" if entry["notes"] else "#475569"
                    tk.Label(card, text=note_text, bg=row_bg, fg=note_color,
                             font=hsub_f, anchor="w", wraplength=440,
                             justify="left").pack(fill="x", pady=(4, 0))

            def _on_close_hist():
                _cache[0] = None
                try:
                    hist.destroy()
                except Exception:
                    pass

            hist.protocol("WM_DELETE_WINDOW", _on_close_hist)
            hist.bind("<Escape>", lambda e: _on_close_hist())
            threading.Thread(target=_fetch_history, daemon=True).start()

        btn_hist.config(command=_open_history)

        def _fetch():
            try:
                issue          = api.get_issue_with_journals(issue_id)
                statuses_name  = api.get_statuses()
                statuses_by_id = {str(v): k for k, v in statuses_name.items()}
                result         = _compute_metrics(issue, statuses_by_id)
                state.tk_root.after(0, lambda: _render(*result))
            except Exception as e:
                state.tk_root.after(0, lambda: loading.config(text=f"Erro: {e}", fg="#ef4444"))

        def _render(time_per, entries_per, refazer_count, current_status, total_ate_aprovacao, total_ate_testar, total_parado, total_geral):
            loading.destroy()
            for w in content.winfo_children():
                w.destroy()

            badges = tk.Frame(content, bg="#0f172a")
            badges.pack(fill="x", pady=(0, 14))

            cur_color = STATUS_COLORS.get(current_status, "#94a3b8")
            cur_card  = tk.Frame(badges, bg="#0c1a2e", padx=18, pady=10)
            cur_card.pack(side="left", padx=(0, 10), fill="both", expand=True)
            tk.Label(cur_card, text="Status atual", bg="#0c1a2e",
                     fg="#475569", font=badge_lf).pack(anchor="center")
            tk.Label(cur_card, text=current_status, bg="#0c1a2e",
                     fg=cur_color, font=cur_f, wraplength=220, justify="center").pack(anchor="center")

            ref_color = "#ef4444" if refazer_count > 0 else "#22c55e"
            ref_bg    = "#2d0a0a"  if refazer_count > 0 else "#052e16"
            ref_card  = tk.Frame(badges, bg=ref_bg, padx=18, pady=10)
            ref_card.pack(side="left", fill="both", expand=True)
            tk.Label(ref_card, text=str(refazer_count), bg=ref_bg,
                     fg=ref_color, font=badge_f).pack()
            tk.Label(ref_card, text="vezes no Refazer", bg=ref_bg,
                     fg=ref_color, font=badge_lf).pack()

            tk.Frame(content, bg="#1e293b", height=1).pack(fill="x", pady=(0, 8))

            th = tk.Frame(content, bg="#0f172a")
            th.pack(fill="x", pady=(0, 4))
            tk.Label(th, text="Status", bg="#0f172a", fg="#475569",
                     font=header_f, anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(th, text="Tempo total", bg="#0f172a", fg="#475569",
                     font=header_f, width=16, anchor="center").pack(side="left")
            tk.Label(th, text="Entradas", bg="#0f172a", fg="#475569",
                     font=header_f, width=9, anchor="e").pack(side="right")

            tk.Frame(content, bg="#1e293b", height=1).pack(fill="x", pady=(0, 4))

            has_any = False
            for idx, status_name in enumerate(METRICS_STATUSES):
                seconds = time_per.get(status_name, 0)
                entries = entries_per.get(status_name, 0)
                if seconds <= 0 and entries == 0:
                    continue
                has_any = True

                row_bg = "#111827" if idx % 2 == 0 else "#0f172a"
                color  = STATUS_COLORS.get(status_name, "#94a3b8")

                row = tk.Frame(content, bg=row_bg, pady=6, padx=4)
                row.pack(fill="x")

                dot = tk.Canvas(row, width=10, height=10, bg=row_bg, highlightthickness=0)
                dot.create_oval(1, 1, 9, 9, fill=color, outline="")
                dot.pack(side="left", padx=(0, 8))

                tk.Label(row, text=status_name, bg=row_bg, fg="#cbd5e1",
                         font=value_f, anchor="w").pack(side="left", fill="x", expand=True)
                tk.Label(row, text=_format_duration(seconds), bg=row_bg, fg="#94a3b8",
                         font=value_f, width=16, anchor="center").pack(side="left")
                tk.Label(row, text=str(entries), bg=row_bg, fg="#64748b",
                         font=value_f, width=8, anchor="e").pack(side="right")

            if not has_any:
                tk.Label(content, text="Nenhum histórico de status encontrado.",
                         bg="#0f172a", fg="#475569", font=value_f).pack(pady=12)


            for w in footer.winfo_children():
                w.destroy()

            tk.Frame(footer, bg="#1e3a5f", height=1).pack(fill="x", pady=(4, 4))

            total_lbl_f = tkfont.Font(family="Segoe UI", size=9, weight="bold")

            if total_ate_aprovacao is not None:
                dur_text  = _format_duration(total_ate_aprovacao)
                lbl_color = "#22c55e"
                dur_color = "#22c55e"
            else:
                dur_text  = "não aprovada"
                lbl_color = "#475569"
                dur_color = "#475569"

            testar_row = tk.Frame(footer, bg="#111827", pady=7, padx=4)
            testar_row.pack(fill="x")
            tk.Label(testar_row, text="Analisar → Testar  (Total)",
                     bg="#111827", fg="#94a3b8", font=total_lbl_f,
                     anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(testar_row, text=_format_duration(total_ate_testar),
                     bg="#111827", fg="#94a3b8", font=total_lbl_f,
                     width=16, anchor="center").pack(side="left")

            aprov_row = tk.Frame(footer, bg="#0c1a2e", pady=7, padx=4)
            aprov_row.pack(fill="x")
            tk.Label(aprov_row, text="Analisar → Aprovado  (Total)",
                     bg="#0c1a2e", fg=lbl_color, font=total_lbl_f,
                     anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(aprov_row, text=dur_text,
                     bg="#0c1a2e", fg=dur_color, font=total_lbl_f,
                     width=16, anchor="center").pack(side="left")

            geral_row = tk.Frame(footer, bg="#0f2040", pady=7, padx=4)
            geral_row.pack(fill="x")
            tk.Label(geral_row, text="Tempo total",
                     bg="#0f2040", fg="#e2e8f0", font=total_lbl_f,
                     anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(geral_row, text=_format_duration(total_geral),
                     bg="#0f2040", fg="#e2e8f0", font=total_lbl_f,
                     width=16, anchor="center").pack(side="left")

        threading.Thread(target=_fetch, daemon=True).start()

    state.tk_root.after(0, _build)


def count_refazer_from_journals(issue, statuses_by_id):
    """Utilitário reutilizado por tasks.py para contar refazeres sem abrir janela."""
    return sum(
        1
        for j in issue.get("journals", [])
        for detail in j.get("details", [])
        if detail.get("name") == "status_id"
        and statuses_by_id.get(str(detail.get("new_value", "")), "") in REFAZER_STATUSES
    )
