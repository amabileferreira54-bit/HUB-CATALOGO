import os
import glob
import io
import pandas as pd
from PIL import Image
import streamlit as st

# ===== Caminhos fixos no seu PC =====
EXCEL_PATH = r"C:\Users\amabi\OneDrive\Desktop\HUB CATALOGO\ARQUIVO COM DESCRIÇÕES E IMAGENS.xlsx"
IMAGES_DIR = r"C:\Users\amabi\OneDrive\Desktop\HUB CATALOGO\Imagens HUB"

TITLE = "Catálogo HUB 3"
SUBTITLE = "Filtre por descrição."
ALLOWED_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# ---------- Utils ----------
def ensure_folders():
    os.makedirs(IMAGES_DIR, exist_ok=True)

def load_catalog() -> pd.DataFrame:
    if os.path.exists(EXCEL_PATH):
        df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
    else:
        df = pd.DataFrame(columns=["descricao", "quantidade"])

    # Normalizar nomes
    rename_map = {}
    for c in df.columns:
        lc = str(c).strip().lower()
        if lc.startswith("descr"): rename_map[c] = "descricao"
        if "quant" in lc: rename_map[c] = "quantidade"
    if rename_map:
        df = df.rename(columns=rename_map)

    if "descricao" not in df.columns: df["descricao"] = ""
    if "quantidade" not in df.columns: df["quantidade"] = 0

    if "seq" not in df.columns:
        df = df.reset_index(drop=True)
        df["seq"] = df.index + 1

    df["descricao"] = df["descricao"].astype(str)
    df["quantidade"] = pd.to_numeric(df["quantidade"], errors="coerce").fillna(0).astype(int)
    return df.sort_values("seq").reset_index(drop=True)

def save_catalog(df: pd.DataFrame):
    df = df[["seq","descricao","quantidade"]].sort_values("seq")
    df.to_excel(EXCEL_PATH, index=False, engine="openpyxl")

def find_image_path_by_seq(seq: int) -> str | None:
    base = os.path.join(IMAGES_DIR, f"image{seq}")
    for ext in ALLOWED_EXTS:
        p = base + ext
        if os.path.exists(p): return p
    for c in glob.glob(os.path.join(IMAGES_DIR, f"image{seq}.*")):
        if os.path.splitext(c)[1].lower() in ALLOWED_EXTS:
            return c
    return None

def pil_image_from_bytes(file) -> Image.Image:
    data = file.read() if hasattr(file, "read") else file
    return Image.open(io.BytesIO(data)).convert("RGB")

def save_uploaded_image_for_seq(uploaded_file, seq: int) -> str:
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_EXTS: ext = ".jpg"
    save_path = os.path.join(IMAGES_DIR, f"image{seq}{ext}")
    img = pil_image_from_bytes(uploaded_file)
    img.save(save_path, quality=90)
    return save_path

def next_seq(df: pd.DataFrame) -> int:
    return (int(df["seq"].max()) + 1) if len(df) else 1

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
                # sem "#"
                st.markdown(f"**{seq}**")
                if img_path and os.path.exists(img_path):
                    st.image(img_path, use_container_width=True)
                else:
                    st.write("— sem imagem —")
                st.markdown(f"**Descrição:** {r['descricao']}")
                st.markdown(f"**Quantidade:** {r['quantidade']}")
            idx += 1

# ---------- App ----------
st.set_page_config(page_title=TITLE, page_icon="🗂️", layout="wide")
ensure_folders()

# Sidebar agora é apenas para ADICIONAR item
with st.sidebar:
    st.header("➕ Adicionar novo item")
    with st.form("form_add_sidebar"):
        descricao = st.text_input("Descrição*", max_chars=300)
        quantidade = st.number_input("Quantidade*", min_value=0, step=1, value=0)
        uploaded = st.file_uploader("Imagem (JPG/PNG/WEBP)", type=[e.replace(".","") for e in ALLOWED_EXTS])
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

# Filtro no conteúdo principal
st.subheader("🔎 Filtro")
filtro = st.text_input("Filtre por descrição (contém):", placeholder="Digite parte da descrição…", label_visibility="collapsed")
df_view = df if not filtro.strip() else df[df["descricao"].str.contains(filtro, case=False, na=False)]

st.subheader("🗂️ Itens")
catalog_grid(df_view)

st.divider()

# Exportações (mantive no corpo da página)
colx, coly = st.columns(2)
with colx:
    csv_bytes = df[["seq","descricao","quantidade"]].to_csv(index=False).encode("utf-8")
    st.download_button("💾 Baixar CSV (tabela)", data=csv_bytes, file_name="catalogo.csv", mime="text/csv")
with coly:
    bio = io.BytesIO()
    df[["seq","descricao","quantidade"]].to_excel(bio, index=False, engine="openpyxl")
    st.download_button(
        "💾 Baixar Excel (tabela)",
        data=bio.getvalue(),
        file_name="catalogo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
