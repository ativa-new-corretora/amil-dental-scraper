# -*- coding: utf-8 -*-
"""
Gera PDFs da rede credenciada separados por ZONA da cidade
(Norte, Sul, Leste, Oeste, Centro) a partir dos PDFs por cidade
que ja estao em documentos/pdfs/.

Nao faz scraping — le o PDF que ja existe, reagrupa pelo bairro
e regera. Roda offline em segundos.

Uso:
    # tudo (SAO PAULO e RIO DE JANEIRO)
    .\\venv\\Scripts\\python.exe scripts/gerar_pdfs_por_zona.py

    # so conferir a contagem, sem gerar PDF
    .\\venv\\Scripts\\python.exe scripts/gerar_pdfs_por_zona.py --listar

    # uma cidade so
    .\\venv\\Scripts\\python.exe scripts/gerar_pdfs_por_zona.py --uf SP

    # uma zona so
    .\\venv\\Scripts\\python.exe scripts/gerar_pdfs_por_zona.py --uf RJ --zona "ZONA SUL"

    # incluir as sub-regioes do Rio (Ilha do Governador, Grande Tijuca)
    .\\venv\\Scripts\\python.exe scripts/gerar_pdfs_por_zona.py --sub

O mapa bairro -> zona fica em config/zonas_bairros.json e pode ser
editado a mao. Bairro que nao estiver la cai em "NAO CLASSIFICADO"
e aparece no aviso no fim da execucao.
"""
import argparse
import json
import locale
import os
import re
import shutil
import sys
import unicodedata
from collections import OrderedDict, defaultdict
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
import pdfkit

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CONFIG_ZONAS = RAIZ / "config" / "zonas_bairros.json"
PDFS_ORIGEM = RAIZ / "documentos" / "pdfs"
SAIDA_COM_TEL = RAIZ / "documentos" / "pdfs_por_zona"
SAIDA_SEM_TEL = RAIZ / "documentos" / "pdfs_por_zona_sem_telefone"
DOCS_COM_TEL = RAIZ / "docs" / "pdfs_por_zona"
DOCS_SEM_TEL = RAIZ / "docs" / "pdfs_por_zona_sem_telefone"
TEMPLATES = RAIZ / "src" / "pdf" / "templates"
LOGO_AMIL = RAIZ / "assets" / "amil_dental.jpg"
LOGO_ATIVA = RAIZ / "assets" / "logo_ativa.jpg"

NAO_CLASSIFICADO = "NAO CLASSIFICADO"

WKHTMLTOPDF_PATH = os.getenv(
    "WKHTMLTOPDF_PATH", r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
)
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)

for _loc in ("pt_BR.UTF-8", "pt_BR", "Portuguese_Brazil"):
    try:
        locale.setlocale(locale.LC_TIME, _loc)
        break
    except locale.Error:
        continue


# =====================================================================
#                            UTILIDADES
# =====================================================================
def norm(texto: str) -> str:
    """Maiusculo, sem acento, espacos normalizados — igual as chaves do JSON."""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip().upper()


def slug(texto: str) -> str:
    return norm(texto).replace(" ", "_").replace("/", "-")


def carregar_zonas() -> dict:
    if not CONFIG_ZONAS.exists():
        sys.exit(f"[ERRO] Nao encontrei {CONFIG_ZONAS}")
    with open(CONFIG_ZONAS, encoding="utf-8") as f:
        return json.load(f)


# Nome e endereco podem quebrar em 2 linhas quando sao longos, por isso o
# re.S + o lookahead: cada registro vai ate o proximo "Nome:" ou o fim.
PADRAO_PRESTADOR = re.compile(
    r"Nome:\s*(?P<nome>.+?)\s*\n"
    r"Bairro:\s*(?P<bairro>.+?)\s*\n"
    r"Endere\u00e7o:\s*(?P<endereco>.+?)\s*"
    r"(?:\nTelefone:\s*(?P<telefone>[^\n]*))?"
    r"(?=\nNome:|\s*\Z)",  # \s*\Z: o ultimo registro do PDF termina com \n
    re.S,
)
PADRAO_TOTAL = re.compile(r"(\d+)\s+prestadores encontrados")


def ler_prestadores(pdf_path: Path) -> tuple[list[dict], int | None]:
    """
    Extrai nome / bairro / endereco / telefone do PDF ja gerado.
    Devolve tambem o total anunciado no cabecalho, para conferencia.
    """
    doc = fitz.open(pdf_path)
    texto = "".join(pagina.get_text() for pagina in doc)
    doc.close()

    achado = PADRAO_TOTAL.search(texto)
    total_cabecalho = int(achado.group(1)) if achado else None

    prestadores = [
        {
            "nome": re.sub(r"\s*\n\s*", " ", m.group("nome")).strip(),
            "bairro": re.sub(r"\s*\n\s*", " ", m.group("bairro")).strip(),
            "endereco": re.sub(r"\s*\n\s*", " ", m.group("endereco")).strip(),
            "telefone": (m.group("telefone") or "").strip(),
        }
        for m in PADRAO_PRESTADOR.finditer(texto)
    ]
    return prestadores, total_cabecalho


# =====================================================================
#                          GERACAO DO PDF
# =====================================================================
def gerar_pdf(titulo: str, uf: str, prestadores: list[dict],
              destino: Path, com_telefone: bool) -> None:
    template = (TEMPLATES / "prestadores.html").read_text(encoding="utf-8")

    blocos = []
    for p in prestadores:
        linhas = [
            f"<strong>Nome:</strong> {p['nome']}<br>",
            f"<strong>Bairro:</strong> {p['bairro']}<br>",
            f"<strong>Endereço:</strong> {p['endereco']}",
        ]
        if com_telefone and p["telefone"]:
            linhas.append(f"<br><strong>Telefone:</strong> {p['telefone']}")
        blocos.append("<div class='prestador'>" + "".join(linhas) + "</div>")

    html = (
        template
        .replace("{{LOGO_AMIL}}", LOGO_AMIL.resolve().as_uri())
        .replace("{{LOGO_ATIVA}}", LOGO_ATIVA.resolve().as_uri())
        .replace("{{REFERENCIA}}", datetime.now().strftime("%B / %Y").capitalize())
        .replace("{{CIDADE}}", titulo)
        .replace("{{UF}}", uf)
        .replace("{{TOTAL_PRESTADORES}}", str(len(prestadores)))
        .replace("<!--PRESTADORES-->", "\n".join(blocos))
    )

    destino.parent.mkdir(parents=True, exist_ok=True)
    pdfkit.from_string(html, str(destino), configuration=PDFKIT_CONFIG,
                       options={"enable-local-file-access": ""})


def copiar_para_docs(origem: Path, destino_base: Path, uf: str) -> None:
    """Espelha o PDF em docs/ para o GitHub Pages."""
    try:
        destino = destino_base / uf / origem.name
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)
    except Exception as e:  # nao interrompe o lote
        print(f"   [aviso] nao copiei para docs/: {e}")


# =====================================================================
#                          PROCESSAR CIDADE
# =====================================================================
def processar(cidade: str, uf: str, cfg_cidade: dict, args) -> dict:
    pdf_origem = PDFS_ORIGEM / uf / f"{cidade.replace(' ', '_')}-{uf}.pdf"
    if not pdf_origem.exists():
        print(f"[ERRO] PDF de origem nao existe: {pdf_origem}")
        return {}

    prestadores, total_cabecalho = ler_prestadores(pdf_origem)
    if total_cabecalho is not None and total_cabecalho != len(prestadores):
        print(f"[ATENCAO] {pdf_origem.name}: o cabecalho diz {total_cabecalho} "
              f"prestadores mas extrai {len(prestadores)}. Confira o PDF de origem.")
    mapa = {norm(k): v for k, v in cfg_cidade["bairros"].items()}

    grupos: dict[str, list[dict]] = defaultdict(list)
    bairros_sem_zona: dict[str, int] = defaultdict(int)

    for p in prestadores:
        bairro = norm(p["bairro"])
        zona = mapa.get(bairro)
        if zona is None:
            # tenta de novo sem o sufixo entre parenteses: "TATUAPE (ZONA LESTE)"
            zona = mapa.get(norm(re.sub(r"\(.*?\)", "", bairro)))
        if zona is None:
            zona = NAO_CLASSIFICADO
            bairros_sem_zona[p["bairro"]] += 1
        grupos[zona].append(p)

    # sub-regioes (Ilha do Governador, Grande Tijuca, ...) — grupos extras
    if args.sub:
        for nome_sub, lista in (cfg_cidade.get("sub_regioes") or {}).items():
            alvo = {norm(b) for b in lista}
            sel = [p for p in prestadores if norm(p["bairro"]) in alvo]
            if sel:
                grupos[nome_sub] = sel

    ordem = list(cfg_cidade["zonas"])
    if args.sub:
        ordem += sorted(cfg_cidade.get("sub_regioes") or {})
    ordem.append(NAO_CLASSIFICADO)

    print(f"\n{'=' * 62}")
    print(f"  {cidade}/{uf} — {len(prestadores)} prestadores no PDF de origem")
    print(f"{'=' * 62}")

    gerados = []
    for zona in ordem:
        lista = grupos.get(zona)
        if not lista:
            continue
        if args.zona and norm(args.zona) != norm(zona):
            continue

        lista.sort(key=lambda p: (norm(p["bairro"]), norm(p["nome"])))
        n_bairros = len({norm(p["bairro"]) for p in lista})
        print(f"  {zona:<24} {len(lista):>5} prestadores  ({n_bairros} bairros)")

        if args.listar:
            continue

        nome_base = f"{slug(cidade)}-{uf}-{slug(zona)}.pdf"
        titulo = f"{cidade} — {zona}"

        com = SAIDA_COM_TEL / uf / nome_base
        gerar_pdf(titulo, uf, lista, com, com_telefone=True)
        copiar_para_docs(com, DOCS_COM_TEL, uf)

        sem = SAIDA_SEM_TEL / uf / nome_base
        gerar_pdf(titulo, uf, lista, sem, com_telefone=False)
        copiar_para_docs(sem, DOCS_SEM_TEL, uf)

        gerados.append(com)

    total_agrupado = sum(len(v) for k, v in grupos.items()
                         if k in cfg_cidade["zonas"] or k == NAO_CLASSIFICADO)
    if total_agrupado != len(prestadores):
        print(f"  [ATENCAO] {total_agrupado} agrupados x {len(prestadores)} lidos")

    if bairros_sem_zona:
        print(f"\n  Bairros SEM zona no config ({len(bairros_sem_zona)}) — "
              f"adicione em {CONFIG_ZONAS.relative_to(RAIZ)}:")
        for b, n in sorted(bairros_sem_zona.items(), key=lambda kv: -kv[1]):
            print(f"     {n:>4}x  {b}")

    if gerados:
        print(f"\n  {len(gerados)} PDFs em {SAIDA_COM_TEL.relative_to(RAIZ)}/{uf}/")
        print(f"  {len(gerados)} PDFs em {SAIDA_SEM_TEL.relative_to(RAIZ)}/{uf}/")

    return grupos


# =====================================================================
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Gera PDFs da rede credenciada separados por zona da cidade."
    )
    ap.add_argument("--uf", nargs="+", help="Filtra por UF (ex.: SP RJ)")
    ap.add_argument("--cidade", help="Filtra por cidade (ex.: 'SAO PAULO')")
    ap.add_argument("--zona", help="Gera so uma zona (ex.: 'ZONA SUL')")
    ap.add_argument("--sub", action="store_true",
                    help="Gera tambem as sub-regioes (Ilha do Governador etc.)")
    ap.add_argument("--listar", action="store_true",
                    help="So mostra a contagem por zona, nao gera PDF")
    args = ap.parse_args()

    cfg = carregar_zonas()
    alvos = []
    for chave, dados in cfg.items():
        if chave.startswith("_"):
            continue
        cidade, uf = chave.rsplit("/", 1)
        if args.uf and uf.upper() not in [u.upper() for u in args.uf]:
            continue
        if args.cidade and norm(args.cidade) != norm(cidade):
            continue
        alvos.append((cidade, uf, dados))

    if not alvos:
        sys.exit("[ERRO] Nenhuma cidade bate com os filtros. "
                 f"Disponiveis: {[k for k in cfg if not k.startswith('_')]}")

    for cidade, uf, dados in alvos:
        processar(cidade, uf, dados, args)

    if not args.listar:
        print(f"\nPronto. Copia para GitHub Pages em "
              f"{DOCS_COM_TEL.relative_to(RAIZ)}/ e {DOCS_SEM_TEL.relative_to(RAIZ)}/")


if __name__ == "__main__":
    main()
