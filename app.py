import json, os, re, uuid, datetime as dt
import numpy as np, pandas as pd, plotly.express as px, plotly.graph_objects as go, requests, streamlit as st, yfinance as yf
from plotly.subplots import make_subplots

st.set_page_config(page_title="Painel Financeiro", page_icon="📈", layout="wide")
PIE_COL = {"Quantum": "#7C5CFF", "Alone Stocks": "#0FB5A6", "Daily Dividend": "#F59E0B", "ETFs": "#3B82F6"}
CAT_COL = {"Restaurantes": "#F97316", "Supermercado": "#84CC16", "Subscrições": "#A855F7", "Transportes": "#06B6D4", "Lazer": "#EC4899", "Saúde": "#EF4444", "Material Escolar": "#3B82F6", "Investido": "#F59E0B", "Outros": "#94A3B8"}
EXTRA = ["#EC4899", "#84CC16", "#06B6D4", "#F97316", "#A855F7", "#64748B", "#EF4444"]
UP, DN = "#12A150", "#E5484D"
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
html,body,.stApp,[class*="st-"]{font-family:'Manrope',system-ui,sans-serif}
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

def show_tl(txs, title, key, color="#6D5BF7"):
    tl = timeline(txs); win = tl["Valor atual"].iloc[-1] >= tl["Valor investido"].iloc[-1]
    fig = go.Figure([go.Scatter(x=tl.index, y=tl["Valor investido"], name="Investido", line=dict(color="#94A3B8", dash="dot", width=2)),
        go.Scatter(x=tl.index, y=tl["Valor atual"], name="Valor atual", line=dict(color=color, width=3), fill="tonexty", fillcolor="rgba(18,161,80,.16)" if win else "rgba(229,72,77,.16)")])
    fig.update_layout(title=dict(text=title, font=dict(size=15)), height=300, margin=dict(t=46, b=10, l=10, r=10), hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.14, x=1, xanchor="right"), yaxis=dict(gridcolor="#E7E5F0", ticksuffix=" €"), xaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch", key=key)

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
t1, t2, t3 = st.tabs(["Portfólio", "Transações", "Despesas"])

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
        a, b = st.columns([1, 2]); g = df.groupby("Pie")["Valor €"].sum().reset_index()
        fig = px.pie(g, names="Pie", values="Valor €", hole=.62, color="Pie", color_discrete_map={p: pcol(p) for p in g["Pie"]}); fig.update_traces(textinfo="percent", marker_line_width=0)
        a.plotly_chart(fig.update_layout(title="Por pie", height=380, margin=dict(t=46, b=10, l=10, r=10), legend=dict(orientation="h"), paper_bgcolor="rgba(0,0,0,0)"), width="stretch")
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
        show_tl(S["tx"], "Geral (todas as pies)", "tl_all", "#14142B")
        pies_in = [p for p in S["pies"] if any(t["pie"] == p for t in S["tx"])]; cols = st.columns(2)
        for i, p in enumerate(pies_in):
            with cols[i % 2]: show_tl([t for t in S["tx"] if t["pie"] == p], p, f"tl_pie_{p}", pcol(p))
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
            new = json.load(up); parts = [k for k in ("tx", "pies", "fx", "ymap", "g", "r", "cats", "inc") if k in new]
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
    c1.plotly_chart(px.bar(sm.melt(id_vars="Mês", value_vars=["Receitas", "Total gastos"]), x="Mês", y="value", color="variable", barmode="group", title="Receitas vs gastos", color_discrete_map={"Receitas": UP, "Total gastos": DN}), width="stretch")
    mes = c2.selectbox("Mês", MES, index=dt.date.today().month - 1); mi = MES.index(mes); cat = sm.iloc[mi][S["cats"]]
    c2.plotly_chart(px.pie(cat[cat > 0].reset_index(name="v"), names="index", values="v", hole=.6, title=f"Gastos de {mes}", color="index", color_discrete_map=CAT_COL), width="stretch")
    for key, lab in (("g", "Gastos"), ("r", "Receitas")):
        L = pd.DataFrame([x for x in S[key] if x["date"].startswith(f"{y}-{mi+1:02d}")]);
        if L.empty: continue
        L.insert(0, "Apagar", False); e = st.data_editor(L, hide_index=True, key="e" + key, disabled=[c for c in L.columns if c != "Apagar"], width="stretch")
        if e["Apagar"].any() and st.button(f"Apagar {lab.lower()} selecionados"):
            S[key] = [x for x in S[key] if x["id"] not in set(e[e["Apagar"]]["id"])]; save(); st.rerun()

with top:
    b1, b2, b3, _ = st.columns([1.2, 1.4, 1, 4])
    if b1.button("➕ Transação", type="primary", width="stretch"): dlg_add()
    if b2.button("📥 Importar CSV", width="stretch"): dlg_imp()
    if b3.button("🔄 Preços", width="stretch"): st.cache_data.clear(); st.rerun()
