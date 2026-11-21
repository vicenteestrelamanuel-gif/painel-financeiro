import json, os, re, uuid, datetime as dt
import pandas as pd, plotly.express as px, requests, streamlit as st, yfinance as yf

st.set_page_config(page_title="Painel Financeiro", page_icon="📈", layout="wide")
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

def positions(group):
    m, last = {}, {}
    for t in sorted(S["tx"], key=lambda t: t["date"]):
        last[t["tk"]] = t
        p = m.setdefault((t["pie"] if group == "pie" else "—", t["tk"]), dict(Pie=t["pie"] if group == "pie" else "—", Ativo=t["tk"], Qtd=0.0, Custo=0.0, pies=set()))
        p["pies"].add(t["pie"])
        if t["type"] == "Compra":
            p["Qtd"] += t["qty"]; p["Custo"] += t["qty"] * t["price"] * t["fx"]
        else:
            f = min(1, t["qty"] / p["Qtd"]) if p["Qtd"] > 0 else 0
            p["Custo"] -= p["Custo"] * f; p["Qtd"] -= t["qty"]
    out = []
    for p in m.values():
        if p["Qtd"] <= 1e-9: continue
        l = last[p["Ativo"]]
        price, cur = quote(S["ymap"].get(p["Ativo"], p["Ativo"]))
        live = price is not None
        if not live: price, cur = S["px"].get(p["Ativo"], l["price"]), l["cur"]
        rate = (fx_live(cur) if live else None) or S["fx"].get(cur) or l["fx"]
        val = p["Qtd"] * price * rate
        out.append({"Ativo": p["Ativo"], "Pie": p["Pie"] if group == "pie" else ", ".join(sorted(p["pies"])), "Moeda": cur, "Qtd": p["Qtd"],
            "Preço": price, "Custo €": p["Custo"], "Valor €": val, "L/P €": val - p["Custo"], "L/P %": (val / p["Custo"] - 1) * 100 if p["Custo"] else 0,
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
    """Valor investido (custo acumulado) e valor atual (qtd x preço de fecho x câmbio) por dia útil."""
    days = pd.bdate_range(min(t["date"] for t in txs), dt.date.today())
    inv = pd.Series(0.0, index=days); val = inv.copy(); groups = {}
    for t in sorted(txs, key=lambda t: t["date"]): groups.setdefault((t["pie"], t["tk"]), []).append(t)
    for (pie, tk), L in groups.items():
        q = c = 0.0; ev = {}
        for t in L:
            if t["type"] == "Compra": q += t["qty"]; c += t["qty"] * t["price"] * t["fx"]
            else:
                f = min(1, t["qty"] / q) if q > 0 else 0; c -= c * f; q -= t["qty"]
            ev[pd.Timestamp(t["date"])] = (q, c)
        s = pd.DataFrame(ev, index=["q", "c"]).T
        s = s.reindex(s.index.union(days)).ffill().reindex(days).fillna(0)
        p, cur = hist(S["ymap"].get(tk, tk), L[0]["date"])
        if p is None or p.empty:  # sem histórico: usa os preços das compras
            cur = L[-1]["cur"]; p = pd.Series({pd.Timestamp(t["date"]): t["price"] for t in L}); p = p[~p.index.duplicated(keep="last")]
        p = p.reindex(p.index.union(days)).ffill().bfill().reindex(days)
        if cur == "EUR": r = 1.0
        else:
            fh, _ = hist(f"{cur}EUR=X", L[0]["date"])
            r = fh.reindex(fh.index.union(days)).ffill().bfill().reindex(days) if fh is not None and not fh.empty else (S["fx"].get(cur) or L[-1]["fx"])
        inv += s["c"]; val += s["q"] * p * r
    return pd.DataFrame({"Valor investido": inv, "Valor atual": val})

def show_tl(txs, title, key):
    tl = timeline(txs)
    st.plotly_chart(px.line(tl, title=title).update_layout(yaxis_title="€", xaxis_title=None, legend_title=None), width="stretch", key=key)

def parse_csv(f):
    d = pd.read_csv(f); d = d[d["Action"].str.contains("buy|sell", case=False, na=False)]; rows = []
    for _, x in d.iterrows():
        cur, ex = x["Currency (Price / share)"], x.get("Exchange rate")
        ex = 1.0 if pd.isna(ex) else float(ex)
        tk, qty, date = x["Ticker"], float(x["No. of shares"]), str(x["Time (UTC)"])[:10]
        dup = any(t.get("bid") == x["ID"] or (t["tk"] == tk and t["date"] == date and abs(t["qty"] - qty) < 1e-6) for t in S["tx"])
        known = sorted({t["pie"] for t in S["tx"] if t["tk"] == tk})
        pie = known[0] if len(known) == 1 else ("ETFs" if not known and re.search("ishares|xetra|etf|vanguard|spdr", str(x["Name"]), re.I) else None)
        rows.append({"Importar": not dup, "Pie": pie, "Data": date, "Ativo": tk, "Tipo": "Venda" if "sell" in x["Action"].lower() else "Compra", "Qtd": qty,
            "Preço": float(x["Price / share"]), "Moeda": cur, "Câmbio €": 1.0 if cur == "EUR" else 1 / ex, "ID": x["ID"], "Duplicada": dup})
    return pd.DataFrame(rows)

st.title("📈 Painel Financeiro")
t1, t2, t3 = st.tabs(["Portfólio", "Transações", "Despesas"])

# ================= PORTFÓLIO =================
with t1:
    c1, c2, c3 = st.columns([2, 2, 1])
    grp = c1.selectbox("Vista", ["Separar por pie", "Agregar por ação"])
    pie_f = c2.selectbox("Pie", ["Todas"] + S["pies"]) if grp.startswith("Sep") else "Todas"
    if c3.button("🔄 Atualizar preços"): st.cache_data.clear(); st.rerun()
    df = positions("pie" if grp.startswith("Sep") else "tk")
    if df.empty: st.info("Sem posições.")
    else:
        if pie_f != "Todas": df = df[df["Pie"] == pie_f]
        V, C = df["Valor €"].sum(), df["Custo €"].sum()
        k = st.columns(4); k[0].metric("Valor atual", f"{V:,.2f} €"); k[1].metric("Investido", f"{C:,.2f} €")
        k[2].metric("Lucro/Prejuízo", f"{V-C:,.2f} €"); k[3].metric("Rentabilidade", f"{(V/C-1)*100 if C else 0:+.2f} %")
        a, b = st.columns(2)
        a.plotly_chart(px.pie(df.groupby("Pie")["Valor €"].sum().reset_index(), names="Pie", values="Valor €", hole=.5, title="Por pie"), width="stretch")
        b.plotly_chart(px.bar(df.head(15), x="Ativo", y="L/P €", color="L/P €", color_continuous_scale="RdYlGn", title="Lucro/Prejuízo por posição"), width="stretch")
        st.dataframe(df.style.format({"Qtd": "{:.4f}", "Preço": "{:.2f}", "Custo €": "{:.2f}", "Valor €": "{:.2f}", "L/P €": "{:+.2f}", "L/P %": "{:+.2f}", "Peso %": "{:.1f}"}), hide_index=True, width="stretch")
        st.caption("“ao vivo” = cotação do Yahoo Finance (atualiza de 15 em 15 min); “último preço” = não encontrei o símbolo, uso o último preço de compra. Corrige os símbolos em Transações.")
        st.subheader("Evolução: valor atual vs valor investido")
        base = [t for t in S["tx"] if pie_f == "Todas" or t["pie"] == pie_f]
        tks = sorted({t["tk"] for t in base})
        sel = st.selectbox("Ativo", ["Geral (todas as posições)"] + tks)
        show_tl(base if sel.startswith("Geral") else [t for t in base if t["tk"] == sel], "Geral" if sel.startswith("Geral") else sel, "tl_sel")
        if st.checkbox("Mostrar um gráfico por ativo (mais lento)"):
            cols = st.columns(3)
            for i, tk in enumerate(tks):
                with cols[i % 3]: show_tl([t for t in base if t["tk"] == tk], tk, f"tl_{tk}")

# ================= TRANSAÇÕES =================
with t2:
    with st.expander("➕ Nova transação (manual)"):
        a = st.columns(4); d = a[0].date_input("Data"); tk = a[1].text_input("Ticker").upper().strip(); pie = a[2].selectbox("Pie ", S["pies"]); ty = a[3].selectbox("Tipo", ["Compra", "Venda"])
        b = st.columns(4); qty = b[0].number_input("Quantidade", min_value=0.0, format="%.8f"); pr = b[1].number_input("Preço por ação", min_value=0.0, format="%.4f")
        cur = b[2].selectbox("Moeda", sorted(set(["EUR", "USD", "GBP", "CHF", "CAD"]) | set(S["fx"]))); other = b[2].text_input("Outra moeda (código)").upper().strip(); cur = other or cur
        suggest = S["fx"].get(cur) or fx_live(cur) or 1.0
        fxv = b[3].number_input("1 unidade = ? €", value=float(suggest), format="%.6f", key=f"fx_{cur}")
        if st.button("Guardar transação", type="primary"):
            if tk and qty > 0 and pr > 0 and fxv > 0:
                S["tx"].append(dict(id=uuid.uuid4().hex[:8], date=str(d), tk=tk, pie=pie, type=ty, qty=qty, price=pr, cur=cur, fx=fxv)); S["fx"].setdefault(cur, fxv); save(); st.rerun()
            else: st.warning("Preenche ativo, quantidade, preço e câmbio.")
    with st.expander("📥 Importar CSV (Trading 212)", expanded=True):
        f = st.file_uploader("Ficheiro CSV", type="csv")
        if f:
            imp = parse_csv(f); allp = st.selectbox("Pie para todas as linhas", ["—"] + S["pies"])
            if allp != "—": imp["Pie"] = allp
            ed = st.data_editor(imp, hide_index=True, key=f"imp{allp}", disabled=[c for c in imp.columns if c not in ("Importar", "Pie")],
                column_config={"Pie": st.column_config.SelectboxColumn(options=S["pies"])})
            sel = ed[ed["Importar"]]
            if sel["Pie"].isna().any(): st.warning("Falta escolher a pie em algumas linhas.")
            elif st.button(f"Importar {len(sel)} transações", type="primary") and len(sel):
                for _, r in sel.iterrows():
                    S["tx"].append(dict(id=uuid.uuid4().hex[:8], date=r["Data"], tk=r["Ativo"], pie=r["Pie"], type=r["Tipo"], qty=r["Qtd"], price=r["Preço"], cur=r["Moeda"], fx=r["Câmbio €"], bid=r["ID"]))
                    S["fx"].setdefault(r["Moeda"], r["Câmbio €"])
                save(); st.success("Importado."); st.rerun()
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
    sm = pd.DataFrame(rows); k = st.columns(3)
    k[0].metric("Receitas", f"{sm['Receitas'].sum():,.2f} €"); k[1].metric("Gastos (sem investido)", f"{sm['Total gastos'].sum()-sm['Investido'].sum():,.2f} €"); k[2].metric("Sobra p/ investir", f"{sm['Sobra'].sum():,.2f} €")
    st.dataframe(sm.set_index("Mês").style.format("{:.2f}"), width="stretch")
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(sm.melt(id_vars="Mês", value_vars=["Receitas", "Total gastos"]), x="Mês", y="value", color="variable", barmode="group", title="Receitas vs gastos"), width="stretch")
    mes = c2.selectbox("Mês", MES, index=dt.date.today().month - 1); mi = MES.index(mes); cat = sm.iloc[mi][S["cats"]]
    c2.plotly_chart(px.pie(cat[cat > 0].reset_index(name="v"), names="index", values="v", hole=.5, title=f"Gastos de {mes}"), width="stretch")
    for key, lab in (("g", "Gastos"), ("r", "Receitas")):
        L = pd.DataFrame([x for x in S[key] if x["date"].startswith(f"{y}-{mi+1:02d}")]);
        if L.empty: continue
        L.insert(0, "Apagar", False); e = st.data_editor(L, hide_index=True, key="e" + key, disabled=[c for c in L.columns if c != "Apagar"], width="stretch")
        if e["Apagar"].any() and st.button(f"Apagar {lab.lower()} selecionados"):
            S[key] = [x for x in S[key] if x["id"] not in set(e[e["Apagar"]]["id"])]; save(); st.rerun()
