"""
Atualiza a referência de data em todos os PDFs existentes.
Relê cada PDF, extrai os prestadores e regenera com a nova data.

Uso:
    python scripts/atualizar_referencia.py                          # usa "Maio / 2026"
    python scripts/atualizar_referencia.py --mes "Junho / 2026"     # referência customizada
    python scripts/atualizar_referencia.py --uf SP RJ               # só esses estados
    python scripts/atualizar_referencia.py --dry-run                # conta, não gera
"""

import os
import sys
import re
import argparse
import pdfkit
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ PyMuPDF não instalado. Execute: pip install PyMuPDF")
    sys.exit(1)

from src.utils.file_manager import LOGO_AMIL, LOGO_ATIVA, TEMPLATES_DIR

# Caminhos de PDFs — usa documentos/ se existir, senão docs/
_pdfs_portable    = SCRIPT_DIR / "documentos" / "pdfs"
_pdfs_main        = SCRIPT_DIR / "docs"       / "pdfs"
PDFS_BASE         = _pdfs_portable if _pdfs_portable.exists() else _pdfs_main

_sem_tel_portable = SCRIPT_DIR / "documentos" / "pdfs_sem_telefone"
_sem_tel_main     = SCRIPT_DIR / "docs"       / "pdfs_sem_telefone"
PDFS_SEM_TEL      = _sem_tel_portable if _sem_tel_portable.exists() else _sem_tel_main

WKHTMLTOPDF_PATH = os.getenv(
    "WKHTMLTOPDF_PATH",
    r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
)
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)

OPTIONS_PDF = {
    "enable-local-file-access": "",
    "encoding": "utf-8",
    "quiet": "",
}


def _carregar_template(nome: str) -> str:
    with open(TEMPLATES_DIR / nome, encoding="utf-8") as f:
        return f.read()


def extrair_prestadores_do_pdf(caminho: Path) -> list[dict] | None:
    """Extrai prestadores de um PDF. Retorna None se for PDF 'sem especialidade'."""
    try:
        doc = fitz.open(caminho)
        texto = "".join(p.get_text() for p in doc)
        doc.close()
    except Exception as e:
        print(f"      ⚠️  Erro ao ler {caminho.name}: {e}")
        return None

    if "não possui a especialidade" in texto.lower():
        return None

    prestadores = []
    for bloco in re.split(r'(?=Nome:\s*)', texto):
        bloco = bloco.strip()
        if not bloco.startswith("Nome:"):
            continue

        def _get(pattern, b=bloco):
            m = re.search(pattern, b, re.DOTALL)
            return " ".join(m.group(1).split()).strip() if m else ""

        nome     = _get(r'Nome:\s*(.+?)(?=\s*(?:Bairro:|Endereço:|Telefone:|Nome:|$))')
        bairro   = _get(r'Bairro:\s*(.+?)(?=\s*(?:Endereço:|Telefone:|Nome:|$))')
        endereco = _get(r'Endereço:\s*(.+?)(?=\s*(?:Telefone:|Nome:|$))')
        telefone = _get(r'Telefone:\s*(.+?)(?=\s*(?:Nome:|$))')

        if nome and len(nome) >= 3:
            prestadores.append({
                "nome": nome,
                "bairro": bairro,
                "endereco": endereco,
                "telefone": telefone,
            })

    return prestadores if prestadores else None


def _html_prestadores(prestadores: list[dict], com_telefone: bool) -> str:
    blocos = []
    for p in prestadores:
        partes = [
            f"<strong>Nome:</strong> {p['nome']}",
            f"<strong>Bairro:</strong> {p['bairro']}",
            f"<strong>Endereço:</strong> {p['endereco']}",
        ]
        if com_telefone:
            partes.append(f"<strong>Telefone:</strong> {p['telefone']}")
        blocos.append("<div class='prestador'>" + "<br>".join(partes) + "</div>")
    return "\n".join(blocos)


def gerar_pdf(uf: str, cidade: str, prestadores: list[dict] | None,
              pasta_normal: Path, pasta_sem_tel: Path, mes: str) -> bool:
    """Gera PDF normal e sem_telefone para uma cidade. Retorna True se bem-sucedido."""
    nome_base = f"{cidade}-{uf}".replace(" ", "_")
    mes_html  = mes.replace("Março", "Mar&ccedil;o")
    logo_amil  = LOGO_AMIL.resolve().as_uri()
    logo_ativa = LOGO_ATIVA.resolve().as_uri()

    # --- PDF sem especialidade (vazio) ---
    if prestadores is None:
        tmpl = _carregar_template("sem_especialidade.html")
        html = (tmpl
                .replace("{{LOGO_AMIL}}", logo_amil)
                .replace("{{LOGO_ATIVA}}", logo_ativa)
                .replace("{{REFERENCIA}}", mes_html)
                .replace("{{CIDADE}}", cidade)
                .replace("{{UF}}", uf))
        for pasta in (pasta_normal, pasta_sem_tel):
            pasta.mkdir(parents=True, exist_ok=True)
            try:
                pdfkit.from_string(html, str(pasta / f"{nome_base}.pdf"),
                                   configuration=PDFKIT_CONFIG, options=OPTIONS_PDF)
            except Exception as e:
                print(f"      ⚠️  Erro ao gerar vazio {nome_base}: {e}")
        return True

    # --- PDF com prestadores ---
    tmpl = _carregar_template("prestadores.html")

    def _gerar_variante(pasta: Path, com_tel: bool) -> bool:
        pasta.mkdir(parents=True, exist_ok=True)
        html = (tmpl
                .replace("{{LOGO_AMIL}}", logo_amil)
                .replace("{{LOGO_ATIVA}}", logo_ativa)
                .replace("{{REFERENCIA}}", mes_html)
                .replace("{{CIDADE}}", cidade)
                .replace("{{UF}}", uf)
                .replace("{{TOTAL_PRESTADORES}}", str(len(prestadores)))
                .replace("<!--PRESTADORES-->", _html_prestadores(prestadores, com_tel)))
        try:
            pdfkit.from_string(html, str(pasta / f"{nome_base}.pdf"),
                               configuration=PDFKIT_CONFIG, options=OPTIONS_PDF)
            return True
        except Exception as e:
            print(f"      ❌ Erro ao gerar {nome_base} ({'c/ tel' if com_tel else 's/ tel'}): {e}")
            return False

    ok = _gerar_variante(pasta_normal, com_tel=True)
    _gerar_variante(pasta_sem_tel, com_tel=False)
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Atualiza referência de data em todos os PDFs existentes"
    )
    parser.add_argument(
        "--mes", default="Maio / 2026",
        help="Nova referência de data (padrão: 'Maio / 2026')"
    )
    parser.add_argument(
        "--uf", nargs="*",
        help="Filtrar por UFs (ex: --uf SP RJ MG)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Apenas conta os PDFs sem gerar novos"
    )
    args = parser.parse_args()

    if not PDFS_BASE.exists():
        print(f"❌ Pasta de PDFs não encontrada: {PDFS_BASE}")
        sys.exit(1)

    filtro_ufs = {u.upper() for u in args.uf} if args.uf else None
    modo = "DRY-RUN" if args.dry_run else f"ATUALIZANDO → '{args.mes}'"

    print("=" * 60)
    print(f"  ATUALIZAR REFERÊNCIA — {modo}")
    print(f"  Fonte:   {PDFS_BASE}")
    print(f"  Destino: {PDFS_BASE}  +  {PDFS_SEM_TEL}")
    print("=" * 60)

    total = erros = pulados = 0

    for uf_dir in sorted(PDFS_BASE.iterdir()):
        if not uf_dir.is_dir():
            continue
        uf = uf_dir.name
        if filtro_ufs and uf not in filtro_ufs:
            continue

        pdfs = sorted(uf_dir.glob("*.pdf"))
        if not pdfs:
            continue

        print(f"\n  [{uf}] — {len(pdfs)} PDFs")

        for pdf in pdfs:
            partes = pdf.stem.rsplit("-", 1)
            if len(partes) != 2:
                print(f"    ⚠️  Nome inválido: {pdf.name}")
                pulados += 1
                continue

            cidade = partes[0].replace("_", " ")
            total += 1

            if args.dry_run:
                continue

            prestadores = extrair_prestadores_do_pdf(pdf)
            n = len(prestadores) if prestadores else 0

            ok = gerar_pdf(uf, cidade, prestadores, uf_dir, PDFS_SEM_TEL / uf, args.mes)

            if ok:
                print(f"    ✅ {cidade} ({n} prestadores)")
            else:
                erros += 1
                print(f"    ❌ Falha em {cidade}")

    print(f"\n{'=' * 60}")
    if args.dry_run:
        print(f"  DRY-RUN: {total} PDFs seriam atualizados.")
        print(f"  Execute sem --dry-run para gerar de verdade.")
    else:
        print(f"  ✅ {total - erros} PDFs atualizados, {erros} erros, {pulados} ignorados.")
    print("=" * 60)


if __name__ == "__main__":
    main()
