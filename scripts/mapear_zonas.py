# -*- coding: utf-8 -*-
"""
Manutencao do config/zonas_bairros.json.

Compara os bairros que aparecem nos PDFs por cidade com o que ja esta
mapeado no config e, para os que faltam, sugere a zona consultando o
CEP no ViaCEP a partir do endereco real do prestador.

Rodar depois da atualizacao mensal, ANTES de gerar_pdfs_por_zona.py.

Uso:
    # so mostra o que falta e a sugestao (nao altera nada)
    .\\venv\\Scripts\\python.exe scripts/mapear_zonas.py

    # grava as sugestoes no config
    .\\venv\\Scripts\\python.exe scripts/mapear_zonas.py --aplicar

Atencao: no RIO a sugestao automatica NAO e confiavel — o CEP carioca nao
acompanha as zonas (Realengo, Bangu e Praca Seca ficam na faixa 21xxx, que
e "Zona Norte" pelos Correios, mas sao Zona Oeste / Jacarepagua). Para o RJ
o script apenas lista os bairros novos para voce classificar a mao.
"""
import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import OrderedDict, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scripts.gerar_pdfs_por_zona import (  # noqa: E402
    CONFIG_ZONAS,
    PDFS_ORIGEM,
    ler_prestadores,
    norm,
)

# Faixas de CEP da capital paulista -> zona. Mesmas regras registradas
# em config/zonas_bairros.json > "SAO PAULO/SP" > "regra_cep".
FAIXAS_SP = [
    (1000000, 1399999, "CENTRO"),
    (1400000, 1499999, "ZONA SUL"),
    (1500000, 1599999, "CENTRO"),
    (2000000, 2999999, "ZONA NORTE"),
    (3000000, 3999999, "ZONA LESTE"),
    (4000000, 4999999, "ZONA SUL"),
    (5000000, 5649999, "ZONA OESTE"),
    (5650000, 5899999, "ZONA SUL"),
    (8000000, 8499999, "ZONA LESTE"),
]

TIPOS_LOGRADOURO = {
    "R", "RUA", "AV", "AVE", "AVENIDA", "AL", "ALAMEDA", "PC", "PCA", "PRACA",
    "TV", "TRV", "TRAVESSA", "EST", "ESTR", "ESTRADA", "ROD", "RODOVIA",
    "PRQ", "PARQUE", "LGO", "LARGO", "VL", "VLA", "VIELA", "VIA", "PSG",
    "PASSAGEM", "MRO", "ACS", "COND", "CJ", "JD", "SIT", "CH",
}

_cache_viacep: dict = {}


def zona_por_cep_sp(cep: str):
    n = int(cep[:5] + "000")
    for ini, fim, z in FAIXAS_SP:
        if ini <= n <= fim:
            return z
    return None


def logradouro_de(endereco: str) -> str:
    partes = norm(endereco.split(",")[0]).split()
    while partes and partes[0] in TIPOS_LOGRADOURO:
        partes = partes[1:]
    while partes and partes[-1].isdigit():
        partes = partes[:-1]
    return " ".join(partes)


def viacep(uf: str, cidade: str, logradouro: str) -> list:
    chave = (uf, cidade, logradouro)
    if chave in _cache_viacep:
        return _cache_viacep[chave]
    url = "https://viacep.com.br/ws/{}/{}/{}/json/".format(
        uf, urllib.parse.quote(cidade), urllib.parse.quote(logradouro)
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            dados = json.loads(r.read().decode("utf-8"))
        dados = dados if isinstance(dados, list) else []
    except Exception as e:
        print(f"   [aviso] ViaCEP falhou para '{logradouro}': {e}")
        dados = []
    _cache_viacep[chave] = dados
    time.sleep(0.12)
    return dados


def sugerir_zona(uf: str, cidade: str, bairro: str, prestadores: list):
    """Descobre o CEP do bairro pelo endereco dos prestadores e deriva a zona."""
    if uf != "SP":
        return None, []  # so a capital paulista tem regra de CEP confiavel

    alvo = norm(re.sub(r"\(.*?\)", "", bairro))
    ceps, tentativas = [], 0
    for p in prestadores:
        if tentativas >= 6 or len(ceps) >= 3:
            break
        lg = logradouro_de(p["endereco"])
        if len(lg) < 4:
            continue
        tentativas += 1
        for item in viacep(uf, cidade, lg):
            achado = norm(re.sub(r"\(.*?\)", "", item.get("bairro", "")))
            if achado == alvo:
                ceps.append(item["cep"].replace("-", ""))

    zonas = [z for z in (zona_por_cep_sp(c) for c in ceps) if z]
    if not zonas:
        return None, ceps
    return max(set(zonas), key=zonas.count), sorted(set(ceps))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true",
                    help="Grava as sugestoes em config/zonas_bairros.json")
    args = ap.parse_args()

    cfg = json.loads(CONFIG_ZONAS.read_text(encoding="utf-8"))
    houve_mudanca = False
    pendencias_manuais = []

    for chave, dados in cfg.items():
        if chave.startswith("_"):
            continue
        cidade, uf = chave.rsplit("/", 1)
        pdf = PDFS_ORIGEM / uf / f"{cidade.replace(' ', '_')}-{uf}.pdf"
        if not pdf.exists():
            print(f"[pulando] PDF nao encontrado: {pdf}")
            continue

        prestadores, _ = ler_prestadores(pdf)
        mapeados = {norm(b) for b in dados["bairros"]}

        novos = defaultdict(list)
        for p in prestadores:
            b = norm(p["bairro"])
            if b not in mapeados and norm(re.sub(r"\(.*?\)", "", b)) not in mapeados:
                novos[b].append(p)

        print(f"\n=== {chave} — {len(dados['bairros'])} bairros mapeados, "
              f"{len(novos)} novos ===")
        if not novos:
            print("   nada a fazer.")
            continue

        for bairro, lista in sorted(novos.items()):
            zona, ceps = sugerir_zona(uf, cidade, bairro, lista)
            if zona:
                print(f"   {bairro:<45} -> {zona:<12} "
                      f"(CEP {ceps[0] if ceps else '?'}, {len(lista)} prest.)")
                if args.aplicar:
                    dados["bairros"][bairro] = zona
                    houve_mudanca = True
            else:
                print(f"   {bairro:<45} -> ??? CLASSIFICAR A MAO "
                      f"({len(lista)} prest.)")
                pendencias_manuais.append((chave, bairro, len(lista),
                                           lista[0]["endereco"]))

        if args.aplicar:
            dados["bairros"] = OrderedDict(sorted(dados["bairros"].items()))

    if pendencias_manuais:
        print(f"\n{'!' * 62}")
        print(f"  {len(pendencias_manuais)} bairro(s) para classificar a mao em "
              f"{CONFIG_ZONAS.relative_to(RAIZ)}:")
        for chave, bairro, n, exemplo in pendencias_manuais:
            print(f"   [{chave}] {bairro} ({n} prest.) — ex.: {exemplo}")
        print(f"{'!' * 62}")

    if args.aplicar and houve_mudanca:
        CONFIG_ZONAS.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nConfig atualizado: {CONFIG_ZONAS.relative_to(RAIZ)}")
    elif not args.aplicar:
        print("\n(dry-run — rode com --aplicar para gravar no config)")


if __name__ == "__main__":
    main()
