"""
Roda o rodar_paralelo.py em ciclos até não faltar nenhuma cidade.

Quando o anti-robô da Amil (Akamai) passa a recusar quase tudo — das últimas
8 tentativas no máximo 1 deu certo —, para todos os processos, espera o IP
"esfriar" e retoma. Cidades que já têm PDF são puladas, então cada ciclo só
continua de onde o anterior parou.

Uso:
    .\\venv\\Scripts\\python.exe -u scripts/rodar_em_ciclos.py
    .\\venv\\Scripts\\python.exe -u scripts/rodar_em_ciclos.py --workers 2 --pausa 45
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DOC = RAIZ / "documentos"
LOGS = DOC / "logs"
JSON_CIDADES = RAIZ / "config" / "estados_cidades_amil.json"


def agora() -> str:
    return datetime.now().strftime("%H:%M")


def faltando() -> list[str]:
    mapa = json.loads(JSON_CIDADES.read_text(encoding="utf-8"))
    return [
        f"{c}-{uf}" for uf, cidades in mapa.items() for c in cidades
        if not (DOC / "pdfs" / uf / (f"{c}-{uf}".replace(" ", "_") + ".pdf")).exists()
    ]


def matar_tudo() -> None:
    """Encerra os processos do scraper e os Chrome ocultos — só os nossos."""
    filtro = ("$_.CommandLine -like '*amil_portable*' -or $_.CommandLine -like '*rodar_paralelo*' "
              "-or $_.CommandLine -like '*window-position=-32000*' -or $_.Name -like 'chromedriver_parte*'")
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"Get-CimInstance Win32_Process | Where-Object {{ {filtro} }} | "
         "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--pausa", type=int, default=45, help="minutos de espera quando o bloqueio dispara")
    ap.add_argument("--espera-inicial", type=int, default=0, help="minutos para esperar antes do 1º ciclo")
    args = ap.parse_args()

    total = sum(len(c) for c in json.loads(JSON_CIDADES.read_text(encoding="utf-8")).values())
    if args.espera_inicial:
        print(f"{agora()} esperando {args.espera_inicial} min antes de começar (IP esfriando)", flush=True)
        time.sleep(args.espera_inicial * 60)

    ciclo = 0
    while True:
        falta = faltando()
        if not falta:
            break
        ciclo += 1
        print(f"{agora()} CICLO {ciclo}: faltam {len(falta)} cidades — subindo {args.workers} processos", flush=True)

        logs = [LOGS / f"execucao_parte{i}.log" for i in range(1, args.workers + 1)]
        inicio = {f: (f.stat().st_size if f.exists() else 0) for f in logs}
        proc = subprocess.Popen(
            [sys.executable, "-u", str(RAIZ / "scripts" / "rodar_paralelo.py"), "--workers", str(args.workers)],
            cwd=str(RAIZ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        bloqueou = False
        while proc.poll() is None:
            time.sleep(60)
            eventos = []
            for f in logs:
                if f.exists():
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        fh.seek(inicio[f])
                        eventos += re.findall(r"OK \(|shadow block", fh.read())
            ok = eventos.count("OK (")
            ultimos = eventos[-8:]
            if len(ultimos) == 8 and ultimos.count("OK (") <= 1:
                print(f"{agora()} bloqueio alto (OK neste ciclo: {ok}; últimas 8 tentativas: "
                      f"{ultimos.count('OK (')} OK) — pausando {args.pausa} min", flush=True)
                matar_tudo()
                bloqueou = True
                break

        if not bloqueou:
            print(f"{agora()} ciclo {ciclo} terminou sozinho", flush=True)
        print(f"{agora()} PDFs: {total - len(faltando())}/{total}", flush=True)
        if bloqueou:
            time.sleep(args.pausa * 60)

    matar_tudo()
    sys.path.insert(0, str(RAIZ))
    from scripts.amil_portable import gerar_planilha_final
    gerar_planilha_final()
    print(f"{agora()} FIM: todas as cidades têm PDF; planilha regerada.", flush=True)


if __name__ == "__main__":
    main()
