# taskMonitor_readmine

Aplicativo Windows de bandeja do sistema que monitora tarefas do Redmine atribuídas ao usuário logado. Exibe contagens por status, notifica mudanças e abre janelas com métricas detalhadas por tarefa.

## Stack

- **Python 3.12+** — sem framework web, sem ORM
- **tkinter** — toda a UI (janelas, popups, tabelas)
- **pystray** — ícone na bandeja do sistema
- **Pillow** — renderização do ícone (inclui badge de alerta ⚠️)
- **requests** — chamadas à API REST do Redmine

## Configuração e execução

```bash
# 1. Copiar e preencher credenciais
cp config.exemplo.py config.py   # editar REDMINE_URL e API_KEY

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Rodar em dev
python redmine_tray.py

# 4. Empacotar para .exe (single-file, sem console)
pyinstaller redmine_tray.spec
```

`config.py` é ignorado pelo `.gitignore` — nunca commitá-lo. O `.spec` inclui `icon.png` e `config.py` no bundle.

## Arquitetura

```
redmine_tray.py        ← entry point: inicializa tk, pystray, monitor thread, menu da bandeja
app/
├── api.py             ← todas as chamadas ao Redmine (requests); get_issue_with_journals inclui journals
├── monitor.py         ← loop de polling a cada 30s (CHECK_INTERVAL); detecta transições de status
├── settings.py        ← STATUS_MAP, STATUS_COLORS, METRICS_STATUSES, REFAZER_STATUSES + persistência
├── state.py           ← estado global compartilhado (task_counts, current_user, tk_root, etc.)
├── tray.py            ← make_icon() — ícone normal ou com badge ⚠️
└── ui/
    ├── popup.py       ← popup da bandeja: contagem por status + botões
    ├── tasks.py       ← "Listar Tarefas": grupos por status, colapsáveis, badge de refazer por tarefa
    ├── metrics.py     ← "Métricas": tabela de tempo por status reconstruída do histórico de journals
    ├── forms.py       ← "Verificar Forms": agrupa tarefas pelo campo customizado #8 (Unit/Form)
    ├── status_config.py ← "Configurar Status": editor runtime do status_map, persiste em status_map.json
    └── utils.py       ← quit_app(), get_status_color()
```

## Estado global (`app/state.py`)

| Variável | Tipo | Conteúdo |
|---|---|---|
| `tk_root` | `tk.Tk` | Janela raiz oculta — pump de eventos do tkinter |
| `tray_icon_ref` | `pystray.Icon` | Ícone da bandeja |
| `task_counts` | `dict[str, int]` | `{label: contagem}` — atualizado a cada ciclo |
| `changed_labels` | `set[str]` | Labels que mudaram desde o último popup aberto |
| `current_user` | `dict` | Dados do usuário Redmine (firstname, lastname, id) |
| `task_status_by_id` | `dict[int, dict]` | Snapshot anterior para detectar transições |

## Regra crítica de thread-safety

**Nunca chamar tkinter diretamente de threads de background.** Sempre usar:
```python
state.tk_root.after(0, lambda: fazer_algo_na_ui())
```
Todo fluxo: thread busca dados → `after(0, render)` → `_render()` monta widgets.

## Configuração de status (`app/settings.py`)

- `STATUS_MAP` — `{label_exibida: nome_exato_no_redmine}` — pode ser sobrescrito em runtime via `status_map.json` (salvo pela janela "Configurar Status")
- `METRICS_STATUSES` — lista ordenada dos status exibidos na tabela de métricas
- `REFAZER_STATUSES` — conjunto de status que incrementam o contador "vezes no Refazer"
- `STATUS_COLORS` — `{nome: cor_hex}` — usado em toda a UI para colorir dots e labels

## Janela de Métricas (`app/ui/metrics.py`)

Algoritmo em `_compute_metrics()`:
1. Lê `issue["journals"]` ordenados por `created_on`
2. Extrai mudanças onde `detail["name"] == "status_id"`
3. Reconstrói segmentos `{status, start, end}` a partir da criação até agora
4. Acumula segundos e contagem de entradas por status

`_format_duration(seconds)` → `"< 1 min"`, `"45 min"`, `"3h 20min"`, `"5d 2h"`, `"1mes 15d"`

## Padrão de janela singleton

Todas as janelas seguem o mesmo padrão:
```python
_window = None

def open_x():
    global _window
    if _window:              # toggle: fecha se já aberta
        close_x(); return
    def _build():
        global _window
        _window = tk.Toplevel(state.tk_root)
        # ... monta UI, dispara thread para buscar dados
    state.tk_root.after(0, _build)
```

## API Redmine (`app/api.py`)

Autenticação via header `X-Redmine-API-Key`. Endpoints usados:
- `GET /users/current.json` — usuário logado
- `GET /issue_statuses.json` — todos os status disponíveis
- `GET /issues.json?assigned_to_id=&status_id=*` — tarefas (paginação automática em `get_all_issues`)
- `GET /issues/{id}.json?include=journals` — histórico completo de uma tarefa

## Instância única

`redmine_tray.py` usa mutex Windows (`CreateMutexW`) para impedir múltiplas instâncias. Exibe `MessageBoxW` se já estiver rodando.
