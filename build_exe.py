import PyInstaller.__main__
import os
import sys
from pathlib import Path

# Raiz do projeto
ROOT = Path(__file__).resolve().parent

# Arquivo principal
SCRIPT = ROOT / "scripts" / "amil_portable.py"

# Configurações de dados extras (formato: "origem;destino")
# No Windows usa ";" no Linux ":"
SEP = ";" if sys.platform == "win32" else ":"

ADD_DATA = [
    f"assets{SEP}assets",
    f"src/pdf/templates{SEP}src/pdf/templates",
    f"bin{SEP}bin",
]

# Argumentos do PyInstaller
params = [
    str(SCRIPT),
    "--onefile",
    "--name=amil_bot_portatil",
    "--clean",
]

for item in ADD_DATA:
    params.extend(["--add-data", item])

# Adicionar imports ocultos se necessário
# undetected_chromedriver às vezes precisa ser explicitado
params.extend(["--hidden-import", "undetected_chromedriver"])
params.extend(["--hidden-import", "pdfkit"])

print("============================================================")
print("      INICIANDO BUILD DO EXECUTÁVEL (AMIL BOT)")
print("============================================================")
print(f"Script: {SCRIPT}")
print(f"Data Incluída: {ADD_DATA}")
print("-" * 60)

try:
    PyInstaller.__main__.run(params)
    print("\n" + "=" * 60)
    print("      BUILD CONCLUÍDO COM SUCESSO!")
    print(f"Executável disponível na pasta: {ROOT / 'dist'}")
    print("=" * 60)
except Exception as e:
    print(f"\nERRO NO BUILD: {e}")
    sys.exit(1)
