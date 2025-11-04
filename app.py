import os
import io
import re
import pandas as pd
from PIL import Image
import streamlit as st

# ===== Caminhos do repo (Streamlit Cloud) =====
EXCEL_PATH = "ARQUIVO COM DESCRIÇÕES E IMAGENS.xlsx"   # seu arquivo no repositório
IMAGES_DIR = "."                                       # imagens estão na RAIZ
TITLE = "Catálogo HUB 3"
SUBTITLE = "Filtre por descrição."
ALLOWED_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# ------------------------------------------------------------
# Helpers de arquivo/imagem
# ------------------------------------------------------------
def ensure_folders():
    os.makedirs(IMAGES_DIR, exist_ok=True)

def _normalize_name(s: str) -> str:
    """normaliza para comparação: minúsculo, sem espaços e não-alfanuméricos"""
    return re.sub(r"[^a-z0-9]", "", s.lower())

def _list_images_case_insensitive(folder: str):
    """retorna {nome_arquivo: caminho_completo} para todas as imagens permitidas"""
    out = {}
    if not os.path.isdir(folder):
        return out
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        _, ext = os.path.splitext(name)
        if ext.lower() in ALLOWED_EXTS:
            out[name] = path
    return out

def find_image_path_by_seq(seq: int) -> str | None:
    """
    Procura na RAIZ nomes como:
      - image1.jpg / imagem1.png
      - Imagem1.jpg / Imagem 1.webp
      - image 1.jpeg
    (case-insensitive)
    """
    images = _list_images_case_insensitive(IMAGES_DIR)
    target_keys = []

    # padrões aceitos (sem/ com espaço; "image" ou "imagem")
    patterns = [
        f"image{seq}", f"imagem{seq}",
        f"image {seq}", f"imagem {seq}",
    ]
    # gerar também variações com zero à esquerda? (opcional)
    # patterns += [f"image{seq:02d}", f"imagem{seq:02d}"]

    norm_targets = [_normalize_name(p) for p in patterns]

    for fname, fpath in images.items():
        name_no_ext, _ = os.path.splitext(fname)
        norm_name = _normalize_name(name_no_ext)
        if any(norm_name == t for t in norm_targets):
            return fpath
    return None

def pil_image_from_bytes(file) -> Image.Image:
    data = file.read() if hasattr(file, "read") else file
    return Image.open(io.BytesIO(data)).convert("RGB")

def save_uploaded_image_for_seq(uploaded_file, seq: int) -> str:
    # Salva na RAIZ padronizando para "image{seq}.ext"
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_EXTS:
        ext = ".jpg"
    save_path = os.path.join(IMAGES_DIR, f"image{seq}{ext}")
    img = pil_image_from_bytes(uploaded_file)
    img.save(save_path, quality=90)
    return save_path

# ------------------------------------------------------------
# Leitura robusta do Excel
# ------------------------------------------------------------
def _pick_best_sheet(xl_dict: dict) -> pd.DataFrame:
    """Escolhe a aba com mais linhas não vazias."""
    best_df, best_score = None, -1
    for _, df in xl_dict.items():
        df2 = df.dropna(how="all")
        score = len(df2)
        if score > best_score:
            best_df, best_score = df2.copy(), score
    return best_df if best_df is not None else pd.DataFrame()

def _choose_col(df: pd.DataFrame, candidates):
    """Retorna a primeira coluna encontrada dentro dos 'candidates' (case-insensitive)."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in lower_map:
            return lower_map[cand]
    # tenta startswith
    for c in df.columns:
        lc = c.lower().strip()
        if any(lc.startswith(x) for x in candidates):
            return c
    return None

def load_catalog() -> pd.DataFrame:
    # se não houver Excel no repo, inicia vazio
    if not os.path.exists(EXCEL_PATH):
        return pd.DataFrame(columns=["seq", "descricao", "quantidade"])

    # Lê TODAS as abas e escolhe a "melhor"
    xl = pd.read_excel(EXCEL_PATH, engine="openpyxl", sheet_name=None)
    df_raw = _pick_best_sheet(xl)

    # normaliza header
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    # tenta localizar colunas por variações comuns
    # descrição
    descricao_col = _choose_col(
        df_raw,
        candidates=[
            "descrição", "descricao", "descr", "descri", "descrição do item",
            "item", "produto", "nome"
        ],
    )
    # quantidade
    quantidade_col = _choose_col(
        df_raw,
        candidates=["quantidade", "qtde", "qtd", "qtd.", "quant", "quant."]
    )
    # sequência (se existir)
    seq_col = _choose_col(df_raw, candidates=["seq", "sequencia", "sequência", "ordem", "id"])

    # monta DF final
    out = pd.DataFrame()
    out["descricao"] = df_raw[descricao_col].astype(str) if descricao_col else ""
    if quantidade_col:
        out["quantidade"] = pd.to_numeric(df_raw[quantidade_col], errors="coerce").fillna(0).astype(int)
    else:
        out["quantidade"] = 0

    if seq_col:
        out["seq"] = pd.to_numeric(df_raw[seq_col], errors="coerce").astype("Int64")
    else:
        out = out.reset_index(drop=True)
        out["seq"] = out.index + 1

    # ordena por seq e limpa
    out = out.dropna(subset=["seq"])
    out["seq"] = out["seq"].astype(int)
    out = out.sort_values("seq").reset_index(drop=True)
    return out[["seq", "descricao", "quantidade"]]

def save_catalog(df: pd.DataFrame):
    df = df[["seq", "descricao", "quantidade"]].sort_values("seq")
    df.to_excel(EXCEL_PATH, index=False, engine="openpyxl")

def next_seq(df: pd.DataFrame) -> int:
    return int(df["seq"].max()) + 1 if not df.empty else 1

# ------------------------------------------------------------
# UI — grid
# ------------------------------------------------------------
def catalog_grid(df: pd.DataFrame):
    if df.empty:
        st.info("Nenhum item cadastrado ainda.")
        return
    cols_per_row = 3
    rows = (len(df) + cols_per_row - 1) // cols_per_row
    idx = 0
    for _ in range(rows):
        colz = st.columns(cols_per_row)
        for c in colz:
            if idx >= len(df): break
            r = df.iloc[idx]
            seq = int(r["seq"])
            img_path = find_image_path_by_seq(seq)
            with c:
                st.markdown(f"**{seq}**")  # sem "#"
                if img_path and os.path.exists(img_path):
                    st.image(img_path, use_container_width=True)
                else:
                    st.write("— sem imagem —")
                st.markdown(f"**Descrição:** {r['descricao']}")
                st.markdown(f"**Quantidade:** {r['quantidade']}")
            idx += 1

# ------------------------------------------------------------
# APP
# ------------------------------------------------------------
st.set_page_config(page_title=TITLE, page_icon="🗂️", layout="wide")
ensure_folders()

# Sidebar: apenas para adicionar item
with st.sidebar:
    st.header("➕ Adicionar novo item")
    with st.form("form_add_sidebar"):
        descricao = st.text_input("Descrição*", max_chars=300)
        quantidade = st.number_input("Quantidade*", min_value=0, step=1, value=0)
        uploaded = st.file_uploader("Imagem (JPG/PNG/WEBP)", type=[e.replace(".", "") for e in ALLOWED_EXTS])
        ok = st.form_submit_button("Adicionar")

    if ok:
        if not descricao.strip():
            st.error("Informe a descrição.")
        elif uploaded is None:
            st.error("Envie a imagem do item.")
        else:
            df_tmp = load_catalog()
            seq_new = next_seq(df_tmp)
            try:
                img_path = save_uploaded_image_for_seq(uploaded, seq_new)
                new_row = {"seq": seq_new, "descricao": descricao.strip(), "quantidade": int(quantidade)}
                df_tmp = pd.concat([df_tmp, pd.DataFrame([new_row])], ignore_index=True)
                save_catalog(df_tmp)
                st.success(f"Item {seq_new} adicionado! (imagem: {os.path.basename(img_path)})")
                st.experimental_rerun()
            except Exception as e:
                st.exception(e)
                st.error("Falha ao salvar o item.")

st.title(TITLE)
st.caption(SUBTITLE)

@st.cache_data(show_spinner=False)
def _cached_load():
    return load_catalog()

df = _cached_load().copy()

# Filtro
st.subheader("🔎 Filtro")
filtro = st.text_input(
    "Filtre por descrição (contém):",
    placeholder="Digite parte da descrição…",
    label_visibility="collapsed"
)
df_view = df if not filtro.strip() else df[df["descricao"].str.contains(filtro, case=False, na=False)]

# Grid
st.subheader("🗂️ Itens")
catalog_grid(df_view)

st.divider()

# Exportações
colx, coly = st.columns(2)
with colx:
    csv_bytes = df[["seq", "descricao", "quantidade"]].to_csv(index=False).encode("utf-8")
    st.download_button("💾 Baixar CSV (tabela)", data=csv_bytes, file_name="catalogo.csv", mime="text/csv")
with coly:
    bio = io.BytesIO()
    df[["seq", "descricao", "quantidade"]].to_excel(bio, index=False, engine="openpyxl")
    st.download_button(
        "💾 Baixar Excel (tabela)",
        data=bio.getvalue(),
        file_name="catalogo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# Diagnóstico
with st.expander("🩺 Diagnóstico (clique para abrir)"):
    st.write(f"Linhas carregadas: **{len(df)}**")
    if len(df):
        st.write("Colunas:", list(df.columns))
    st.checkbox("Mostrar tabela bruta", key="show_raw", value=False)
    if st.session_state.get("show_raw"):
        st.dataframe(df, use_container_width=True)
