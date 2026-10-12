"""
Roda o amil_portable.py em N processos paralelos (cada um com seu Chrome),
dividindo as cidades entre eles, e no fim consolida planilha + falhas.

Uso:
    .\\venv\\Scripts\\python.exe scripts/rodar_paralelo.py              # 3 processos
    .\\venv\\Scripts\\python.exe scripts/rodar_paralelo.py --workers 2
    .\\venv\\Scripts\\python.exe scripts/rodar_paralelo.py --estrategico

Qualquer argumento além de --workers é repassado ao amil_portable.py.
Pula cidades que já têm PDF, então pode ser interrompido e rodado de novo.

Acompanhar: documentos/logs/execucao_parte1.log, _parte2.log, ...
Resumo final: documentos/logs/resumo_paralelo.txt

Mais processos = mais rápido, mas o anti-robô da Amil (Akamai) conta por IP:
acima de 3-4 a taxa de bloqueio sobe e o ganho some.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

LOGS = RAIZ / "documentos" / "logs"
SCRIPT = RAIZ / "scripts" / "amil_portable.py"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=3)
    args, repassar = ap.parse_known_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, AMIL_JANELA_OCULTA="1", PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    inicio = datetime.now()
    print(f"{inicio:%H:%M} Iniciando {args.workers} processos...", flush=True)
    procs = []
    for i in range(1, args.workers + 1):
        cmd = [sys.executable, "-u", str(SCRIPT), "--parte", f"{i}/{args.workers}", *repassar]
        procs.append(subprocess.Popen(cmd, env=env, cwd=str(RAIZ), creationflags=flags,
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=open(LOGS / f"erros_parte{i}.log", "a", encoding="utf-8")))
        print(f"  parte {i} -> PID {procs[-1].pid}", flush=True)
        if i < args.workers:
            time.sleep(45)  # não abrir todos os Chrome no mesmo instante

    for i, p in enumerate(procs, start=1):
        p.wait()
        print(f"{datetime.now():%H:%M} parte {i} terminou (código {p.returncode})", flush=True)

    # Consolidar
    from scripts.amil_portable import gerar_planilha_final, PDFS_DIR
    gerar_planilha_final()

    falhas = []
    for f in sorted(LOGS.glob("falhas_parte*.json")):
        falhas += json.loads(f.read_text(encoding="utf-8"))
    total_pdfs = len(list(PDFS_DIR.rglob("*.pdf")))

    resumo = [
        f"Início: {inicio:%d/%m %H:%M}  Fim: {datetime.now():%d/%m %H:%M}",
        f"PDFs em documentos/pdfs: {total_pdfs}",
        f"Cidades que falharam: {len(falhas)}",
        *[f"  - {x['cidade']}-{x['uf']}" for x in falhas],
    ]
    if falhas:
        resumo.append("Rode este script de novo para tentar só as que faltam.")
    (LOGS / "resumo_paralelo.txt").write_text("\n".join(resumo), encoding="utf-8")
    print("\n".join(resumo), flush=True)
    print("FIM_PARALELO", flush=True)


if __name__ == "__main__":
    main()
