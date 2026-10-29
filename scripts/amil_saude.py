"""
Extrai a rede Amil SAÚDE (plano, cidades e categorias de config/saude_prata_qc.json)
e consolida numa planilha. Independente do fluxo Dental (amil_portable.py).

Uso:
    .\\venv\\Scripts\\python.exe -u scripts/amil_saude.py                 # todas as cidades do config
    .\\venv\\Scripts\\python.exe -u scripts/amil_saude.py --listar        # só mostra o que seria buscado (sem navegador)
    .\\venv\\Scripts\\python.exe -u scripts/amil_saude.py --uf PE --cidade Recife
    .\\venv\\Scripts\\python.exe -u scripts/amil_saude.py --forcar        # refaz cidades já coletadas
    .\\venv\\Scripts\\python.exe -u scripts/amil_saude.py --so-planilha   # só regera a planilha

Saída em documentos/saude/<plano>/:
    cidades/<UF>/<CIDADE>.json   resultado de cada cidade (pula as que já existem)
    rede_saude_<plano>.xlsx      aba Resumo + uma aba por categoria
    logs/execucao.log, logs/bot.log, logs/falhas.json

Com $env:AMIL_JANELA_OCULTA = "1" o Chrome abre fora da tela (igual ao Dental).
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import pandas as pd

from src.scraper.amil_saude import (
    Bloqueio, buscar_plano, coletar_cidade, consolidar, listar_municipios,
    normalizar, planejar_consultas,
)
from src.scraper.anti_bot import preparar_driver_proprio
from src.utils.logger import setup_logger

CONFIG_PADRAO = RAIZ / "config" / "saude_prata_qc.json"

COLUNAS = {
    "uf": "UF", "municipio": "Cidade", "prestador": "Prestador", "bairro": "Bairro",
    "endereco": "Endereço", "cep": "CEP", "telefones": "Telefones", "whatsapp": "WhatsApp",
    "especialidades": "Especialidades", "tipos_servico": "Tipo de serviço",
    "em_descredenciamento": "Em descredenciamento", "codigo_amil": "Código Amil",
}


def _manter_pc_acordado() -> None:
    """Impede o Windows de suspender enquanto este processo roda."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:
        pass


def _slug(texto: str) -> str:
    return normalizar(texto).lower().replace(" ", "_")


def _arquivo_cidade(saida: Path, uf: str, municipio: str) -> Path:
    return saida / "cidades" / uf / (f"{municipio}-{uf}".replace(" ", "_").replace("'", "") + ".json")


def _salvar(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


def _arquivo_parcial(saida: Path, uf: str, municipio: str) -> Path:
    """Respostas brutas já obtidas da cidade — rodar de novo continua da próxima consulta."""
    return saida / "parciais" / _arquivo_cidade(saida, uf, municipio).relative_to(saida / "cidades")


def _ler_parcial(caminho: Path) -> dict:
    if not caminho.exists():
        return {}
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    return {tuple(k.split("|", 1)): v for k, v in bruto.items()}


def _gravar_parcial(caminho: Path, feitas: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps({f"{t}|{e}": v for (t, e), v in feitas.items()}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(caminho)  # troca atômica: um Ctrl+C no meio não corrompe o parcial


def processar_cidade(plano, uf, nome, municipios_uf, categorias, saida, forcar, log, log_bot,
                     limpar_parcial: bool = True) -> bool:
    """
    Coleta uma cidade e grava o JSON. Retorna False se falhou (vai para a 2ª passada).
    forcar: ignora o JSON já coletado; limpar_parcial: com forcar, descarta também o parcial.
    """
    municipio = next((m for m in municipios_uf if normalizar(m) == normalizar(nome)), None)
    base = {"uf": uf, "cidade_config": nome, "plano": plano["nomeDoPlano"],
            "codigo_rede": plano["codigoRede"], "coletado_em": datetime.now().isoformat(timespec="seconds")}

    if not municipio:
        _salvar(_arquivo_cidade(saida, uf, normalizar(nome)),
                {**base, "municipio": normalizar(nome), "status": "SEM REDE NO PLANO",
                 "avisos": [f"'{nome}' não está na lista de municípios do plano no site"], "prestadores": []})
        log.info(f"  {nome}-{uf}: SEM REDE NO PLANO (cidade não aparece no site para {plano['nomeDoPlano']})")
        return True

    arquivo = _arquivo_cidade(saida, uf, municipio)
    if arquivo.exists() and not forcar:
        status = json.loads(arquivo.read_text(encoding="utf-8")).get("status")
        if status in ("OK", "SEM REDE NO PLANO"):
            log.info(f"  {municipio}-{uf}: já coletada ({status}) — pulando (use --forcar para refazer)")
            return True

    consultas, avisos = planejar_consultas(plano["codigoRede"], uf, municipio, categorias)
    if not consultas:
        _salvar(arquivo, {**base, "municipio": municipio, "status": "SEM REDE NO PLANO",
                          "avisos": avisos, "prestadores": []})
        log.info(f"  {municipio}-{uf}: SEM REDE NO PLANO para as categorias pedidas")
        return True

    parcial = _arquivo_parcial(saida, uf, municipio)
    if forcar and limpar_parcial and parcial.exists():
        parcial.unlink()
    feitas = _ler_parcial(parcial)
    feitas = {k: v for k, v in feitas.items() if any((c["tipo"], c["especialidade"]) == k for c in consultas)}
    retomada = f" (retomando: {len(feitas)} já feitas)" if feitas else ""
    log.info(f"  {municipio}-{uf}: {len(consultas)} consultas{retomada}...")
    erro = ""
    for tentativa in range(1, 4):
        try:
            coletar_cidade(plano, uf, municipio, consultas, feitas, logger=log_bot,
                           ao_concluir=lambda f: _gravar_parcial(parcial, f))
            erro = ""
            break
        except Exception as e:
            erro = str(e).splitlines()[0][:150] if str(e) else type(e).__name__
            if tentativa == 3:
                break
            bloqueio = isinstance(e, Bloqueio)
            espera = random.uniform(60, 120) if bloqueio else random.uniform(8, 15)
            log.info(f"    T{tentativa} {'bloqueio Akamai' if bloqueio else 'erro'}: {erro[:80]} — "
                     f"{len(feitas)}/{len(consultas)} feitas, nova tentativa em {espera:.0f}s")
            time.sleep(espera)

    if erro:
        log.info(f"  {municipio}-{uf}: FALHA ({len(feitas)}/{len(consultas)} consultas, "
                 f"parcial guardado): {erro}")
        return False

    linhas, fora = consolidar(uf, municipio, consultas, feitas)
    por_categoria = {c: sum(1 for l in linhas if l["categoria"] == c) for c in categorias}
    _salvar(arquivo, {
        **base, "municipio": municipio, "status": "OK", "avisos": avisos,
        "consultas": [{**c, "total_api": len(feitas[(c["tipo"], c["especialidade"])])} for c in consultas],
        "enderecos_outro_municipio": sum(fora.values()), "outros_municipios": fora, "por_categoria": por_categoria, "prestadores": linhas,
    })
    parcial.unlink(missing_ok=True)
    resumo = ", ".join(f"{c}: {n}" for c, n in por_categoria.items())
    log.info(f"  {municipio}-{uf}: OK — {resumo} (descartados de outro município: {sum(fora.values())})")
    return True


def gerar_planilha(saida: Path, plano_nome: str, categorias: list[str], cidades_config: list[tuple[str, str]]) -> Path:
    """Aba Resumo (cidade x categoria) + uma aba por categoria, a partir dos JSONs das cidades."""
    por_cidade = {}
    for arq in sorted((saida / "cidades").glob("*/*.json")):
        d = json.loads(arq.read_text(encoding="utf-8"))
        por_cidade[(d["uf"], normalizar(d["cidade_config"]))] = d

    resumo, linhas = [], []
    for uf, nome in cidades_config:
        d = por_cidade.get((uf, normalizar(nome)))
        item = {"UF": uf, "Cidade": d["municipio"] if d else normalizar(nome),
                "Status": d["status"] if d else "NÃO COLETADA"}
        for c in categorias:
            item[c] = (d or {}).get("por_categoria", {}).get(c, 0)
        item["Descartados (outro município)"] = (d or {}).get("enderecos_outro_municipio", 0)
        item["Municípios descartados"] = ", ".join(f"{m} ({n})" for m, n in (d or {}).get("outros_municipios", {}).items())
        item["Observações"] = "; ".join((d or {}).get("avisos", []))
        resumo.append(item)
        if d:
            linhas.extend(d.get("prestadores", []))

    destino = saida / f"rede_saude_{_slug(plano_nome)}.xlsx"
    with pd.ExcelWriter(destino, engine="openpyxl") as xw:
        pd.DataFrame(resumo).to_excel(xw, sheet_name="Resumo", index=False)
        for c in categorias:
            df = pd.DataFrame([l for l in linhas if l["categoria"] == c], columns=list(COLUNAS) + ["categoria"])
            df = df.drop(columns="categoria").rename(columns=COLUNAS)
            # "/" não é permitido em nome de aba do Excel
            df.to_excel(xw, sheet_name=c.replace("/", "-")[:31], index=False)
        for ws in xw.book.worksheets:
            ws.auto_filter.ref = ws.dimensions
            ws.freeze_panes = "A2"
            for col in ws.columns:
                largura = max(len(str(cel.value or "")) for cel in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(largura + 2, 8), 60)
    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(CONFIG_PADRAO))
    ap.add_argument("--uf", nargs="*", help="Filtrar UFs (ex.: --uf SP PE)")
    ap.add_argument("--cidade", nargs="*", help="Filtrar cidades (com ou sem acento)")
    ap.add_argument("--forcar", action="store_true", help="Refazer cidades já coletadas")
    ap.add_argument("--listar", action="store_true", help="Só listar as consultas de cada cidade, sem navegador")
    ap.add_argument("--so-planilha", action="store_true", help="Só regerar a planilha a partir dos JSONs")
    ap.add_argument("--pausa", type=float, default=15,
                    help="Minutos de pausa depois de uma cidade falhar (IP marcado pelo Akamai). Padrão: 15")
    args = ap.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    categorias = config["categorias"]
    saida = RAIZ / "documentos" / "saude" / _slug(config["plano"])
    logs = saida / "logs"

    # Cidades do config sem repetição (a planilha original tinha São Paulo duas vezes)
    cidades, vistas = [], set()
    for uf, nomes in config["cidades"].items():
        for nome in nomes:
            if (uf, normalizar(nome)) not in vistas:
                vistas.add((uf, normalizar(nome)))
                cidades.append((uf, nome))

    if args.so_planilha:
        print(f"Planilha: {gerar_planilha(saida, config['plano'], list(categorias), cidades)}")
        return

    filtro_uf = {u.upper() for u in args.uf or []}
    filtro_cid = {normalizar(c) for c in args.cidade or []}
    alvo = [(uf, n) for uf, n in cidades
            if (not filtro_uf or uf in filtro_uf) and (not filtro_cid or normalizar(n) in filtro_cid)]
    if not alvo:
        print("Nenhuma cidade do config bate com os filtros.")
        return

    log = setup_logger("amil_saude", logs / "execucao.log")
    log_bot = setup_logger("amil_saude_bot", logs / "bot.log")
    for h in list(log_bot.handlers):
        if type(h).__name__ == "StreamHandler":
            log_bot.removeHandler(h)  # detalhe do navegador só no arquivo

    plano = buscar_plano(config["plano"])
    log.info("=" * 60)
    log.info(f"AMIL SAÚDE — plano {plano['nomeDoPlano']} (codigoRede {plano['codigoRede']}) — {len(alvo)} cidades")
    log.info("=" * 60)

    municipios: dict[str, list[str]] = {}
    for uf in sorted({uf for uf, _ in alvo}):
        municipios[uf] = listar_municipios(plano["codigoRede"], uf)

    if args.listar:
        for uf, nome in alvo:
            m = next((x for x in municipios[uf] if normalizar(x) == normalizar(nome)), None)
            if not m:
                print(f"{nome}-{uf}: SEM REDE NO PLANO")
                continue
            consultas, avisos = planejar_consultas(plano["codigoRede"], uf, m, categorias)
            print(f"{m}-{uf}: {len(consultas)} consultas")
            for c in consultas:
                print(f"    {c['categoria']:<28} {c['tipo']} / {c['especialidade']}")
            for a in avisos:
                print(f"    aviso: {a}")
        return

    _manter_pc_acordado()
    driver_exe = preparar_driver_proprio("saude")
    if driver_exe:
        os.environ["AMIL_DRIVER_EXE"] = driver_exe

    falhas = []
    for i, (uf, nome) in enumerate(alvo, 1):
        log.info(f"[{i}/{len(alvo)}] {datetime.now():%H:%M} {nome}-{uf}")
        if processar_cidade(plano, uf, nome, municipios[uf], categorias, saida, args.forcar, log, log_bot):
            time.sleep(random.uniform(3, 6))
            continue
        falhas.append((uf, nome))
        # 3 sessões seguidas bloqueadas = IP marcado. Insistir só piora a reputação.
        if i < len(alvo) and args.pausa > 0:
            log.info(f"  Pausa de {args.pausa:.0f} min para o anti-robô esfriar ({datetime.now():%H:%M})...")
            time.sleep(args.pausa * 60)

    if falhas:
        log.info(f"{len(falhas)} cidades falharam. Pausa de {args.pausa:.0f} min antes da 2ª passada...")
        time.sleep(args.pausa * 60)
        # o parcial gravado na 1ª passada é reaproveitado
        falhas = [(uf, n) for uf, n in falhas
                  if not processar_cidade(plano, uf, n, municipios[uf], categorias, saida, args.forcar,
                                          log, log_bot, limpar_parcial=False)]

    logs.mkdir(parents=True, exist_ok=True)
    (logs / "falhas.json").write_text(
        json.dumps([{"uf": uf, "cidade": n} for uf, n in falhas], ensure_ascii=False, indent=1), encoding="utf-8")

    destino = gerar_planilha(saida, config["plano"], list(categorias), cidades)
    log.info("-" * 60)
    log.info(f"Cidades OK: {len(alvo) - len(falhas)}/{len(alvo)}")
    if falhas:
        log.info(f"Falharam: {', '.join(f'{n}-{uf}' for uf, n in falhas)} — rode de novo para tentar só essas.")
    log.info(f"Planilha: {destino}")


if __name__ == "__main__":
    main()
