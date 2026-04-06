from pathlib import Path

# Raiz do projeto (pasta onde fica o main.py)
# Se estamos em src/utils/, precisamos subir 2 níveis para chegar na raiz
SCRIPT_DIR = Path(__file__).resolve().parents[2]

# Pastas de saída
OUTPUT_DIR = SCRIPT_DIR / "output"
LOGS_DIR = SCRIPT_DIR / "logs"
REDE_COMPLETA_DIR = OUTPUT_DIR / "Rede_Amil_Completa"
REDE_SEM_TEL_DIR = OUTPUT_DIR / "Rede_Amil_Sem_Telefone"

# Pastas de documentação (GitHub Pages)
DOCS_PDFS_DIR = SCRIPT_DIR / "docs" / "pdfs"
DOCS_PLANILHAS_DIR = SCRIPT_DIR / "docs" / "planilhas"

# Pastas de configuração
CONFIG_DIR = SCRIPT_DIR / "config"
CIDADES_JSON = CONFIG_DIR / "estados_cidades_amil.json"

# Pastas de assets
ASSETS_DIR = SCRIPT_DIR / "assets"
LOGO_AMIL = ASSETS_DIR / "amil_dental.jpg"
LOGO_ATIVA = ASSETS_DIR / "logo_ativa.jpg"

# Templates
TEMPLATES_DIR = SCRIPT_DIR / "src" / "pdf" / "templates"


def ensure_dir(path: Path) -> Path:
    """Garante que um diretório existe."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_estado_dir(uf: str, base_dir: Path | None = None) -> Path:
    """Retorna/cria a pasta do estado dentro da base."""
    if base_dir is None:
        base_dir = REDE_COMPLETA_DIR
    return ensure_dir(base_dir / uf)


def get_pdf_path(uf: str, cidade: str, base_dir: Path | None = None) -> Path:
    """Caminho do PDF para uma cidade/UF."""
    if base_dir is None:
        base_dir = REDE_COMPLETA_DIR
    uf_dir = get_estado_dir(uf, base_dir)
    nome_arquivo = f"{cidade}-{uf}".replace(" ", "_")
    return uf_dir / f"{nome_arquivo}.pdf"