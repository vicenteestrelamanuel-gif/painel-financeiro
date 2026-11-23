import json, os, re, uuid, datetime as dt
import numpy as np, pandas as pd, plotly.express as px, plotly.graph_objects as go, requests, streamlit as st, yfinance as yf
from plotly.subplots import make_subplots
from zoneinfo import ZoneInfo
from itertools import groupby
import concurrent.futures as cf

st.set_page_config(page_title="Painel Financeiro", page_icon="📈", layout="wide")
PIE_COL = {"Quantum": "#7C5CFF", "Alone Stocks": "#0FB5A6", "Daily Dividend": "#F59E0B", "ETFs": "#3B82F6"}
CAT_COL = {"Restaurantes": "#F97316", "Supermercado": "#84CC16", "Subscrições": "#A855F7", "Transportes": "#06B6D4", "Lazer": "#EC4899", "Saúde": "#EF4444", "Material Escolar": "#3B82F6", "Investido": "#F59E0B", "Outros": "#94A3B8"}
EXTRA = ["#EC4899", "#84CC16", "#06B6D4", "#F97316", "#A855F7", "#64748B", "#EF4444"]
UP, DN = "#12A150", "#E5484D"
PALX = ["#7C5CFF", "#0FB5A6", "#F59E0B", "#3B82F6", "#EC4899", "#84CC16", "#06B6D4", "#F97316", "#A855F7", "#64748B"]
pcol = lambda p: PIE_COL.get(p) or EXTRA[sum(map(ord, str(p))) % len(EXTRA)]
def num(x, d=2, sign=False):
    return (f"{x:+,.{d}f}" if sign else f"{x:,.{d}f}").replace(",", " ").replace(".", ",")
def chip(v, txt, kind=None): return f'<span class="chip {kind or ("up" if v >= 0 else "dn")}">{txt}</span>'
def card(label, value, sub="", color="#7C5CFF", bar=None):
    b = f'<div class="pbar"><i style="width:{max(2, min(100, bar)):.0f}%"></i></div>' if bar is not None else ""
    return f'<div class="kc" style="--c:{color}"><div class="l">{label}</div><div class="v">{value}</div>{sub}{b}</div>'
def pl_style(v): return "" if pd.isna(v) or v == 0 else f"color:{UP if v > 0 else DN};font-weight:700"
def styler_map(sty, fn, subset): return (sty.map if hasattr(sty, "map") else sty.applymap)(fn, subset=subset)
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;800&display=swap');
html,body,.stApp,.stApp p,.stApp label,.stApp button,.stApp input,.stApp textarea,.stApp li,.stApp h1,.stApp h2,.stApp h3,.stApp h4,[data-testid="stMarkdownContainer"]{font-family:'Manrope',system-ui,sans-serif}
[data-testid="stIconMaterial"],.material-icons,.material-symbols-rounded{font-family:'Material Symbols Rounded','Material Icons'!important}
.block-container{padding-top:1.1rem;max-width:1250px}
.brand{font-weight:800;font-size:1.6rem;color:#14142B;letter-spacing:-.02em}
.hero{background:#14142B;color:#fff;border-radius:22px;padding:22px 26px;margin:8px 0 14px}
.hero small{color:#A9A8C8;font-weight:600}.hero .big{font-size:2.7rem;font-weight:800;letter-spacing:-.025em;line-height:1.1;margin:2px 0 10px}
.chip{display:inline-block;padding:3px 11px;border-radius:99px;font-weight:700;font-size:.82rem;margin:2px 6px 2px 0}
.chip.up{background:#DDF5E7;color:#0B7A3B}.chip.dn{background:#FDE3E4;color:#B4232A}.chip.nt{background:#ECEBF7;color:#4A4980}
.hero .chip.up{background:#16A34A33;color:#7BF0A5}.hero .chip.dn{background:#E5484D33;color:#FF9A9D}.hero .chip.nt{background:#ffffff1f;color:#E7E6FF}
.kc{background:#fff;border-radius:16px;padding:14px 16px;border-left:6px solid var(--c);box-shadow:0 1px 4px rgba(20,20,43,.07);margin-bottom:8px}
.kc .l{color:#6B6A8C;font-size:.82rem;font-weight:600}.kc .v{font-size:1.45rem;font-weight:800;color:#14142B;line-height:1.3}
.pbar{height:6px;background:#ECEBF7;border-radius:9px;margin-top:9px;overflow:hidden}.pbar i{display:block;height:100%;background:var(--c);border-radius:9px}
.stTabs [data-baseweb="tab-list"]{gap:6px}.stTabs [data-baseweb="tab"]{border-radius:99px;padding:6px 18px;background:#fff;height:auto}
.stTabs [aria-selected="true"]{background:#14142B!important}.stTabs [aria-selected="true"] p{color:#fff!important}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none}
div[data-testid="stMetric"]{background:#fff;border-radius:14px;padding:10px 14px;box-shadow:0 1px 4px rgba(20,20,43,.07)}
div[data-testid="stExpander"]{background:#fff;border-radius:14px;border:0;box-shadow:0 1px 4px rgba(20,20,43,.07)}
.stButton>button,.stDownloadButton>button{border-radius:12px;font-weight:700}
</style>""", unsafe_allow_html=True)

MES = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]

def has(k):
    try: return k in st.secrets
    except Exception: return False

# ---------- palavra-passe (opcional: secret APP_PASSWORD) ----------
if has("APP_PASSWORD") and not st.session_state.get("ok"):
    pw = st.text_input("Palavra-passe", type="password")
    if pw and pw == st.secrets["APP_PASSWORD"]:
        st.session_state.ok = True; st.rerun()
    st.stop()

# ---------- armazenamento: Turso via HTTP (ou state.json em local) ----------
def turso(sql, args=()):
    url = st.secrets["TURSO_URL"].replace("libsql://", "https://")
    r = requests.post(url + "/v2/pipeline", headers={"Authorization": "Bearer " + st.secrets["TURSO_TOKEN"]}, timeout=20,
        json={"requests": [{"type": "execute", "stmt": {"sql": sql, "args": [{"type": "text", "value": a} for a in args]}}, {"type": "close"}]})
    r.raise_for_status()
    return r.json()["results"][0]["response"]["result"]["rows"]

def save():
    s = json.dumps(st.session_state.S, ensure_ascii=False)
    if has("TURSO_URL"):
        turso("INSERT INTO kv(k,v) VALUES('state',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (s,))
    else:
        open("state.json", "w").write(s)

if "S" not in st.session_state:
    try:
        S = None
        if has("TURSO_URL"):
            turso("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
            rows = turso("SELECT v FROM kv WHERE k='state'")
            S = json.loads(rows[0][0]["value"]) if rows else None
        elif os.path.exists("state.json"):
            S = json.load(open("state.json"))
        st.session_state.S = S or json.load(open("seed.json"))
        if S is None: save()
    except Exception as e:
        st.error(f"Não consegui ligar à base de dados: {e}"); st.stop()
S = st.session_state.S
S.setdefault("div", [])

# ---------- cotações e câmbios (yfinance) ----------
@st.cache_data(ttl=900)
def quote(sym):
    try:
        fi = yf.Ticker(sym).fast_info
        p, c = float(fi["last_price"]), fi["currency"]
        return (p / 100, "GBP") if c == "GBp" else (p, c)
    except Exception:
        return None, None

@st.cache_data(ttl=900)
def fx_live(cur):
    if cur == "EUR": return 1.0
    return quote(f"{cur}EUR=X")[0]

def rate_of(c, fb=1.0):
    """Câmbio atual para €: manual (se definido) > Yahoo ao vivo > último guardado."""
    return 1.0 if c == "EUR" else (S.get("fxman", {}).get(c) or fx_live(c) or S["fx"].get(c) or fb)

def positions(group):
    m, last = {}, {}
    for t in sorted(S["tx"], key=lambda t: t["date"]):
        last[t["tk"]] = t
        p = m.setdefault((t["pie"] if group == "pie" else "—", t["tk"]), dict(Pie=t["pie"] if group == "pie" else "—", Ativo=t["tk"], Qtd=0.0, Custo=0.0, CN=0.0, pies=set()))
        p["pies"].add(t["pie"])
        if t["type"] == "Compra":
            p["Qtd"] += t["qty"]; p["CN"] += t["qty"] * t["price"]
        else:
            f = min(1, t["qty"] / p["Qtd"]) if p["Qtd"] > 0 else 0
            p["CN"] -= p["CN"] * f; p["Qtd"] -= t["qty"]
    out = []
    for p in m.values():
        if p["Qtd"] <= 1e-9: continue
        l = last[p["Ativo"]]
        price, cur = quote(S["ymap"].get(p["Ativo"], p["Ativo"]))
        live = price is not None
        if not live: price, cur = S["px"].get(p["Ativo"], l["price"]), l["cur"]
        val = p["Qtd"] * price * rate_of(cur, l["fx"]); custo = p["CN"] * rate_of(l["cur"], l["fx"])  # custo = qtd x preço de compra, convertido ao câmbio atual
        out.append({"Ativo": p["Ativo"], "Pie": p["Pie"] if group == "pie" else ", ".join(sorted(p["pies"])), "Moeda": cur, "Qtd": p["Qtd"],
            "Preço": price, "Custo €": custo, "Valor €": val, "L/P €": val - custo, "L/P %": (val / custo - 1) * 100 if custo else 0,
            "Fonte": "ao vivo" if live else "último preço"})
    df = pd.DataFrame(out)
    if not df.empty: df["Peso %"] = df["Valor €"] / df["Valor €"].sum() * 100
    return df.sort_values("Valor €", ascending=False) if not df.empty else df

@st.cache_data(ttl=3600)
def hist(sym, start):
    try:
        tk = yf.Ticker(sym); cur = tk.fast_info["currency"]
        h = tk.history(start=start, auto_adjust=False)["Close"]
        if h.empty: return None, None
        h.index = h.index.tz_localize(None).normalize(); h = h[~h.index.duplicated()]
        return (h / 100, "GBP") if cur == "GBp" else (h, cur)
    except Exception:
        return None, None

def timeline(txs):
    """Valor investido (qtd x preço de compra) e valor atual (qtd x preço de fecho), ambos ao câmbio atual, por dia útil."""
    days = pd.bdate_range(min(t["date"] for t in txs), dt.date.today())
    inv = pd.Series(0.0, index=days); val = inv.copy(); groups = {}
    for t in sorted(txs, key=lambda t: t["date"]): groups.setdefault((t["pie"], t["tk"]), []).append(t)
    for (pie, tk), L in groups.items():
        q = c = 0.0; ev = {}
        for t in L:
            if t["type"] == "Compra": q += t["qty"]; c += t["qty"] * t["price"]
            else:
                f = min(1, t["qty"] / q) if q > 0 else 0; c -= c * f; q -= t["qty"]
            ev[pd.Timestamp(t["date"])] = (q, c)
        s = pd.DataFrame(ev, index=["q", "c"]).T
        s = s.reindex(s.index.union(days)).ffill().reindex(days).fillna(0)
        p, cur = hist(S["ymap"].get(tk, tk), L[0]["date"])
        if p is None or p.empty:  # sem histórico: usa os preços das compras
            cur = L[-1]["cur"]; p = pd.Series({pd.Timestamp(t["date"]): t["price"] for t in L}); p = p[~p.index.duplicated(keep="last")]
        p = p.reindex(p.index.union(days)).ffill().bfill().reindex(days)
        r = rate_of(cur, L[-1]["fx"])
        inv += s["c"] * rate_of(L[-1]["cur"], L[-1]["fx"]); val += s["q"] * p * r
    return pd.DataFrame({"Valor investido": inv, "Valor atual": val})

def show_tl(txs, title, key, color="#6D5BF7", tl=None):
    tl = tl if tl is not None else timeline(txs); win = tl["Valor atual"].iloc[-1] >= tl["Valor investido"].iloc[-1]
    fig = go.Figure([go.Scatter(x=tl.index, y=tl["Valor investido"], name="Investido", line=dict(color="#94A3B8", dash="dot", width=2)),
        go.Scatter(x=tl.index, y=tl["Valor atual"], name="Valor atual", line=dict(color=color, width=3), fill="tonexty", fillcolor="rgba(18,161,80,.16)" if win else "rgba(229,72,77,.16)")])
    fig.update_layout(title=dict(text=title, font=dict(size=15)), height=300, margin=dict(t=46, b=10, l=10, r=10), hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.14, x=1, xanchor="right"), yaxis=dict(gridcolor="#E7E5F0", ticksuffix=" €"), xaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch", key=key)

_tlc = {}
def tl_of(key, txs):
    if key not in _tlc: _tlc[key] = timeline(txs)
    return _tlc[key]

def pie_stats(tl, txs):
    """Retorno diário ponderado pelo tempo (tira as entradas e saídas de dinheiro) e estatísticas: dia, drawdown, melhor/pior dia, volatilidade."""
    V = tl["Valor atual"]; fl = pd.Series(0.0, index=tl.index)
    for t in txs:
        p = tl.index.searchsorted(pd.Timestamp(t["date"]))
        if p < len(tl.index): fl.iloc[p] += (1 if t["type"] == "Compra" else -1) * t["qty"] * t["price"] * rate_of(t["cur"], t["fx"])
    prev = V.shift(1); r = ((V - fl) / prev - 1).where(prev > 1e-6).replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) < 2: return None
    idx = (1 + r).cumprod(); dd = idx / idx.cummax() - 1
    return dict(last=float(r.iloc[-1]) * 100, chg=float((V - prev - fl).iloc[-1]), mdd=float(dd.min()) * 100, cur_dd=float(dd.iloc[-1]) * 100,
        best=(r.idxmax(), float(r.max()) * 100), worst=(r.idxmin(), float(r.min()) * 100), vol=float(r.std() * np.sqrt(252)) * 100)

@st.cache_data(ttl=3600)
def hist_full(sym):
    try:
        tk = yf.Ticker(sym); cur = tk.fast_info["currency"]
        h = tk.history(period="max", auto_adjust=False)
        if h.empty: return None, None
        h.index = h.index.tz_localize(None).normalize(); h = h[~h.index.duplicated()]
        if cur == "GBp": h[["Open", "High", "Low", "Close"]] = h[["Open", "High", "Low", "Close"]] / 100; cur = "GBP"
        return h, cur
    except Exception:
        return None, None

@st.cache_data(ttl=3600)
def info(sym):
    try:
        t = yf.Ticker(sym); i = dict(t.info or {})
        dv = t.dividends
        if len(dv):
            dv.index = dv.index.tz_localize(None); i["div12m"] = float(dv[dv.index >= pd.Timestamp.today() - pd.Timedelta(days=365)].sum())
        return i
    except Exception:
        return {}

PER = {"1M": 30, "3M": 91, "6M": 182, "YTD": None, "1A": 365, "2A": 730, "5A": 1826, "Máx": 0}

@st.dialog("Detalhe do ativo", width="large")
def detail(tk):
    sym = S["ymap"].get(tk, tk); txs = [t for t in S["tx"] if t["tk"] == tk]
    st.subheader(f"{tk}  ·  {sym}")
    per = st.radio("Período", list(PER), index=4, horizontal=True)
    h, cur = hist_full(sym)
    if h is None:
        st.warning("Não encontrei histórico no Yahoo para este símbolo. Corrige-o em Transações → Pies e símbolos do Yahoo.")
        st.dataframe(pd.DataFrame(txs).drop(columns=["id"], errors="ignore"), hide_index=True); return
    today = pd.Timestamp(dt.date.today())
    start = pd.Timestamp(today.year, 1, 1) if per == "YTD" else (h.index[0] if PER[per] == 0 else today - pd.Timedelta(days=PER[per]))
    d = h[h.index >= start]
    if len(d) < 3: st.warning("Poucos dados neste período."); return
    c = d["Close"]; r = c.pct_change().dropna(); dd = c / c.cummax() - 1; i = info(sym)
    t_stats, t_graf, t_prev, t_dados = st.tabs(["Estatísticas", "Gráficos", "Previsão", "Dados"])
    with t_stats:
        k = st.columns(4); k[0].metric(f"Preço ({cur})", f"{c.iloc[-1]:,.2f}"); k[1].metric(f"Retorno ({per})", f"{(c.iloc[-1]/c.iloc[0]-1)*100:+.2f} %")
        k[2].metric("Máximo / Mínimo", f"{c.max():,.2f} / {c.min():,.2f}"); k[3].metric("Volatilidade anual", f"{r.std()*np.sqrt(252)*100:.1f} %")
        k = st.columns(4); k[0].metric("Queda máx. (drawdown)", f"{dd.min()*100:.1f} %"); k[1].metric("MM50", f"{h['Close'].rolling(50).mean().iloc[-1]:,.2f}"); k[2].metric("MM200", f"{h['Close'].rolling(200).mean().iloc[-1]:,.2f}")
        k[3].metric("Dividendos 12m", f"{i['div12m']:.2f} ({i['div12m']/c.iloc[-1]*100:.2f} %)" if i.get("div12m") else "—")
        rows = {"Nome": i.get("longName"), "Setor": i.get("sector"), "Indústria": i.get("industry"), "Market cap": f"{i['marketCap']/1e9:,.1f} mil M" if i.get("marketCap") else None,
            "P/E": i.get("trailingPE"), "P/E futuro": i.get("forwardPE"), "Alvo analistas (médio)": i.get("targetMeanPrice"), "Alvo mín. / máx.": f"{i.get('targetLowPrice')} / {i.get('targetHighPrice')}" if i.get("targetMeanPrice") else None,
            "Recomendação": i.get("recommendationKey"), "Nº analistas": i.get("numberOfAnalystOpinions")}
        rows = {a: str(b) for a, b in rows.items() if b not in (None, "")}
        if rows: st.dataframe(pd.DataFrame({"Dado": rows.keys(), "Valor": rows.values()}), hide_index=True, width="stretch")
        pdf = positions("pie"); pdf = pdf[pdf["Ativo"] == tk][["Pie", "Qtd", "Custo €", "Valor €", "L/P €", "L/P %"]] if not pdf.empty else pdf
        if len(pdf): st.markdown("**A minha posição**"); st.dataframe(pdf.style.format({"Qtd": "{:.4f}", "Custo €": "{:.2f}", "Valor €": "{:.2f}", "L/P €": "{:+.2f}", "L/P %": "{:+.2f}"}), hide_index=True, width="stretch")
    with t_graf:
        a, b = st.columns(2); kind = a.radio("Tipo", ["Linha", "Candlestick"], horizontal=True); ma = b.checkbox("Médias móveis 50/200", True)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.75, .25], vertical_spacing=.03)
        if kind == "Linha": fig.add_trace(go.Scatter(x=d.index, y=c, name="Fecho", line=dict(color="#2f6df6")), 1, 1)
        else: fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=c, name="Preço"), 1, 1)
        if ma:
            for n, col in ((50, "#e5a113"), (200, "#8e5bd9")): fig.add_trace(go.Scatter(x=d.index, y=h["Close"].rolling(n).mean()[d.index], name=f"MM{n}", line=dict(color=col, width=1)), 1, 1)
        tb = [t for t in txs if t["type"] == "Compra" and t["cur"] == cur and pd.Timestamp(t["date"]) >= start]
        if tb: fig.add_trace(go.Scatter(x=[t["date"] for t in tb], y=[t["price"] for t in tb], mode="markers", name="Minhas compras", marker=dict(size=9, color="#13935a", symbol="triangle-up")), 1, 1)
        fig.add_trace(go.Bar(x=d.index, y=d["Volume"], name="Volume", marker_color="#7a8699"), 2, 1)
        fig.update_layout(height=560, xaxis_rangeslider_visible=False, margin=dict(t=20), legend_orientation="h"); st.plotly_chart(fig, width="stretch")
        st.plotly_chart(px.area(dd * 100, title="Queda desde o máximo (%)").update_layout(showlegend=False, yaxis_title="%", xaxis_title=None, height=260), width="stretch")
    with t_prev:
        hz = st.select_slider("Horizonte (dias)", [30, 60, 90, 180, 365], value=90); lr = np.log(c).diff().dropna(); mu, sg = lr.mean(), lr.std(); n = max(2, int(hz * 252 / 365))
        paths = c.iloc[-1] * np.exp(np.cumsum((mu - .5 * sg ** 2) + sg * np.random.default_rng(1).normal(size=(2000, n)), axis=1)); q = np.percentile(paths, [10, 50, 90], axis=0)
        fx_ = pd.bdate_range(c.index[-1] + pd.Timedelta(days=1), periods=n); hh = c.iloc[-min(len(c), 252):]
        fig = go.Figure([go.Scatter(x=hh.index, y=hh, name="Histórico", line=dict(color="#2f6df6")), go.Scatter(x=fx_, y=q[2], line=dict(width=0), showlegend=False),
            go.Scatter(x=fx_, y=q[0], fill="tonexty", fillcolor="rgba(120,120,120,.25)", line=dict(width=0), name="Intervalo 10–90%"), go.Scatter(x=fx_, y=q[1], name="Mediana", line=dict(dash="dash", color="#e5a113"))])
        st.plotly_chart(fig.update_layout(height=420, margin=dict(t=20), legend_orientation="h"), width="stretch")
        k = st.columns(4); k[0].metric("Mediana final", f"{q[1][-1]:,.2f} ({(q[1][-1]/c.iloc[-1]-1)*100:+.1f} %)"); k[1].metric("Cenário baixo (10%)", f"{q[0][-1]:,.2f}"); k[2].metric("Cenário alto (90%)", f"{q[2][-1]:,.2f}"); k[3].metric("Prob. de subir", f"{(paths[:, -1] > c.iloc[-1]).mean()*100:.0f} %")
        if i.get("targetMeanPrice"): st.info(f"Preço-alvo médio dos analistas: {i['targetMeanPrice']:,.2f} {cur} ({(i['targetMeanPrice']/c.iloc[-1]-1)*100:+.1f} % face ao preço atual).")
        st.caption("Simulação estatística (Monte Carlo) com a rentabilidade e volatilidade do período escolhido. Não é uma previsão fiável: não conhece notícias, resultados nem o mercado.")
    with t_dados:
        st.dataframe(d[["Open", "High", "Low", "Close", "Volume"]].sort_index(ascending=False).style.format("{:,.2f}", subset=["Open", "High", "Low", "Close"]), width="stretch", height=300)
        if txs: st.markdown("**As minhas transações**"); st.dataframe(pd.DataFrame(txs).drop(columns=["id", "bid"], errors="ignore").sort_values("date", ascending=False), hide_index=True, width="stretch")

@st.cache_data(ttl=21600)
def dps_hist(sym):
    """Histórico de dividendos por ação (moeda de cotação) do Yahoo."""
    try:
        t = yf.Ticker(sym); dv = t.dividends; cur = t.fast_info["currency"]
        if dv is None or dv.empty: return None, cur
        dv.index = dv.index.tz_localize(None).normalize()
        return (dv / 100, "GBP") if cur == "GBp" else (dv, cur)
    except Exception:
        return None, None

def pie_of(tk, date):
    q = {}
    for t in S["tx"]:
        if t["tk"] == tk and t["date"] <= date: q[t["pie"]] = q.get(t["pie"], 0) + (t["qty"] if t["type"] == "Compra" else -t["qty"])
    if not q: q = {t["pie"]: 1 for t in S["tx"] if t["tk"] == tk}
    return max(q, key=q.get) if q else None

def parse_div(f):
    d = pd.read_csv(f); d = d[d["Action"].str.contains("dividend", case=False, na=False)].copy(); have = {x["id"] for x in S["div"]}; rows = []
    d["_d"] = d["Time (UTC)"].astype(str).str[:10]
    if "ID" in d.columns and d["ID"].notna().all(): d["_id"] = d["ID"].astype(str)
    else:  # sem coluna ID (export de dividendos): id estável = data|ativo|ações|total|tipo|nº de repetição
        k = d["_d"] + "|" + d["Ticker"].astype(str) + "|" + d["No. of shares"].astype(str) + "|" + d["Total"].astype(str) + "|" + d["Action"].astype(str)
        d["_id"] = k + "|" + k.groupby(k).cumcount().astype(str)
    for _, x in d.iterrows():
        tk = x.get("Ticker")
        if pd.isna(tk): continue
        rows.append({"Importar": x["_id"] not in have, "Pie": pie_of(tk, x["_d"]), "Data": x["_d"], "Ativo": tk, "Valor": float(x["Total"]), "Moeda": x["Currency (Total)"], "ID": x["_id"], "Duplicado": x["_id"] in have})
    return pd.DataFrame(rows)

# ---- calendário: datas oficiais (BLS, Fed, BCE) confirmadas até abril de 2027
NY, CET = "America/New_York", "Europe/Berlin"
TYPES = {
 "FOMC": dict(tag="Fed · EUA", title="Decisão de juros da Fed (FOMC)", imp=3, color="#E5484D", kind="m",
   desc="O comité da Fed decide a taxa de juro dos EUA e publica o comunicado. Logo a seguir (14h30 em Nova Iorque) o presidente da Fed faz a conferência de imprensa, que costuma mexer mais com os mercados do que a própria decisão.",
   watch="Se a decisão e o tom surpreendem face ao esperado. Juros altos por mais tempo pesam em tecnológicas, quantum e REITs; sinais de cortes ajudam. O dólar também reage."),
 "ATAS": dict(tag="Fed · EUA", title="Atas da última reunião da Fed", imp=2, color="#E5484D", kind="m",
   desc="Publicadas três semanas depois da decisão. Mostram o debate interno: quantos membros defendiam subir, manter ou cortar os juros.",
   watch="Sinais sobre a próxima decisão. Atas mais duras ou mais brandas do que o esperado mexem com as taxas de juro e com o dólar."),
 "CPI": dict(tag="Inflação · EUA", title="Inflação nos EUA (CPI)", imp=3, color="#3B82F6", kind="m",
   desc="Mede a variação dos preços ao consumidor no mês anterior. É o dado que mais influencia as expectativas para os juros da Fed.",
   watch="A inflação 'core' (sem alimentos e energia) face ao esperado. Acima do esperado: juros mais altos por mais tempo e pressão nas ações de crescimento. Abaixo: alívio."),
 "NFP": dict(tag="Emprego · EUA", title="Relatório de emprego dos EUA (NFP)", imp=3, color="#3B82F6", kind="m",
   desc="Postos de trabalho criados, taxa de desemprego e salários do mês anterior. Mostra a força da economia americana.",
   watch="Emprego muito forte pode adiar cortes de juros; muito fraco assusta com recessão. Os salários também contam para a inflação."),
 "BCE": dict(tag="BCE · Zona euro", title="Decisão de juros do BCE", imp=3, color="#0FB5A6", kind="m",
   desc="O Conselho do BCE decide as taxas de juro da zona euro (decisão às 14h15 CET, conferência de imprensa às 14h45).",
   watch="Efeito no euro e nos ETFs europeus. Um euro mais forte reduz o valor em euros das tuas ações em dólares."),
 "WITCH": dict(tag="Mercado", title="Expiração de opções e futuros (triple witching)", imp=1, color="#94A3B8", kind="x",
   desc="Terceira sexta-feira de março, junho, setembro e dezembro: vencem opções e futuros sobre índices e ações.",
   watch="Mais volume e movimentos bruscos perto do fecho. Normalmente não muda a tendência."),
 "FERIADO": dict(tag="Feriado", title="Mercados fechados", imp=1, color="#94A3B8", kind="x", desc="Sem negociação nem cotações novas.", watch="Ordens feitas nesse dia só executam na abertura seguinte."),
}
MACRO = ([(d, "08:30", NY, "NFP") for d in ("2026-12-04", "2027-01-08", "2027-02-05", "2027-03-05", "2027-04-02")]
  + [(d, "08:30", NY, "CPI") for d in ("2026-12-10", "2027-01-13", "2027-02-11", "2027-03-10", "2027-04-13")]
  + [(d, "14:00", NY, "FOMC") for d in ("2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28")]
  + [(d, "14:00", NY, "ATAS") for d in ("2026-12-30", "2027-02-17", "2027-04-07", "2027-05-19")]
  + [(d, "14:15", CET, "BCE") for d in ("2026-12-17", "2027-02-04", "2027-03-18", "2027-04-29")]
  + [(d, None, None, "WITCH") for d in ("2026-12-18", "2027-03-19")]
  + [(d, None, None, "FERIADO:" + n) for d, n in (("2026-12-25", "Natal (EUA e Europa)"), ("2027-01-01", "Ano Novo (EUA e Europa)"), ("2027-01-18", "Martin Luther King (só EUA)"), ("2027-02-15", "Presidents Day (só EUA)"), ("2027-03-26", "Sexta-feira Santa (EUA e Europa)"))])
WD = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

def lisboa(d, hm, tz):
    h, m = map(int, hm.split(":")); return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=ZoneInfo(tz)).astimezone(ZoneInfo("Europe/Lisbon")).strftime("%H:%M")

def _cal1(sym):
    """Calendário do Yahoo; se não trouxer resultados, tenta o histórico de datas e, em último caso, estima (último trimestre + 91 dias)."""
    out = {}; hoje = dt.date.today()
    try:
        t = yf.Ticker(sym); c = t.calendar
        if isinstance(c, dict): out.update(c)
    except Exception:
        return out
    if not out.get("Earnings Date"):
        try:
            e = t.get_earnings_dates(limit=8)
            if e is not None and len(e):
                days = sorted({i.date() for i in e.index}); fut = [x for x in days if x >= hoje]
                if fut:
                    out["Earnings Date"] = [fut[0]]
                    for i, row in e.iterrows():
                        if i.date() == fut[0] and row.get("EPS Estimate") == row.get("EPS Estimate"): out["Earnings Average"] = row.get("EPS Estimate")
                else:
                    d = days[-1] + dt.timedelta(days=91)
                    while d < hoje: d += dt.timedelta(days=91)
                    out["Earnings Date"] = [d]; out["_est"] = True
        except Exception:
            pass
    return out

@st.cache_data(ttl=21600)
def cal_all(syms):
    with cf.ThreadPoolExecutor(4) as ex: return dict(zip(syms, ex.map(_cal1, syms)))

def to_date(v):
    try:
        if v is None or pd.isna(v): return None
        d = v if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else pd.Timestamp(v).date()
        return None if pd.isna(d) else d
    except Exception: return None

MKT = [("S&P 500", "^GSPC"), ("Nasdaq", "^IXIC"), ("Dow Jones", "^DJI"), ("Euro Stoxx 50", "^STOXX50E"), ("DAX", "^GDAXI"), ("FTSE 100", "^FTSE"), ("Nikkei 225", "^N225"),
       ("EUR/USD", "EURUSD=X"), ("Ouro", "GC=F"), ("Petróleo WTI", "CL=F"), ("VIX (medo)", "^VIX"), ("Yield 10 anos EUA", "^TNX")]

@st.cache_data(ttl=900)
def closes(syms):
    try:
        d = yf.download(list(syms), period="3mo", auto_adjust=False, progress=False, group_by="column", threads=True)["Close"]
        if isinstance(d, pd.Series): d = d.to_frame(syms[0])
        d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
        return d.ffill()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=900)
def headlines(sym, n=4):
    out = []
    try:
        for it in (yf.Ticker(sym).news or [])[:n]:
            c = it.get("content") or it; title = c.get("title")
            if title: out.append((title, (c.get("canonicalUrl") or {}).get("url") or c.get("link") or "", (c.get("provider") or {}).get("displayName") or c.get("publisher") or "", str(c.get("pubDate") or "")[:10]))
    except Exception:
        pass
    return out

@st.cache_data(ttl=86400, show_spinner=False)
def ai_explain(prompt):
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=120, headers={"x-api-key": st.secrets["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": st.secrets["ANTHROPIC_MODEL"] if has("ANTHROPIC_MODEL") else "claude-sonnet-5-5", "max_tokens": 1200, "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}], "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status(); return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")

def qty_before(d):
    q = {}
    for t in S["tx"]:
        if t["date"] < str(d): q[(t["pie"], t["tk"])] = q.get((t["pie"], t["tk"]), 0) + (t["qty"] if t["type"] == "Compra" else -t["qty"])
    return {k: v for k, v in q.items() if v > 1e-9}

def gh_grid(vals, year, title, lo, hi):
    """Grelha estilo GitHub: 1 quadrado por dia do ano (colunas = semanas, linhas = dias da semana); intensidade ~ raiz do valor desse dia."""
    j1 = dt.date(year, 1, 1); n = (dt.date(year, 12, 31) - j1).days + 1; nw = (n - 1 + j1.weekday()) // 7 + 1
    z = np.full((7, nw), np.nan); txt = [[None] * nw for _ in range(7)]; vmax = max([v for d_, v in vals.items() if d_.year == year] or [0]); mt, mv = [], []
    for i in range(n):
        d_ = j1 + dt.timedelta(days=i); wk, wd = (i + j1.weekday()) // 7, d_.weekday(); v = vals.get(d_, 0.0)
        z[wd, wk] = 0 if v <= 0 or vmax <= 0 else 0.2 + 0.8 * (v / vmax) ** 0.5
        txt[wd][wk] = f"{d_.day}/{d_.month}/{d_.year}: " + (f"{num(v)} €" if v > 0 else "sem atividade")
        if d_.day == 1: mt.append(wk); mv.append(MES[d_.month - 1][:3])
    fig = go.Figure(go.Heatmap(z=z, text=txt, hoverinfo="text", colorscale=[[0, "#ECEBF7"], [0.001, lo], [1, hi]], zmin=0, zmax=1, showscale=False, xgap=3, ygap=3))
    fig.update_yaxes(autorange="reversed", tickvals=[0, 2, 4], ticktext=["Seg", "Qua", "Sex"], showgrid=False, zeroline=False, scaleanchor="x", scaleratio=1)
    fig.update_xaxes(tickvals=mt, ticktext=mv, showgrid=False, zeroline=False, side="top")
    return fig.update_layout(title=dict(text=title, font=dict(size=15)), height=230, margin=dict(t=64, b=5, l=40, r=5), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"), sum(v for d_, v in vals.items() if d_.year == year), sum(1 for d_, v in vals.items() if d_.year == year and v > 0), vmax

# ---- radar de fundamentais
AXES = ["Crescimento", "Valorização", "Dividendos", "Solidez financeira", "Momento", "Diversificação"]
lin = lambda x, lo, hi: float(min(1.0, max(0.0, (x - lo) / (hi - lo))) * 100)
isn = lambda x: isinstance(x, (int, float)) and x == x and abs(x) != float("inf")

@st.cache_data(ttl=21600)
def fund_all(syms):
    def one(sym):
        out = {}
        try:
            t = yf.Ticker(sym); i = t.info or {}
            out = {k: i.get(k) for k in ("quoteType", "sector", "revenueGrowth", "earningsGrowth", "forwardPE", "trailingPE", "debtToEquity", "currentRatio")}
            try:
                dv = t.dividends; dv.index = dv.index.tz_localize(None)
                out["div12"] = float(dv[dv.index >= pd.Timestamp.today() - pd.Timedelta(days=365)].sum()) / (100 if sym.endswith(".L") else 1)
            except Exception: out["div12"] = None
        except Exception:
            pass
        return out
    with cf.ThreadPoolExecutor(4) as ex: return dict(zip(syms, ex.map(one, syms)))

@st.cache_data(ttl=3600)
def closes1y(syms):
    try:
        d = yf.download(list(syms), period="14mo", auto_adjust=False, progress=False, group_by="column", threads=True)["Close"]
        if isinstance(d, pd.Series): d = d.to_frame(syms[0])
        d.index = pd.to_datetime(d.index).tz_localize(None).normalize(); return d.ffill()
    except Exception:
        return pd.DataFrame()

def radar_scores(sub, F, H):
    """Pontuação 0-100 por eixo. Média ponderada pelo valor de cada posição, só com as posições que têm dados; devolve também a cobertura (% do valor com dados)."""
    V = sub["Valor €"].astype(float).values; w = V / V.sum() if V.sum() else V; rows = []
    for (_, r), wi in zip(sub.iterrows(), w):
        sy = S["ymap"].get(r["Ativo"], r["Ativo"]); f = F.get(sy) or {}; has = bool(f.get("quoteType")); eq = f.get("quoteType") == "EQUITY"
        px = H[sy].dropna() if sy in H.columns else pd.Series(dtype=float); o = dict(Ativo=r["Ativo"], w=wi, setor=f.get("sector") or ("ETF" if f.get("quoteType") == "ETF" else "Outro"))
        gs = [(min(max(f[k], -.5), 1.0), q) for k, q in (("revenueGrowth", .6), ("earningsGrowth", .4)) if isn(f.get(k))]  # receita pesa 60 %, lucros 40 %
        o["gr"] = sum(a * q for a, q in gs) / sum(q for _, q in gs) if gs else None; o["s_cr"] = lin(o["gr"], -.10, .30) if gs else None
        pe = next((f[k] for k in ("forwardPE", "trailingPE") if isn(f.get(k)) and f[k] > 0), None); o["pe"] = pe; o["ey"] = 1 / pe if pe else (0.0 if eq else None)  # sem lucros = earnings yield 0
        o["y"] = f["div12"] / r["Preço"] if has and isn(f.get("div12")) and r["Preço"] else None; o["s_dv"] = lin(o["y"], 0, .05) if o["y"] is not None else None
        de = f.get("debtToEquity") if f.get("sector") != "Financial Services" else None; ps = []
        if isn(de): o["de"] = de; ps.append((100 - lin(de, 30, 250), .7))
        if isn(f.get("currentRatio")) and f.get("sector") != "Financial Services": ps.append((lin(f["currentRatio"], .8, 2.0), .3))
        o["s_so"] = sum(a * q for a, q in ps) / sum(q for _, q in ps) if ps else None
        n = len(px); r12 = px.iloc[-22] / px.iloc[-253] - 1 if n >= 253 else (px.iloc[-22] / px.iloc[-127] - 1 if n >= 127 else None)  # momento 12-1 meses (ou 6-1 se houver pouco histórico)
        dist = px.iloc[-1] / px.iloc[-200:].mean() - 1 if n >= 150 else None; o["r12"] = r12
        o["s_mo"] = (0.7 * lin(r12, -.2, .4) + 0.3 * lin(dist, -.1, .1) if dist is not None else lin(r12, -.2, .4)) if r12 is not None else None; rows.append(o)
    D = pd.DataFrame(rows)
    for c_ in ("gr", "s_cr", "pe", "ey", "y", "s_dv", "de", "s_so", "r12", "s_mo"): D[c_] = pd.to_numeric(D[c_], errors="coerce") if c_ in D else np.nan
    def agg(c):
        m = D[c].notna()
        return (float((D.loc[m, c] * D.loc[m, "w"]).sum() / D.loc[m, "w"].sum()), float(D.loc[m, "w"].sum())) if m.any() else (None, 0.0)
    sc, cv, raw = {}, {}, {}
    g_, cv["Crescimento"] = agg("gr"); sc["Crescimento"] = agg("s_cr")[0]; raw["Crescimento"] = f"crescimento médio {num(g_ * 100, 1, True)} %" if g_ is not None else "sem dados"
    ey, cv["Valorização"] = agg("ey"); pe_p = (1 / ey if ey else None); sc["Valorização"] = (lin(45 - pe_p, 0, 35) if pe_p else 0.0) if ey is not None else None; raw["Valorização"] = (f"P/E da carteira {num(pe_p, 1)} (média harmónica)" if pe_p else "empresas sem lucros") if ey is not None else "sem dados"
    y_, cv["Dividendos"] = agg("y"); sc["Dividendos"] = lin(y_, 0, .05) if y_ is not None else None; raw["Dividendos"] = f"yield {num(y_ * 100, 2)} %" if y_ is not None else "sem dados"
    sc["Solidez financeira"], cv["Solidez financeira"] = agg("s_so"); de_, _ = agg("de"); raw["Solidez financeira"] = f"dívida/capitais próprios médio {num(de_, 0)} %" if de_ is not None else "sem dados"
    sc["Momento"], cv["Momento"] = agg("s_mo"); m_, _ = agg("r12"); raw["Momento"] = f"retorno 12-1 meses {num(m_ * 100, 1, True)} %" if m_ is not None else "sem dados"
    ww = D["w"].values; effn = 1 / (ww ** 2).sum() if len(ww) else 0; sw = D.groupby("setor")["w"].sum().values; effs = 1 / (sw ** 2).sum() if len(sw) else 0; rho = None
    cols = [S["ymap"].get(a, a) for a in D["Ativo"]]; ok = [(c, wv) for c, wv in zip(cols, ww) if c in H.columns and H[c].dropna().shape[0] >= 120]
    if len(ok) >= 2:
        Rt = H[[c for c, _ in ok]].iloc[-252:].pct_change().dropna(how="all").corr().values; wv = np.array([x for _, x in ok]); W = np.outer(wv, wv); np.fill_diagonal(W, 0)
        rho = float((W * np.nan_to_num(Rt)).sum() / W.sum()) if W.sum() else None
    parts = [(lin(effn, 1, 25), .4), (lin(effs, 1, 8), .3)] + ([(lin(.8 - rho, 0, .6), .3)] if rho is not None else [])
    sc["Diversificação"] = sum(a * q for a, q in parts) / sum(q for _, q in parts); cv["Diversificação"] = 1.0
    raw["Diversificação"] = f"{num(effn, 1)} posições efetivas · {num(effs, 1)} setores efetivos" + (f" · correlação média {num(rho, 2)}" if rho is not None else "")
    return dict(sc=sc, cv=cv, raw=raw, D=D)

def parse_csv(f):
    d = pd.read_csv(f); d = d[d["Action"].str.contains("buy|sell", case=False, na=False)]; rows = []
    d["_ts"] = pd.to_datetime(d["Time (UTC)"], utc=True).astype("int64") / 1e9
    def ref_fx(cur, ts):  # ordens pagas com saldo em moeda estrangeira (Total != EUR): usa o câmbio da ordem em € mais próxima no tempo
        r = d[(d["Currency (Price / share)"] == cur) & (d["Currency (Total)"] == "EUR") & d["Exchange rate"].notna()]
        return float(1 / r.iloc[(r["_ts"] - ts).abs().values.argmin()]["Exchange rate"]) if len(r) else float(S["fx"].get(cur) or 1.0)
    for _, x in d.iterrows():
        cur, ex = x["Currency (Price / share)"], x.get("Exchange rate")
        ex = 1.0 if pd.isna(ex) else float(ex)
        tk, qty, date = x["Ticker"], float(x["No. of shares"]), str(x["Time (UTC)"])[:10]
        dup = any(t.get("bid") == x["ID"] or (t["tk"] == tk and t["date"] == date and abs(t["qty"] - qty) < 1e-6) for t in S["tx"])
        known = sorted({t["pie"] for t in S["tx"] if t["tk"] == tk})
        pie = known[0] if len(known) == 1 else ("ETFs" if not known and re.search("ishares|xetra|etf|vanguard|spdr", str(x["Name"]), re.I) else None)
        rows.append({"Importar": not dup, "Pie": pie, "Data": date, "Ativo": tk, "Tipo": "Venda" if "sell" in x["Action"].lower() else "Compra", "Qtd": qty,
            "Preço": float(x["Price / share"]), "Moeda": cur, "Câmbio €": 1.0 if cur == "EUR" else (1 / ex if x["Currency (Total)"] == "EUR" else ref_fx(cur, x["_ts"])), "ID": x["ID"], "Duplicada": dup})
    return pd.DataFrame(rows)

st.markdown('<div class="brand">📈 Painel Financeiro</div>', unsafe_allow_html=True)
top = st.container()
t1, t_rad, t_day, t_div, t_cal, t2, t3 = st.tabs(["Portfólio", "Radar", "Resumo do dia", "Dividendos", "Calendário", "Transações", "Despesas"])

# ================= PORTFÓLIO =================
with t1:
    dfa = positions("pie")
    if not dfa.empty:
        VA, CA = dfa["Valor €"].sum(), dfa["Custo €"].sum(); LA = VA - CA
        st.markdown(f'<div class="hero"><small>Valor da carteira</small><div class="big">{num(VA)} €</div>{chip(LA, f"{num(LA, 2, True)} €  ·  {num(LA / CA * 100 if CA else 0, 2, True)} %")}'
            f'<span class="chip nt">Investido {num(CA)} €</span></div>', unsafe_allow_html=True)
        gp = dfa.groupby("Pie").agg(v=("Valor €", "sum"), c=("Custo €", "sum")).sort_values("v", ascending=False)
        for i in range(0, len(gp), 4):
            cols = st.columns(4)
            for col, (p, r) in zip(cols, list(gp.iterrows())[i:i + 4]):
                col.markdown(card(p, num(r.v) + " €", chip(r.v - r.c, f"{num(r.v - r.c, 2, True)} € · {num((r.v / r.c - 1) * 100 if r.c else 0, 1, True)} %"), pcol(p), r.v / VA * 100), unsafe_allow_html=True)
    c1, c2 = st.columns([4, 1.5])
    grp = c2.selectbox("Vista", ["Separar por pie", "Agregar por ação"], label_visibility="collapsed")
    open_pies = [p for p in S["pies"] if not dfa.empty and p in set(dfa["Pie"])]
    pie_f = (c1.pills("Pie", ["Todas"] + open_pies, default="Todas", label_visibility="collapsed") or "Todas") if grp.startswith("Sep") else "Todas"
    df = positions("pie" if grp.startswith("Sep") else "tk")
    if df.empty: st.info("Sem posições.")
    else:
        if pie_f != "Todas": df = df[df["Pie"] == pie_f]
        V, C = df["Valor €"].sum(), df["Custo €"].sum()
        if pie_f != "Todas": st.markdown(f'<span class="chip nt">{pie_f}</span>{chip(V - C, f"{num(V)} €  ·  {num(V - C, 2, True)} €  ·  {num((V / C - 1) * 100 if C else 0, 2, True)} %")}', unsafe_allow_html=True)
        scope = [t for t in S["tx"] if (t["pie"] == pie_f if pie_f != "Todas" and grp.startswith("Sep") else t["pie"] in open_pies)]; col = pcol(pie_f) if pie_f != "Todas" else "#6D5BF7"
        with st.spinner("A calcular estatísticas..."): ps = pie_stats(tl_of("sel:" + pie_f, scope), scope)
        k = st.columns(4); dcol = lambda v: UP if v >= 0 else DN; big = df.iloc[0]
        k[0].markdown(card("Valor atual", num(V) + " €", chip(V - C, f"{num(V - C, 2, True)} €  ·  {num((V / C - 1) * 100 if C else 0, 2, True)} %"), col), unsafe_allow_html=True)
        k[1].markdown(card("Valor investido", num(C) + " €", f'<span class="chip nt">{len(df)} posições</span>', col), unsafe_allow_html=True)
        if ps:
            k[2].markdown(card("Variação do dia", num(ps["last"], 2, True) + " %", chip(ps["chg"], num(ps["chg"], 2, True) + " €"), dcol(ps["last"])), unsafe_allow_html=True)
            k[3].markdown(card("Máx. drawdown", num(ps["mdd"], 2) + " %", f'<span class="chip nt">atual {num(ps["cur_dd"], 2)} %</span>', DN), unsafe_allow_html=True)
            k = st.columns(4); dt_ = lambda d_: f'<span class="chip nt">{d_.day}/{d_.month}/{d_.year}</span>'
            k[0].markdown(card("Melhor dia", num(ps["best"][1], 2, True) + " %", dt_(ps["best"][0]), UP), unsafe_allow_html=True)
            k[1].markdown(card("Pior dia", num(ps["worst"][1], 2, True) + " %", dt_(ps["worst"][0]), DN), unsafe_allow_html=True)
            k[2].markdown(card("Volatilidade anual", num(ps["vol"], 1) + " %", '<span class="chip nt">oscilação diária × √252</span>', col), unsafe_allow_html=True)
            k[3].markdown(card("Maior posição", big["Ativo"], f'<span class="chip nt">{num(big["Valor €"] / V * 100 if V else 0, 1)} % da {"pie" if pie_f != "Todas" else "carteira"}</span>', col), unsafe_allow_html=True)
        a, b = st.columns([1, 2])
        if pie_f != "Todas" and grp.startswith("Sep"):
            g = df.groupby("Ativo")["Valor €"].sum().sort_values(ascending=False)
            if len(g) > 10: g = pd.concat([g.head(9), pd.Series({f"Outras ({len(g) - 9})": g.iloc[9:].sum()})])
            fig = px.pie(pd.DataFrame({"Ativo": g.index, "Valor": g.values}), names="Ativo", values="Valor", hole=.62, color_discrete_sequence=PALX); ttl = f"Alocação por ação em {pie_f}"
        else:
            g = df.groupby("Pie")["Valor €"].sum().reset_index(); fig = px.pie(g, names="Pie", values="Valor €", hole=.62, color="Pie", color_discrete_map={p: pcol(p) for p in g["Pie"]}); ttl = "Alocação por pie"
        fig.update_traces(textinfo="percent", marker_line_width=0)
        a.plotly_chart(fig.update_layout(title=ttl, height=380, margin=dict(t=46, b=10, l=10, r=10), legend=dict(orientation="h"), paper_bgcolor="rgba(0,0,0,0)"), width="stretch")
        tm = df.assign(Carteira="Carteira"); path = ["Carteira", "Pie", "Ativo"] if grp.startswith("Sep") else ["Carteira", "Ativo"]
        fig = px.treemap(tm, path=path, values="Valor €", color="L/P %", color_continuous_scale=[[0, DN], [.5, "#F3F2FA"], [1, UP]], range_color=(-30, 30))
        fig.update_traces(texttemplate="<b>%{label}</b><br>%{color:+.1f}%", marker_line_width=2)
        b.plotly_chart(fig.update_layout(title="Mapa da carteira: tamanho = valor, cor = lucro/prejuízo", height=380, margin=dict(t=46, b=10, l=10, r=10), coloraxis_showscale=False, paper_bgcolor="rgba(0,0,0,0)"), width="stretch")
        df = df.reset_index(drop=True)
        sty = df.style.format({"Qtd": "{:.4f}", "Preço": "{:.2f}", "Custo €": "{:.2f}", "Valor €": "{:.2f}", "L/P €": "{:+.2f}", "L/P %": "{:+.2f}", "Peso %": "{:.1f}"}, na_rep="—")
        sty = styler_map(styler_map(sty, pl_style, ["L/P €", "L/P %"]), lambda p: f"color:{pcol(p)};font-weight:700", ["Pie"])
        ev = st.dataframe(sty, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="pos_tbl",
            column_config={"Peso %": st.column_config.ProgressColumn("Peso", format="%.1f%%", min_value=0, max_value=float(max(df["Peso %"].max(), 1)))})
        rows = ev.selection.rows
        if rows:
            tk_sel = df.iloc[rows[0]]["Ativo"]
            if st.button(f"📊 Abrir detalhe de {tk_sel}") or st.session_state.get("opened") != tk_sel: st.session_state.opened = tk_sel; detail(tk_sel)
        else: st.session_state.opened = None
        st.caption("Clica numa linha para abrir o detalhe do ativo (estatísticas, gráficos, previsão e dados).")
        st.caption("“ao vivo” = cotação do Yahoo Finance (atualiza de 15 em 15 min); “último preço” = não encontrei o símbolo, uso o último preço de compra. Corrige os símbolos em Transações.")
        st.subheader("Evolução: valor atual vs valor investido")
        cur_tx = [t for t in S["tx"] if t["pie"] in open_pies]; show_tl(cur_tx, "Geral (pies atuais)", "tl_all", "#14142B", tl_of("sel:Todas", cur_tx))
        pies_in = open_pies; cols = st.columns(2)
        for i, p in enumerate(pies_in):
            with cols[i % 2]: show_tl([t for t in S["tx"] if t["pie"] == p], p, f"tl_pie_{p}", pcol(p), tl_of("sel:" + p, [t for t in S["tx"] if t["pie"] == p]))
        with st.expander("Por ativo"):
            tks = sorted({t["tk"] for t in S["tx"]}); sel = st.selectbox("Ativo", tks); show_tl([t for t in S["tx"] if t["tk"] == sel], sel, "tl_sel")
            if st.checkbox("Mostrar um gráfico por ativo (mais lento)"):
                cols = st.columns(3)
                for i, tk in enumerate(tks):
                    with cols[i % 3]: show_tl([t for t in S["tx"] if t["tk"] == tk], tk, f"tl_{tk}")

# ================= TRANSAÇÕES =================
with t2:
    @st.dialog("➕ Nova transação", width="large")
    def dlg_add():
        a = st.columns(4); d = a[0].date_input("Data"); tk = a[1].text_input("Ticker").upper().strip(); pie = a[2].selectbox("Pie ", S["pies"]); ty = a[3].selectbox("Tipo", ["Compra", "Venda"])
        b = st.columns(4); qty = b[0].number_input("Quantidade", min_value=0.0, format="%.8f"); pr = b[1].number_input("Preço por ação", min_value=0.0, format="%.4f")
        cur = b[2].selectbox("Moeda", sorted(set(["EUR", "USD", "GBP", "CHF", "CAD"]) | set(S["fx"]))); other = b[2].text_input("Outra moeda (código)").upper().strip(); cur = other or cur
        suggest = S["fx"].get(cur) or fx_live(cur) or 1.0
        fxv = float(suggest)
        if st.button("Guardar transação", type="primary"):
            if tk and qty > 0 and pr > 0 and fxv > 0:
                S["tx"].append(dict(id=uuid.uuid4().hex[:8], date=str(d), tk=tk, pie=pie, type=ty, qty=qty, price=pr, cur=cur, fx=fxv)); S["fx"].setdefault(cur, fxv); save(); st.rerun()
            else: st.warning("Preenche ativo, quantidade, preço e câmbio.")
    @st.dialog("📥 Importar CSV (Trading 212)", width="large")
    def dlg_imp():
        f = st.file_uploader("Ficheiro CSV", type="csv")
        if f:
            imp = parse_csv(f); allp = st.selectbox("Pie para todas as linhas", ["—"] + S["pies"])
            if allp != "—": imp["Pie"] = allp
            ed = st.data_editor(imp, hide_index=True, key=f"imp{allp}", disabled=[c for c in imp.columns if c not in ("Importar", "Pie")],
                column_config={"Pie": st.column_config.SelectboxColumn(options=S["pies"])})
            sel = ed[ed["Importar"]]; dups = ed[ed["Duplicada"]]
            upd = False
            n_up = len(dups) if upd else 0
            if sel["Pie"].isna().any(): st.warning("Falta escolher a pie em algumas linhas.")
            elif (len(sel) or n_up) and st.button(f"Importar {len(sel)} novas" + (f" e atualizar {n_up} existentes" if n_up else ""), type="primary"):
                for _, r in sel.iterrows():
                    S["tx"].append(dict(id=uuid.uuid4().hex[:8], date=r["Data"], tk=r["Ativo"], pie=r["Pie"], type=r["Tipo"], qty=r["Qtd"], price=r["Preço"], cur=r["Moeda"], fx=r["Câmbio €"], bid=r["ID"]))
                    S["fx"].setdefault(r["Moeda"], r["Câmbio €"])
                if upd:
                    for _, r in dups.iterrows():
                        t = next((t for t in S["tx"] if t.get("bid") == r["ID"] or (t["tk"] == r["Ativo"] and t["date"] == r["Data"] and abs(t["qty"] - r["Qtd"]) < 1e-6)), None)
                        if t: t.update(fx=r["Câmbio €"], price=r["Preço"], cur=r["Moeda"], bid=r["ID"])
                save(); st.success("Concluído."); st.rerun()
    with st.expander("💾 Backup e restauro de dados"):
        st.download_button("⬇️ Exportar backup (JSON)", json.dumps(S, ensure_ascii=False), file_name=f"backup_{dt.date.today()}.json", mime="application/json")
        up = st.file_uploader("Carregar ficheiro de dados (JSON)", type="json", key="restore")
        if up:
            new = json.load(up); parts = [k for k in ("tx", "pies", "fx", "ymap", "div", "g", "r", "cats", "inc") if k in new]
            st.info(f"O ficheiro substitui: {', '.join(parts)} (o resto fica como está). Transações: {len(S['tx'])} atuais → {len(new.get('tx', S['tx']))} no ficheiro.")
            if st.checkbox("Já exportei um backup dos dados atuais") and st.button("Substituir dados", type="primary"):
                S.update({k: new[k] for k in parts}); save(); st.success("Dados substituídos."); st.rerun()
    with st.expander("💱 Câmbio de conversão para euros"):
        S.setdefault("fxman", {}); curs = sorted({t["cur"] for t in S["tx"]} - {"EUR"})
        st.caption("O custo (quantidade × preço de compra) e o valor atual são calculados na moeda da ação e convertidos para € ao câmbio atual. É o do Yahoo, ao vivo; aqui podes fixar outro.")
        for cur in curs:
            c = st.columns(3); live = fx_live(cur); c[0].metric(f"{cur}→€ ao vivo (Yahoo)", f"{live:.5f}" if live else "—")
            man = c[1].number_input(f"Câmbio manual {cur}→€ (0 = ao vivo)", min_value=0.0, value=float(S["fxman"].get(cur) or 0), format="%.6f", key=f"man_{cur}")
            if c[2].button("Guardar", key=f"sman_{cur}"):
                (S["fxman"].__setitem__(cur, man) if man > 0 else S["fxman"].pop(cur, None)); save(); st.rerun()

    with st.expander("⚙️ Pies e símbolos do Yahoo"):
        n = st.text_input("Nova pie")
        if st.button("Criar pie") and n and n not in S["pies"]: S["pies"].append(n); save(); st.rerun()
        ym = st.data_editor(pd.DataFrame(sorted({(t["tk"], S["ymap"].get(t["tk"], t["tk"])) for t in S["tx"]}), columns=["Ativo", "Símbolo Yahoo"]), hide_index=True, disabled=["Ativo"])
        if st.button("Guardar símbolos"): S["ymap"] = dict(zip(ym["Ativo"], ym["Símbolo Yahoo"])); save(); st.cache_data.clear(); st.rerun()
    tdf = pd.DataFrame(S["tx"]).sort_values("date", ascending=False); tdf.insert(0, "Apagar", False)
    ed = st.data_editor(tdf.drop(columns=[c for c in ("bid",) if c in tdf]), hide_index=True, disabled=[c for c in tdf.columns if c != "Apagar"], width="stretch")
    if ed["Apagar"].any() and st.button("Apagar selecionadas"):
        S["tx"] = [t for t in S["tx"] if t["id"] not in set(ed[ed["Apagar"]]["id"])]; save(); st.rerun()

# ================= DESPESAS =================
with t3:
    a, b = st.columns(2)
    with a:
        st.subheader("Novo gasto"); x = st.columns(4); gd = x[0].date_input("Data ", key="gd"); gc = x[1].selectbox("Categoria", S["cats"]); gv = x[2].number_input("Valor €", min_value=0.0, step=0.5, key="gv"); gn = x[3].text_input("Nota", key="gn")
        if st.button("Adicionar gasto") and gv > 0: S["g"].append(dict(id=uuid.uuid4().hex[:8], date=str(gd), cat=gc, v=gv, n=gn)); save(); st.rerun()
    with b:
        st.subheader("Nova receita"); x = st.columns(4); rd = x[0].date_input("Data  ", key="rd"); rc = x[1].selectbox("Tipo", S["inc"]); rv = x[2].number_input("Valor €", min_value=0.0, step=0.5, key="rv"); rn = x[3].text_input("Nota", key="rn")
        if st.button("Adicionar receita") and rv > 0: S["r"].append(dict(id=uuid.uuid4().hex[:8], date=str(rd), cat=rc, v=rv, n=rn)); save(); st.rerun()
    y = st.selectbox("Ano", sorted({int(x["date"][:4]) for x in S["g"] + S["r"]} | {dt.date.today().year}), index=0)
    rows = []
    for i, m in enumerate(MES, 1):
        mk = f"{y}-{i:02d}"; g = [x for x in S["g"] if x["date"].startswith(mk)]; ri = sum(x["v"] for x in S["r"] if x["date"].startswith(mk))
        row = {"Mês": m, "Receitas": ri, **{c: sum(x["v"] for x in g if x["cat"] == c) for c in S["cats"]}}
        row["Total gastos"] = sum(x["v"] for x in g); row["Sobra"] = ri - row["Total gastos"]; rows.append(row)
    sm = pd.DataFrame(rows); rec, gas, inv_, sob = sm["Receitas"].sum(), sm["Total gastos"].sum() - sm["Investido"].sum(), sm["Investido"].sum(), sm["Total gastos"].sum()
    k = st.columns(4)
    k[0].markdown(card(f"Receitas {y}", num(rec) + " €", color=UP), unsafe_allow_html=True); k[1].markdown(card("Despesas (sem investido)", num(gas) + " €", color=DN), unsafe_allow_html=True)
    k[2].markdown(card("Investido", num(inv_) + " €", color="#F59E0B"), unsafe_allow_html=True); k[3].markdown(card("Sobra p/ investir", num(rec - sob) + " €", color="#7C5CFF" if rec - sob >= 0 else DN), unsafe_allow_html=True)
    st.dataframe(styler_map(sm.set_index("Mês").style.format("{:.2f}"), pl_style, ["Sobra"]), width="stretch")
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(sm.assign(Despesas=sm["Total gastos"] - sm["Investido"]).melt(id_vars="Mês", value_vars=["Despesas", "Investido"]), x="Mês", y="value", color="variable", barmode="group", title="Despesas vs valor investido por mês", color_discrete_map={"Despesas": DN, "Investido": "#F59E0B"}), width="stretch")
    mes = c2.selectbox("Mês", MES, index=dt.date.today().month - 1); mi = MES.index(mes); cat = sm.iloc[mi][S["cats"]]
    c2.plotly_chart(px.pie(cat[cat > 0].reset_index(name="v"), names="index", values="v", hole=.6, title=f"Gastos de {mes}", color="index", color_discrete_map=CAT_COL), width="stretch")
    for key, lab in (("g", "Gastos"), ("r", "Receitas")):
        L = pd.DataFrame([x for x in S[key] if x["date"].startswith(f"{y}-{mi+1:02d}")]);
        if L.empty: continue
        L.insert(0, "Apagar", False); e = st.data_editor(L, hide_index=True, key="e" + key, disabled=[c for c in L.columns if c != "Apagar"], width="stretch")
        if e["Apagar"].any() and st.button(f"Apagar {lab.lower()} selecionados"):
            S[key] = [x for x in S[key] if x["id"] not in set(e[e["Apagar"]]["id"])]; save(); st.rerun()

with t_day:
    dfa = positions("pie")
    if dfa.empty: st.info("Sem posições abertas.")
    else:
        sym_all = {tk: S["ymap"].get(tk, tk) for tk in set(S["tx"] and [t["tk"] for t in S["tx"]])}
        with st.spinner("A ir buscar as cotações do dia..."): C = closes(tuple(sorted(set(sym_all.values()) | {m for _, m in MKT})))
        if C.empty or len(C) < 3: st.warning("Não consegui obter as cotações do Yahoo agora. Tenta de novo dentro de uns minutos (🔄 Preços).")
        else:
            days = [d_ for d_ in C.index[C.notna().sum(axis=1) >= max(3, C.shape[1] // 3)]][-30:]
            live = days[-1].date() == dt.date.today() and dt.datetime.now(ZoneInfo("Europe/Lisbon")).hour < 22
            opts = [d_.date() for d_ in days[1:]][::-1]
            dsel = st.selectbox("Dia", opts, index=1 if live and len(opts) > 1 else 0, format_func=lambda d_: f"{WD[d_.weekday()]}, {d_.day}/{d_.month}/{d_.year}" + (" (a decorrer)" if d_ == dt.date.today() and live else ""))
            d1 = pd.Timestamp(dsel); d0 = days[days.index(d1) - 1]; cur_of = dict(zip(dfa["Ativo"], dfa["Moeda"])); rows = []
            for (pie, tk), q in qty_before(dsel).items():
                sy = sym_all.get(tk)
                if sy not in C.columns: continue
                c0, c1 = C.at[d0, sy], C.at[d1, sy]; sc = 0.01 if sy.endswith(".L") else 1.0
                if c0 == c0 and c1 == c1 and c0 > 0: rr = rate_of(cur_of.get(tk, "EUR")); rows.append({"Ativo": tk, "Pie": pie, "Var %": (c1 / c0 - 1) * 100, "L/P dia €": q * (c1 - c0) * sc * rr, "Valor antes €": q * c0 * sc * rr})
            D = pd.DataFrame(rows)
            mk = {n: ((C.at[d1, m] / C.at[d0, m] - 1) * 100 if m in C.columns and C.at[d0, m] > 0 else np.nan, C.at[d1, m] if m in C.columns else np.nan) for n, m in MKT}
            if D.empty: st.info("Sem dados para este dia.")
            else:
                P = D["L/P dia €"].sum(); V0 = D["Valor antes €"].sum(); pp = P / V0 * 100 if V0 else 0; T = D.groupby("Ativo").agg(pl=("L/P dia €", "sum"), v0=("Valor antes €", "sum")); T["pct"] = T["pl"] / T["v0"] * 100
                best, worst = T["pct"].idxmax(), T["pct"].idxmin(); sp = mk["S&P 500"][0]; bm = f'<span class="chip nt">S&P 500 {num(sp, 2, True)} %</span>' if sp == sp else ""
                st.markdown(f'<div class="hero"><small>A tua carteira em {dsel.day}/{dsel.month}</small><div class="big">{num(P, 2, True)} €</div>{chip(pp, num(pp, 2, True) + " %")}{bm}'
                    + (f'<span class="chip {"up" if pp - sp >= 0 else "dn"}">{num(pp - sp, 2, True)} p.p. vs S&P 500</span>' if sp == sp else "") + "</div>", unsafe_allow_html=True)
                a, b = st.columns(2)
                a.markdown(card("Maior ganho do dia", f"{best}  {num(T.at[best, 'pct'], 2, True)} %", chip(T.at[best, "pl"], num(T.at[best, "pl"], 2, True) + " €"), UP), unsafe_allow_html=True)
                b.markdown(card("Maior perda do dia", f"{worst}  {num(T.at[worst, 'pct'], 2, True)} %", chip(T.at[worst, "pl"], num(T.at[worst, "pl"], 2, True) + " €"), DN), unsafe_allow_html=True)
                st.markdown("#### Mercado global")
                for i in range(0, len(MKT), 4):
                    for col, (n, m) in zip(st.columns(4), MKT[i:i + 4]):
                        v, lvl = mk[n]; col.markdown(card(n, (num(v, 2, True) + " %") if v == v else "—", f'<span class="chip nt">{num(lvl, 2)}</span>' if lvl == lvl else "", UP if v == v and v >= 0 else DN), unsafe_allow_html=True)
                idx = [mk[n][0] for n in ("S&P 500", "Nasdaq", "Dow Jones", "Euro Stoxx 50", "DAX", "FTSE 100", "Nikkei 225") if mk[n][0] == mk[n][0]]; avg = np.mean(idx) if idx else 0
                tone = "um dia de ganhos generalizados" if avg > 0.4 else "um dia de perdas generalizadas" if avg < -0.4 else "um dia misto, sem direção clara"
                up5, dn5 = T.sort_values("pl", ascending=False).head(3), T.sort_values("pl").head(3); g = lambda df_: ", ".join(f"{k} ({num(r.pct, 1, True)} %, {num(r.pl, 2, True)} €)" for k, r in df_.iterrows())
                pie_d = D.groupby("Pie")["L/P dia €"].sum().sort_values(); narr = (f"**Mercado:** {tone}. S&P 500 {num(mk['S&P 500'][0], 2, True)} %, Nasdaq {num(mk['Nasdaq'][0], 2, True)} %, Euro Stoxx 50 {num(mk['Euro Stoxx 50'][0], 2, True)} %; "
                    f"euro/dólar {num(mk['EUR/USD'][0], 2, True)} %, ouro {num(mk['Ouro'][0], 2, True)} %, petróleo {num(mk['Petróleo WTI'][0], 2, True)} %, VIX {num(mk['VIX (medo)'][0], 1, True)} %.\n\n"
                    f"**Carteira:** {'subiu' if P >= 0 else 'caiu'} {num(abs(pp), 2)} % ({num(P, 2, True)} €). Mais contribuíram: {g(up5)}. Mais pesaram: {g(dn5)}. "
                    f"Por pie, a que mais ganhou foi {pie_d.index[-1]} ({num(pie_d.iloc[-1], 2, True)} €) e a que mais perdeu foi {pie_d.index[0]} ({num(pie_d.iloc[0], 2, True)} €).")
                st.markdown("#### O que aconteceu"); st.markdown(narr)
                hl = {"Mercado": headlines("^GSPC", 5) + headlines("^STOXX50E", 3)}
                for k_ in list(up5.index) + list(dn5.index): hl[k_] = headlines(sym_all.get(k_, k_), 3)
                prompt = (f"Dia de mercado: {dsel}. Escreve em português de Portugal, em 6 a 10 frases, o que moveu os mercados globais nesse dia e porque é que a carteira de um investidor particular subiu ou caiu. "
                    "Usa a pesquisa web para confirmar as causas (Fed, dados económicos, resultados de empresas, geopolítica, matérias-primas). Liga as causas às posições que mais mexeram. Se não souberes a causa, di-lo; não inventes; não dês aconselhamento financeiro.\n\n"
                    f"{narr}\n\nManchetes encontradas:\n" + "\n".join(f"- [{k_}] {t_[0]} ({t_[2]})" for k_, v_ in hl.items() for t_ in v_))
                if has("ANTHROPIC_API_KEY"):
                    if st.button("🤖 Explicar o dia com IA (pesquisa as notícias)"):
                        try:
                            with st.spinner("A pesquisar e a escrever..."): st.session_state[f"ai_{dsel}"] = ai_explain(prompt)
                        except Exception as e: st.error(f"Não consegui gerar a explicação: {str(e)[:160]}")
                    if st.session_state.get(f"ai_{dsel}"): st.info(st.session_state[f"ai_{dsel}"])
                else: st.caption("Para uma explicação escrita por IA com pesquisa de notícias, junta `ANTHROPIC_API_KEY` aos Secrets da app (tem custo por utilização). Sem isso, o resumo acima é gerado só pelos números.")
                c1_, c2_ = st.columns(2); X = T.sort_values("pl"); X = pd.concat([X.head(8), X.tail(8)]).drop_duplicates().reset_index()
                fig = px.bar(X, x="pl", y="Ativo", orientation="h", color=X["pl"] >= 0, color_discrete_map={True: UP, False: DN}, title="Contribuição por ação (€)")
                c1_.plotly_chart(fig.update_layout(showlegend=False, height=420, xaxis_title=None, yaxis_title=None, margin=dict(t=46, b=10), paper_bgcolor="rgba(0,0,0,0)"), width="stretch")
                fig = px.bar(pie_d.reset_index(), x="Pie", y="L/P dia €", color="Pie", color_discrete_map={p: pcol(p) for p in pie_d.index}, title="Contribuição por pie (€)")
                c2_.plotly_chart(fig.update_layout(showlegend=False, height=420, xaxis_title=None, margin=dict(t=46, b=10), paper_bgcolor="rgba(0,0,0,0)"), width="stretch")
                st.markdown("#### Notícias")
                for k_, v_ in hl.items():
                    for t_ in v_: st.markdown(f"- **{k_}** · [{t_[0]}]({t_[1]}) · {t_[2]} {t_[3]}" if t_[1] else f"- **{k_}** · {t_[0]} · {t_[2]}")
                if not any(hl.values()): st.caption("O Yahoo não devolveu notícias agora.")
                with st.expander("Todas as posições neste dia"):
                    st.dataframe(styler_map(T.reset_index().rename(columns={"pl": "L/P €", "pct": "Var %", "v0": "Valor antes €"}).sort_values("L/P €", ascending=False).style.format({"L/P €": "{:+.2f}", "Var %": "{:+.2f}", "Valor antes €": "{:.2f}"}), pl_style, ["L/P €", "Var %"]), hide_index=True, width="stretch")
                st.caption("A variação usa as cotações de fecho do Yahoo, as quantidades que tinhas na véspera e o câmbio atual. Depois do fecho dos EUA (cerca das 21h00 em Lisboa) o dia fica completo.")

with t_div:
    dfa = positions("pie"); pies_d = [p for p in S["pies"] if not dfa.empty and p in set(dfa["Pie"])]
    if dfa.empty: st.info("Sem posições abertas.")
    else:
        pick = st.pills("Pie", ["Todas"] + pies_d, default="Daily Dividend" if "Daily Dividend" in pies_d else "Todas", key="div_pie", label_visibility="collapsed") or "Todas"
        sel = dfa if pick == "Todas" else dfa[dfa["Pie"] == pick]; col = "#6D5BF7" if pick == "Todas" else pcol(pick); today_ts = pd.Timestamp(dt.date.today())
        rec = [x for x in S["div"] if pick == "Todas" or x["pie"] == pick]; recv = lambda x: x["amt"] * rate_of(x["cur"])
        rows, cal = [], np.zeros(12)
        with st.spinner("A ir buscar o histórico de dividendos (a primeira vez demora)..."):
            for _, r in sel.iterrows():
                dv, cur = dps_hist(S["ymap"].get(r["Ativo"], r["Ativo"])); rate = rate_of(cur or r["Moeda"])
                l12 = dv[dv.index >= today_ts - pd.Timedelta(days=365)] if dv is not None else pd.Series(dtype=float)
                inc = r["Qtd"] * float(l12.sum()) * rate
                for d_, a_ in l12.items(): cal[d_.month - 1] += r["Qtd"] * a_ * rate
                mine = [x for x in rec if x["tk"] == r["Ativo"]]
                rows.append({"Ativo": r["Ativo"], "Pie": r["Pie"], "Qtd": r["Qtd"], "Div./ação 12m": float(l12.sum()), "Moeda": cur or r["Moeda"], "Pag./ano": len(l12), "Estimado €/ano": inc,
                    "Yield s/ custo %": inc / r["Custo €"] * 100 if r["Custo €"] else 0, "Yield s/ valor %": inc / r["Valor €"] * 100 if r["Valor €"] else 0,
                    "Recebido €": sum(recv(x) for x in mine), "Último pag.": max((x["date"] for x in mine), default=None)})
        T = pd.DataFrame(rows).sort_values("Estimado €/ano", ascending=False); est = T["Estimado €/ano"].sum(); C, V = sel["Custo €"].sum(), sel["Valor €"].sum()
        y12 = sum(recv(x) for x in rec if x["date"] >= str(dt.date.today() - dt.timedelta(days=365)))
        k = st.columns(4)
        k[0].markdown(card("Rendimento anual estimado", num(est) + " €", f'<span class="chip nt">≈ {num(est / 12)} € / mês</span>', col), unsafe_allow_html=True)
        k[1].markdown(card("Yield sobre o custo", num(est / C * 100 if C else 0) + " %", f'<span class="chip nt">sobre o valor atual: {num(est / V * 100 if V else 0)} %</span>', col), unsafe_allow_html=True)
        k[2].markdown(card("Recebido (total registado)", num(sum(recv(x) for x in rec)) + " €", f'<span class="chip nt">últimos 12 meses: {num(y12)} €</span>', UP), unsafe_allow_html=True)
        k[3].markdown(card("Ativos que pagam", f"{int((T['Pag./ano'] > 0).sum())} de {len(T)}", f'<span class="chip nt">{int(T["Pag./ano"].sum())} pagamentos / ano</span>', "#F59E0B"), unsafe_allow_html=True)
        a, b = st.columns(2); order = [(today_ts.month - 1 + i) % 12 for i in range(12)]
        fig = px.bar(x=[MES[i][:3] for i in order], y=[cal[i] for i in order], title="Calendário estimado (próximos 12 meses, pelo que pagaram no último ano)")
        a.plotly_chart(fig.update_traces(marker_color=col).update_layout(height=320, xaxis_title=None, yaxis_title="€", margin=dict(t=46, b=10), paper_bgcolor="rgba(0,0,0,0)"), width="stretch")
        if rec:
            R = pd.DataFrame([{"Mês": x["date"][:7], "Pie": x["pie"], "€": recv(x)} for x in rec]).groupby(["Mês", "Pie"], as_index=False)["€"].sum()
            fig = px.bar(R, x="Mês", y="€", color="Pie", color_discrete_map={p: pcol(p) for p in R["Pie"].unique()}, title="Dividendos recebidos por mês")
            b.plotly_chart(fig.update_layout(height=320, xaxis_title=None, margin=dict(t=46, b=10), paper_bgcolor="rgba(0,0,0,0)"), width="stretch")
        else: b.info("Ainda não registaste dividendos recebidos. Importa o CSV de dividendos da Trading 212 ou regista à mão (em baixo).")
        td = dt.date.today(); aport, divd = {}, {}
        for t in S["tx"]:
            if t["type"] == "Compra" and (pick == "Todas" or t["pie"] == pick):
                d_ = dt.date.fromisoformat(t["date"]); aport[d_] = aport.get(d_, 0) + t["qty"] * t["price"] * rate_of(t["cur"], t["fx"])
        for x in rec: d_ = dt.date.fromisoformat(x["date"]); divd[d_] = divd.get(d_, 0) + recv(x)
        st.markdown("#### Calendário anual de atividade")
        yrs = sorted({d_.year for d_ in list(aport) + list(divd)} | {td.year}, reverse=True); ysel = st.radio("Ano", yrs, horizontal=True, key="cal_year", label_visibility="collapsed")
        for vals, ttl, lo, hi in ((divd, "Dividendos recebidos", "#BDEBD0", "#0B7A3B"), (aport, "Aportes (todas as compras)", "#D8D2FF", "#4B2FD6")):
            fig, tot, nd, vm = gh_grid(vals, ysel, f"{ttl} em {ysel}", lo, hi); st.plotly_chart(fig, width="stretch", key=f"gh_{ttl}")
            st.caption(f"{num(tot)} € no ano  ·  {nd} dias com atividade  ·  maior dia: {num(vm)} €")
        st.markdown("#### Bola de neve")
        if divd:
            mdiv = pd.Series(divd).groupby(lambda k: pd.Timestamp(k).to_period("M")).sum(); mapo = pd.Series(aport).groupby(lambda k: pd.Timestamp(k).to_period("M")).sum()
            ms = pd.period_range(min(mdiv.index.min(), mapo.index.min() if len(mapo) else mdiv.index.min()), td, freq="M"); mdiv = mdiv.reindex(ms, fill_value=0); mapo = mapo.reindex(ms, fill_value=0)
            lab_ = [str(p) for p in ms]; fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=lab_, y=mdiv.values, name="Dividendos do mês (€)", marker_color=UP), secondary_y=False)
            fig.add_trace(go.Scatter(x=lab_, y=mdiv.cumsum().values, name="Dividendos acumulados (€)", line=dict(color="#14142B", width=3)), secondary_y=True)
            fig.add_trace(go.Scatter(x=lab_, y=mapo.cumsum().values, name="Aportes acumulados (€)", line=dict(color="#7C5CFF", width=2, dash="dot")), secondary_y=True)
            st.plotly_chart(fig.update_layout(height=360, margin=dict(t=30, b=10), legend=dict(orientation="h", y=1.12), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"), width="stretch")
            ta = mapo.sum(); st.caption(f"Já recebeste {num(mdiv.sum())} € em dividendos, {num(mdiv.sum() / ta * 100 if ta else 0)} % do que aportaste ({num(ta)} €).")
        else: st.info("Sem dividendos registados para este gráfico. Importa o CSV da Trading 212 em baixo.")
        st.markdown("#### Yield on cost vs yield atual")
        scope = [t for t in S["tx"] if (t["pie"] in pies_d if pick == "Todas" else t["pie"] == pick)]; dl = sorted((k, v) for k, v in divd.items())
        if len(dl) < 2 or not scope: st.info("Precisas de dividendos registados para este gráfico.")
        else:
            tlY = tl_of("sel:" + pick, scope); first = dl[0][0]; pts = []
            for _, g_ in tlY.groupby(tlY.index.to_period("M")):
                t_ = g_.index[-1].date(); w = min(90, (t_ - first).days + 1)
                if w < 30: continue
                ann = sum(v for k, v in dl if t_ - dt.timedelta(days=w) < k <= t_) * 365 / w; r_ = g_.iloc[-1]
                pts.append((t_, ann / r_["Valor investido"] * 100 if r_["Valor investido"] > 0 else np.nan, ann / r_["Valor atual"] * 100 if r_["Valor atual"] > 0 else np.nan))
            if len(pts) < 2: st.info("Ainda há pouco histórico (menos de 2 meses desde o primeiro dividendo).")
            else:
                P_ = pd.DataFrame(pts, columns=["Data", "Yield on cost", "Yield atual"])
                fig = go.Figure([go.Scatter(x=P_["Data"], y=P_["Yield on cost"], name="Yield on cost (sobre o que investiste)", line=dict(color=col, width=3)), go.Scatter(x=P_["Data"], y=P_["Yield atual"], name="Yield atual (sobre o valor de mercado)", line=dict(color="#94A3B8", width=2, dash="dash"))])
                st.plotly_chart(fig.update_layout(height=340, yaxis=dict(ticksuffix=" %", gridcolor="#E7E5F0"), margin=dict(t=30, b=10), legend=dict(orientation="h", y=1.12), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"), width="stretch")
            st.caption(f"Estimativa a 12 meses (forward): yield on cost {num(est / C * 100 if C else 0)} % · yield atual {num(est / V * 100 if V else 0)} %. Séries calculadas com os dividendos recebidos nos últimos 90 dias, anualizados, a dividir pelo custo e pelo valor de mercado de cada mês. O yield on cost fica acima do yield atual quando os preços subiram desde a compra (e abaixo quando desceram); com o tempo cresce se os dividendos por ação aumentarem ou se reinvestires.")
        sty = T.style.format({"Qtd": "{:.4f}", "Div./ação 12m": "{:.3f}", "Estimado €/ano": "{:.2f}", "Yield s/ custo %": "{:.2f}", "Yield s/ valor %": "{:.2f}", "Recebido €": "{:.2f}"}, na_rep="—")
        sty = styler_map(sty, lambda p: f"color:{pcol(p)};font-weight:700", ["Pie"])
        st.dataframe(sty, hide_index=True, width="stretch", column_config={"Estimado €/ano": st.column_config.ProgressColumn("Estimado €/ano", format="%.2f", min_value=0, max_value=float(max(T["Estimado €/ano"].max(), 0.01)))})
        st.caption("Estimativa = quantidade atual × dividendos pagos nos últimos 12 meses (Yahoo). Não garante pagamentos futuros; ativos sem histórico no Yahoo ficam a zero.")
    with st.expander("➕ Registar ou importar dividendos"):
        up = st.file_uploader("CSV de dividendos (Trading 212 → History → filtrar por Dividends → Export)", type="csv", key="divcsv")
        if up:
            nd = parse_div(up)
            if nd.empty: st.warning("Não encontrei dividendos neste ficheiro.")
            else:
                ed = st.data_editor(nd, hide_index=True, key="div_ed", disabled=[c for c in nd.columns if c not in ("Importar", "Pie")], column_config={"Pie": st.column_config.SelectboxColumn(options=S["pies"])})
                go_ = ed[ed["Importar"] & ed["Pie"].notna()]
                if st.button(f"Importar {len(go_)} dividendos", type="primary") and len(go_):
                    for _, r in go_.iterrows(): S["div"].append(dict(id=r["ID"], date=r["Data"], tk=r["Ativo"], pie=r["Pie"], amt=r["Valor"], cur=r["Moeda"]))
                    save(); st.success("Importado."); st.rerun()
        m = st.columns(5); mtk = m[1].selectbox("Ativo", sorted({t["tk"] for t in S["tx"]}), key="dm_tk"); mdt = m[0].date_input("Data", key="dm_dt")
        pe = pie_of(mtk, str(mdt)); mp = m[2].selectbox("Pie", S["pies"], index=S["pies"].index(pe) if pe in S["pies"] else 0, key=f"dm_p_{mtk}")
        mv = m[3].number_input("Valor recebido", min_value=0.0, step=0.01, format="%.2f", key="dm_v"); mc = m[4].selectbox("Moeda", ["EUR", "USD"], key="dm_c")
        if st.button("Registar dividendo") and mv > 0: S["div"].append(dict(id=uuid.uuid4().hex[:8], date=str(mdt), tk=mtk, pie=mp, amt=mv, cur=mc)); save(); st.rerun()
        if S["div"]:
            L = pd.DataFrame(S["div"]).sort_values("date", ascending=False); L.insert(0, "Apagar", False)
            e = st.data_editor(L, hide_index=True, key="div_list", disabled=[c for c in L.columns if c != "Apagar"], width="stretch")
            if e["Apagar"].any() and st.button("Apagar dividendos selecionados"): S["div"] = [x for x in S["div"] if x["id"] not in set(e[e["Apagar"]]["id"])]; save(); st.rerun()

with t_cal:
    today = dt.date.today(); dfa = positions("pie"); totv = dfa["Valor €"].sum() if not dfa.empty else 0
    usd = dfa[dfa["Moeda"] == "USD"]["Valor €"].sum() / totv * 100 if totv else 0
    f1, f2, f3 = st.columns([3, 2, 2]); KS = ["🏛️ Mercado e bancos centrais", "📊 Resultados", "💰 Dividendos", "🔕 Feriados e expirações"]
    kinds = f1.pills("Tipo", KS, selection_mode="multi", default=KS, label_visibility="collapsed") or []
    horiz = f2.select_slider("Horizonte", [7, 14, 30, 60, 90, 120, 160], value=60, format_func=lambda n: f"{n} dias"); minv = f3.number_input("Mínimo investido por ação (€)", min_value=0.0, value=15.0, step=5.0); end = today + dt.timedelta(days=horiz); ev = []
    for d_, hm, tz, k in MACRO:
        d_ = dt.date.fromisoformat(d_); name = None
        if k.startswith("FERIADO:"): k, name = k.split(":", 1)
        T = TYPES[k]
        if not (today <= d_ <= end) or KS[0 if T["kind"] == "m" else 3] not in kinds: continue
        ev.append(dict(date=d_, time=lisboa(d_, hm, tz) if hm else None, tag=T["tag"], title=name or T["title"], imp=T["imp"], color=T["color"], desc=T["desc"], watch=T["watch"],
            extra=f"Tens {usd:.0f} % da carteira em dólares" if k in ("FOMC", "CPI", "NFP", "ATAS", "BCE") and usd else ""))
    if (KS[1] in kinds or KS[2] in kinds) and not dfa.empty:
        pos = dfa.groupby("Ativo").agg(q=("Qtd", "sum"), v=("Valor €", "sum"), c=("Custo €", "sum")); pos = pos[pos["c"] >= minv]; sym = {t: S["ymap"].get(t, t) for t in pos.index}
        with st.spinner("A ir buscar resultados e dividendos das tuas ações (a primeira vez demora)..."): cal = cal_all(tuple(sorted(set(sym.values()))))
        nf = sum(1 for v in cal.values() if v.get("Earnings Date")); st.caption(f"{len(pos)} ações com pelo menos {num(minv, 0)} € investidos. O Yahoo devolveu data de resultados para {nf}.")
        if len(pos) and not nf: st.warning("O Yahoo não devolveu nenhuma data de resultados (pode estar a limitar pedidos). Tenta de novo dentro de uns minutos com o botão 🔄 Preços.")
        for tk, r in pos.iterrows():
            c = cal.get(sym[tk]) or {}; w = r.v / totv * 100
            ds = [to_date(x) for x in (c.get("Earnings Date") or [])]; ds = [x for x in ds if x and today <= x <= end]
            if ds and KS[1] in kinds:
                eps, rev = c.get("Earnings Average"), c.get("Revenue Average")
                est = (f" Estimativa dos analistas: lucro por ação {eps:.2f}" if eps == eps and eps is not None else "") + (f", receita {rev / 1e9:.2f} mil M." if rev == rev and rev else ".")
                ev.append(dict(date=ds[0], time=None, tag=f"Resultados · {tk}", title=f"{tk} apresenta resultados" + (" (data estimada)" if c.get("_est") else ""), imp=3 if w >= 3 else 2 if w >= 1 else 1, color="#7C5CFF",
                    desc=("Data estimada a partir do último trimestre: a empresa ainda não a confirmou. " if c.get("_est") else "") + "A empresa divulga lucros e receitas do trimestre e, muitas vezes, as previsões para os próximos." + est, watch="A surpresa face ao esperado e as previsões futuras: é aqui que as ações mais saltam (para cima ou para baixo), muitas vezes 5 % a 15 %.", extra=f"Pesa {w:.1f} % da tua carteira"))
            xd = to_date(c.get("Ex-Dividend Date"))
            if xd and today <= xd <= end and KS[2] in kinds:
                dv, cur = dps_hist(sym[tk]); pay = to_date(c.get("Dividend Date")); last = float(dv.iloc[-1]) if dv is not None and len(dv) else 0
                ev.append(dict(date=xd, time=None, tag=f"Dividendo · {tk}", title=f"{tk}: data ex-dividendo", imp=2 if r.v > 0 else 1, color="#F59E0B",
                    desc="Quem tiver a ação antes desta data recebe o próximo dividendo" + (f", pago a {pay.day}/{pay.month}." if pay else ".") + " No dia a ação costuma descer um pouco, o valor do dividendo.",
                    watch="Nada a fazer se já tens a ação. Comprar nesse dia já não dá direito a este dividendo.", extra=f"Estimativa para ti: {num(r.q * last * rate_of(cur or 'USD'))} €" if last else ""))
    ev.sort(key=lambda e: (e["date"], -e["imp"], e["time"] or "")); w7 = [e for e in ev if e["date"] <= today + dt.timedelta(days=7)]
    k = st.columns(3)
    k[0].markdown(card("Próximo evento", ev[0]["title"] if ev else "—", f'<span class="chip nt">{ev[0]["date"].day}/{ev[0]["date"].month}</span>' if ev else "", "#6D5BF7"), unsafe_allow_html=True)
    k[1].markdown(card("Próximos 7 dias", f"{len(w7)} eventos", f'<span class="chip dn">{sum(e["imp"] == 3 for e in w7)} de importância alta</span>', "#E5484D"), unsafe_allow_html=True)
    k[2].markdown(card("Exposição ao dólar", f"{usd:.0f} %", '<span class="chip nt">Fed, inflação e emprego dos EUA mexem no valor em €</span>', "#3B82F6"), unsafe_allow_html=True)
    if not ev: st.info("Sem eventos neste período com os filtros escolhidos.")
    for d_, grp in groupby(ev, key=lambda e: e["date"]):
        n = (d_ - today).days; st.markdown(f"#### {WD[d_.weekday()]}, {d_.day}/{d_.month}/{d_.year}  ·  " + ("hoje" if n == 0 else "amanhã" if n == 1 else f"em {n} dias"))
        for e in grp:
            st.markdown(f'<div class="kc" style="--c:{e["color"]}"><div class="l">{e["tag"]}' + (f' · {e["time"]} (Lisboa)' if e["time"] else "") + f'</div><div class="v" style="font-size:1.1rem">{e["title"]}</div>'
                f'<div style="color:#3D3C5C;font-size:.92rem;margin-top:5px">{e["desc"]}</div><div style="color:#3D3C5C;font-size:.92rem;margin-top:4px"><b>O que observar:</b> {e["watch"]}</div>'
                f'<div style="margin-top:6px"><span class="chip nt">Importância {"alta" if e["imp"] == 3 else "média" if e["imp"] == 2 else "baixa"}</span>' + (f'<span class="chip nt">{e["extra"]}</span>' if e["extra"] else "") + "</div></div>", unsafe_allow_html=True)
    st.caption("Datas oficiais do BLS (inflação e emprego), da Fed e do BCE, confirmadas até abril de 2027; horas convertidas para Lisboa. Resultados e dividendos das tuas ações vêm do Yahoo e podem mudar. O calendário da Fed para 2027 foi revisto em novembro de 2026 (a reunião de outubro de 2027 não terá decisão de juros). Não é aconselhamento financeiro.")

with t_rad:
    dfa = positions("pie")
    if dfa.empty: st.info("Sem posições abertas.")
    else:
        pies_r = [p for p in S["pies"] if p in set(dfa["Pie"])]; pick = st.pills("Pie", ["Todas"] + pies_r, default="Todas", key="rad_pie", label_visibility="collapsed") or "Todas"
        syms = tuple(sorted({S["ymap"].get(t, t) for t in dfa["Ativo"]}))
        with st.spinner("A recolher fundamentais e histórico de preços (a primeira vez demora)..."): F = fund_all(syms); H = closes1y(syms)
        if not any(F.values()): st.warning("O Yahoo não devolveu fundamentais agora (pode estar a limitar pedidos). Tenta de novo dentro de uns minutos com o botão 🔄 Preços.")
        R = {p: radar_scores(dfa[dfa["Pie"] == p], F, H) for p in pies_r}; show = pies_r if pick == "Todas" else [pick]
        fig = go.Figure()
        for p in show:
            sc = R[p]["sc"]; v = [sc[a] if sc[a] is not None else 0 for a in AXES]; c_ = pcol(p).lstrip("#"); rgb = ",".join(str(int(c_[i:i + 2], 16)) for i in (0, 2, 4))
            fig.add_trace(go.Scatterpolar(r=v + v[:1], theta=AXES + AXES[:1], name=p, fill="toself", fillcolor=f"rgba({rgb},{0.30 if len(show) == 1 else 0.12})", line=dict(color=pcol(p), width=3), hovertemplate="%{theta}: %{r:.0f}/100<extra>" + p + "</extra>"))
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], tickvals=[25, 50, 75, 100], gridcolor="#DAD8EA", tickfont=dict(size=10)), angularaxis=dict(tickfont=dict(size=13)), bgcolor="rgba(0,0,0,0)"), height=520, margin=dict(t=30, b=30, l=60, r=60), legend=dict(orientation="h", y=-.08), paper_bgcolor="rgba(0,0,0,0)")
        a, b = st.columns([3, 2]); a.plotly_chart(fig, width="stretch")
        with b:
            for p in show:
                sc = R[p]["sc"]; ok_ = [(x, sc[x]) for x in AXES if sc[x] is not None and R[p]["cv"][x] >= .2]; ok_.sort(key=lambda z: -z[1])
                if len(ok_) >= 3: st.markdown(card(f"Perfil · {p}", f"{ok_[0][0]} e {ok_[1][0]}", f'<span class="chip nt">ponto fraco: {ok_[-1][0]} ({ok_[-1][1]:.0f}/100)</span>', pcol(p)), unsafe_allow_html=True)
            st.caption("Cada eixo vai de 0 a 100 (100 = melhor). Eixos com menos de 20 % do valor com dados ficam a 0 e estão marcados como 'sem dados fiáveis' na tabela.")
        T = pd.DataFrame([{"Pie": p, **{a: R[p]["sc"][a] for a in AXES}} for p in show]).set_index("Pie")
        st.dataframe(T.style.format("{:.0f}", na_rep="—"), width="stretch", column_config={a: st.column_config.ProgressColumn(a, min_value=0, max_value=100, format="%.0f") for a in AXES})
        for p in show:
            with st.expander(f"Detalhe e cobertura · {p}", expanded=len(show) == 1):
                Q = pd.DataFrame([{"Eixo": a, "Pontuação": R[p]["sc"][a], "Medida": R[p]["raw"][a], "Cobertura": f"{R[p]['cv'][a] * 100:.0f} % do valor" + ("" if R[p]["cv"][a] >= .2 else " · sem dados fiáveis")} for a in AXES])
                st.dataframe(Q.style.format({"Pontuação": "{:.0f}"}, na_rep="—"), hide_index=True, width="stretch")
                Dd = R[p]["D"].copy(); Dd["Peso %"] = Dd["w"] * 100
                st.dataframe(Dd[["Ativo", "Peso %", "setor", "gr", "pe", "y", "de", "r12"]].rename(columns={"setor": "Setor", "gr": "Crescimento", "pe": "P/E", "y": "Yield", "de": "Dív./Capitais %", "r12": "Momento 12-1"}).sort_values("Peso %", ascending=False).style.format({"Peso %": "{:.1f}", "Crescimento": "{:+.1%}", "P/E": "{:.1f}", "Yield": "{:.2%}", "Dív./Capitais %": "{:.0f}", "Momento 12-1": "{:+.1%}"}, na_rep="—"), hide_index=True, width="stretch")
        with st.expander("Como cada eixo é calculado"):
            st.markdown("""
| Eixo | Medida | 0 pontos | 100 pontos |
|---|---|---|---|
| **Crescimento** | crescimento anual da receita (60 %) e dos lucros (40 %), limitado a −50 %/+100 % por ação | −10 % | +30 % |
| **Valorização** | P/E da carteira = média **harmónica** ponderada (equivale a 1 ÷ earnings yield médio); usa o P/E futuro, ou o dos últimos 12 meses; empresas sem lucros contam como earnings yield 0 | P/E ≥ 45 | P/E ≤ 10 |
| **Dividendos** | yield médio ponderado: dividendos dos últimos 12 meses ÷ preço | 0 % | 5 % |
| **Solidez financeira** | dívida/capitais próprios (70 %) e rácio de liquidez corrente (30 %); bancos e seguradoras ficam de fora da dívida | D/E ≥ 250 % | D/E ≤ 30 % |
| **Momento** | momento clássico 12−1 meses (ignora o último mês) com 70 %, e distância à média de 200 dias com 30 % | −20 % | +40 % |
| **Diversificação** | posições efetivas 1/Σw² (40 %), setores efetivos (30 %) e correlação média ponderada entre posições nos últimos 12 meses (30 %) | 1 posição, 1 setor, correlação 0,8 | 25 posições, 8 setores, correlação 0,2 |

Todas as médias são ponderadas pelo valor de cada posição, só com as posições que têm dados, e a tabela mostra a cobertura. Os fundamentais vêm do Yahoo Finance (podem estar atrasados ou em falta, sobretudo em ETFs) e são uma fotografia de hoje, não histórico. Não é aconselhamento financeiro.""")

with top:
    b1, b2, b3, _ = st.columns([1.2, 1.4, 1, 4])
    if b1.button("➕ Transação", type="primary", width="stretch"): dlg_add()
    if b2.button("📥 Importar CSV", width="stretch"): dlg_imp()
    if b3.button("🔄 Preços", width="stretch"): st.cache_data.clear(); st.rerun()
