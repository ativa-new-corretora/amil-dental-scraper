"""
Limpa PDFs de cidades que não existem mais no JSON da Amil.

Uso:
    python scripts/limpar_pdfs_obsoletos.py           # lista o que seria deletado (dry-run)
    python scripts/limpar_pdfs_obsoletos.py --deletar  # deleta de verdade
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent.parent
JSON_PATH  = SCRIPT_DIR / "config" / "estados_cidades_amil.json"

# Detecta a pasta de PDFs usada (portátil ou main.py)
_pdfs_portable = SCRIPT_DIR / "documentos" / "pdfs"
_pdfs_main     = SCRIPT_DIR / "docs"       / "pdfs"
PDFS_BASE      = _pdfs_portable if _pdfs_portable.exists() else _pdfs_main

_sem_tel_portable = SCRIPT_DIR / "documentos" / "pdfs_sem_telefone"
_sem_tel_main     = SCRIPT_DIR / "docs"       / "pdfs_sem_telefone"
PDFS_SEM_TEL      = _sem_tel_portable if _sem_tel_portable.exists() else _sem_tel_main


def carregar_json() -> set[tuple[str, str]]:
    with open(JSON_PATH, encoding="utf-8") as f:
        dados = json.load(f)
    return {
        (uf.strip().upper(), cidade.strip().upper())
        for uf, cidades in dados.items()
        for cidade in cidades
    }


def listar_pdfs(pasta: Path) -> list[Path]:
    if not pasta.exists():
        return []
    return list(pasta.rglob("*.pdf"))


def pdf_para_chave(pdf: Path) -> tuple[str, str] | None:
    """Converte path do PDF em (UF, CIDADE). Retorna None se o nome for inválido."""
    nome = pdf.stem  # ex: SAO_PAULO-SP
    if "-" not in nome:
        return None
    partes = nome.rsplit("-", 1)
    if len(partes) != 2:
        return None
    cidade = partes[0].replace("_", " ").strip().upper()
    uf     = partes[1].strip().upper()
    return (uf, cidade)


def main():
    parser = argparse.ArgumentParser(description="Limpa PDFs de cidades removidas do JSON")
    parser.add_argument("--deletar", action="store_true",
                        help="Deleta os arquivos. Sem essa flag, apenas lista (dry-run).")
    args = parser.parse_args()

    if not JSON_PATH.exists():
        print(f"❌ JSON não encontrado: {JSON_PATH}")
        sys.exit(1)

    cidades_validas = carregar_json()
    print(f"📋 Cidades no JSON atual: {len(cidades_validas)}")

    pastas = [(PDFS_BASE, "pdfs"), (PDFS_SEM_TEL, "pdfs_sem_telefone")]

    total_obsoletos = 0
    obsoletos: list[Path] = []

    for pasta, nome in pastas:
        pdfs = listar_pdfs(pasta)
        for pdf in pdfs:
            chave = pdf_para_chave(pdf)
            if chave is None:
                continue
            if chave not in cidades_validas:
                obsoletos.append(pdf)
                total_obsoletos += 1

    if total_obsoletos == 0:
        print("✅ Nenhum PDF obsoleto encontrado. Tudo em dia!")
        return

    # Agrupar por UF para exibição
    por_uf: dict[str, list[Path]] = {}
    for pdf in sorted(obsoletos):
        chave = pdf_para_chave(pdf)
        uf = chave[1] if chave else "?"  # chave = (UF, CIDADE) mas UF é index 0
        chave2 = pdf_para_chave(pdf)
        uf2 = chave2[0] if chave2 else "?"
        por_uf.setdefault(uf2, []).append(pdf)

    modo = "DELETANDO" if args.deletar else "DRY-RUN (use --deletar para apagar de verdade)"
    print(f"\n{'='*60}")
    print(f"  PDFs OBSOLETOS — {modo}")
    print(f"{'='*60}")
    print(f"  Total: {total_obsoletos} arquivos\n")

    deletados = 0
    erros = 0

    for uf in sorted(por_uf):
        print(f"  [{uf}]")
        for pdf in por_uf[uf]:
            chave = pdf_para_chave(pdf)
            cidade = chave[1] if chave else pdf.stem
            print(f"    - {cidade}")
            if args.deletar:
                try:
                    pdf.unlink()
                    deletados += 1
                except Exception as e:
                    print(f"      ⚠️ Erro: {e}")
                    erros += 1

    print(f"\n{'='*60}")
    if args.deletar:
        print(f"  ✅ {deletados} PDFs deletados, {erros} erros.")
    else:
        print(f"  ℹ️  Nenhum arquivo foi deletado (dry-run).")
        print(f"  Execute com --deletar para apagar os {total_obsoletos} arquivos listados.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
