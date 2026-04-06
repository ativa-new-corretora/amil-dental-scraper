import os
import shutil
from pathlib import Path
import pdfkit
from datetime import datetime
import locale

from src.utils.file_manager import (
    SCRIPT_DIR,
    REDE_COMPLETA_DIR,
    get_estado_dir,
    get_pdf_path,
    LOGO_AMIL,
    LOGO_ATIVA,
    TEMPLATES_DIR,
    DOCS_PDFS_DIR,
)

# ---------------------------------------------------------------------
#    CONFIGURAÇÃO DE LOCALIZAÇÃO – GARANTE MÊS EM PORTUGUÊS
# ---------------------------------------------------------------------
try:
    locale.setlocale(locale.LC_TIME, "pt_BR.UTF-8")
except:
    try:
        locale.setlocale(locale.LC_TIME, "pt_BR")
    except:
        pass

# ---------------------------------------------------------------------
#    WKHTMLTOPDF CONFIG
# ---------------------------------------------------------------------
WKHTMLTOPDF_PATH = os.getenv(
    "WKHTMLTOPDF_PATH",
    r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
)

PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)


def _carregar_template(nome_arquivo: str) -> str:
    caminho = TEMPLATES_DIR / nome_arquivo
    with open(caminho, "r", encoding="utf-8") as f:
        return f.read()


# =====================================================================
#                    COPIAR PDF PARA GITHUB PAGES
# =====================================================================
def _copiar_para_github_pages(pdf_path: Path, uf: str) -> None:
    """
    Copia o PDF gerado para a pasta docs/pdfs para GitHub Pages.
    """
    try:
        destino_base = DOCS_PDFS_DIR
        destino_uf = destino_base / uf
        destino_uf.mkdir(parents=True, exist_ok=True)
        
        destino_pdf = destino_uf / pdf_path.name
        
        # Copiar apenas se o arquivo foi modificado ou não existe
        precisa_copiar = True
        if destino_pdf.exists():
            if pdf_path.stat().st_mtime <= destino_pdf.stat().st_mtime:
                precisa_copiar = False
        
        if precisa_copiar:
            shutil.copy2(pdf_path, destino_pdf)
            print(f"📤 PDF copiado para GitHub Pages: {destino_pdf}")
    except Exception as e:
        # Não interrompe o processo se falhar a cópia
        print(f"⚠️  Aviso: não foi possível copiar para GitHub Pages: {e}")


# =====================================================================
#                    GERAR PDF — PRESTADORES
# =====================================================================
def gerar_pdf_prestadores(uf: str,
                          cidade: str,
                          prestadores: list[dict],
                          pasta_base: Path | None = None) -> None:
    """
    Gera o PDF normal com lista de prestadores.
    """
    if pasta_base is None:
        pasta_base = REDE_COMPLETA_DIR

    get_estado_dir(uf, pasta_base)
    pdf_path = get_pdf_path(uf, cidade, pasta_base)

    template = _carregar_template("prestadores.html")

    # LOGOS
    logo_amil = LOGO_AMIL.resolve().as_uri()
    logo_ativa = LOGO_ATIVA.resolve().as_uri()

    # Cabeçalho mês/ano
    hoje = datetime.now()
    mes_ano = hoje.strftime("%B / %Y").capitalize()

    # Gera os blocos dos prestadores
    html_prestadores = []
    for p in prestadores:
        bloco = (
            "<div class='prestador'>"
            f"<strong>Nome:</strong> {p['nome']}<br>"
            f"<strong>Bairro:</strong> {p['bairro']}<br>"
            f"<strong>Endereço:</strong> {p['endereco']}<br>"
            f"<strong>Telefone:</strong> {p['telefone']}"
            "</div>"
        )
        html_prestadores.append(bloco)

    # Insere tudo no template
    html = (
        template
        .replace("{{LOGO_AMIL}}", logo_amil)
        .replace("{{LOGO_ATIVA}}", logo_ativa)
        .replace("{{REFERENCIA}}", mes_ano)
        .replace("{{CIDADE}}", cidade)
        .replace("{{UF}}", uf)
        .replace("{{TOTAL_PRESTADORES}}", str(len(prestadores)))
        .replace("<!--PRESTADORES-->", "\n".join(html_prestadores))
    )

    options_pdf = {"enable-local-file-access": ""}

    pdfkit.from_string(html, str(pdf_path), configuration=PDFKIT_CONFIG, options=options_pdf)
    print(f"✅ PDF salvo: {pdf_path}")
    
    # 🔥 NOVO — Gerar também versão sem telefone simultaneamente
    try:
        gerar_pdf_sem_telefone(uf, cidade, prestadores)
    except Exception as e:
        print(f"⚠️  Aviso: erro ao gerar PDF sem telefone: {e}")
    
    # 🔥 NOVO — copiar automaticamente para GitHub Pages
    _copiar_para_github_pages(pdf_path, uf)


# =====================================================================
#            GERAR PDF — SEM TELEFONE (COM PRESTADORES)
# =====================================================================
def gerar_pdf_sem_telefone(uf: str,
                           cidade: str,
                           prestadores: list[dict]) -> None:
    """
    Gera o PDF sem telefone simultaneamente com o PDF normal.
    Salva em docs/pdfs_sem_telefone.
    """
    # Pasta de destino para PDFs sem telefone
    pasta_destino = SCRIPT_DIR / "docs" / "pdfs_sem_telefone"
    uf_dir = pasta_destino / uf
    uf_dir.mkdir(parents=True, exist_ok=True)
    
    nome_arquivo = f"{cidade}-{uf}".replace(" ", "_")
    pdf_path = uf_dir / f"{nome_arquivo}.pdf"
    
    template = _carregar_template("prestadores.html")
    
    # LOGOS
    logo_amil = LOGO_AMIL.resolve().as_uri()
    logo_ativa = LOGO_ATIVA.resolve().as_uri()
    
    # Cabeçalho mês/ano
    hoje = datetime.now()
    mes_ano = hoje.strftime("%B / %Y").capitalize()
    
    # Gera os blocos dos prestadores SEM TELEFONE
    html_prestadores = []
    for p in prestadores:
        bloco = (
            "<div class='prestador'>"
            f"<strong>Nome:</strong> {p['nome']}<br>"
            f"<strong>Bairro:</strong> {p['bairro']}<br>"
            f"<strong>Endereço:</strong> {p['endereco']}"
            "</div>"
        )
        html_prestadores.append(bloco)
    
    # Insere tudo no template
    html = (
        template
        .replace("{{LOGO_AMIL}}", logo_amil)
        .replace("{{LOGO_ATIVA}}", logo_ativa)
        .replace("{{REFERENCIA}}", mes_ano)
        .replace("{{CIDADE}}", cidade)
        .replace("{{UF}}", uf)
        .replace("{{TOTAL_PRESTADORES}}", str(len(prestadores)))
        .replace("<!--PRESTADORES-->", "\n".join(html_prestadores))
    )
    
    options_pdf = {"enable-local-file-access": ""}
    
    try:
        pdfkit.from_string(html, str(pdf_path), configuration=PDFKIT_CONFIG, options=options_pdf)
        print(f"✅ PDF sem telefone salvo: {pdf_path}")
    except Exception as e:
        print(f"⚠️  Aviso: não foi possível gerar PDF sem telefone: {e}")


# =====================================================================
#            GERAR PDF — SEM TELEFONE (VAZIO - SEM ESPECIALIDADE)
# =====================================================================
def gerar_pdf_sem_telefone_vazio(uf: str, cidade: str) -> None:
    """
    Gera PDF vazio sem telefone (sem especialidade).
    Salva em docs/pdfs_sem_telefone.
    """
    pasta_destino = SCRIPT_DIR / "docs" / "pdfs_sem_telefone"
    uf_dir = pasta_destino / uf
    uf_dir.mkdir(parents=True, exist_ok=True)
    
    nome_arquivo = f"{cidade}-{uf}".replace(" ", "_")
    pdf_path = uf_dir / f"{nome_arquivo}.pdf"
    
    template = _carregar_template("sem_especialidade.html")
    
    # Cabeçalho mês/ano
    hoje = datetime.now()
    mes_ano = hoje.strftime("%B / %Y").capitalize()
    
    html = (
        template
        .replace("{{REFERENCIA}}", mes_ano)
        .replace("{{CIDADE}}", cidade)
        .replace("{{UF}}", uf)
    )
    
    options_pdf = {"enable-local-file-access": ""}
    
    try:
        pdfkit.from_string(html, str(pdf_path), configuration=PDFKIT_CONFIG, options=options_pdf)
        print(f"✅ PDF sem telefone (vazio) salvo: {pdf_path}")
    except Exception as e:
        print(f"⚠️  Aviso: não foi possível gerar PDF sem telefone: {e}")


# =====================================================================
#            GERAR PDF — SEM ESPECIALIDADE
# =====================================================================
def gerar_pdf_sem_especialidade(uf: str,
                                cidade: str,
                                pasta_base: Path | None = None) -> None:
    """
    Gera o PDF para cidades sem CLÍNICA GERAL.
    """
    if pasta_base is None:
        pasta_base = REDE_COMPLETA_DIR

    get_estado_dir(uf, pasta_base)
    pdf_path = get_pdf_path(uf, cidade, pasta_base)

    template = _carregar_template("sem_especialidade.html")

    # Cabeçalho mês/ano
    hoje = datetime.now()
    mes_ano = hoje.strftime("%B / %Y").capitalize()

    html = (
        template
        .replace("{{REFERENCIA}}", mes_ano)
        .replace("{{CIDADE}}", cidade)
        .replace("{{UF}}", uf)
    )

    options_pdf = {"enable-local-file-access": ""}

    pdfkit.from_string(html, str(pdf_path), configuration=PDFKIT_CONFIG, options=options_pdf)
    print(f"⚠️ PDF sem especialidade gerado: {pdf_path}")
    
    # 🔥 NOVO — Gerar também versão sem telefone (vazio)
    try:
        gerar_pdf_sem_telefone_vazio(uf, cidade)
    except Exception as e:
        print(f"⚠️  Aviso: erro ao gerar PDF sem telefone: {e}")
    
    # 🔥 NOVO — copiar automaticamente para GitHub Pages
    _copiar_para_github_pages(pdf_path, uf)