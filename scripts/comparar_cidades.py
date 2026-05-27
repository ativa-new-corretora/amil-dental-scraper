import json
import os
from pathlib import Path
from datetime import datetime

# Definir caminhos relativos ao projeto
SCRIPT_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = SCRIPT_DIR / "config" / "estados_cidades_amil.json"
# Base de PDFs: 'documentos/pdfs' (portable script) ou 'docs/pdfs' (main.py)
_pdfs_portable = SCRIPT_DIR / "documentos" / "pdfs"
_pdfs_main     = SCRIPT_DIR / "docs" / "pdfs"
PDFS_DIR = _pdfs_portable if _pdfs_portable.exists() else _pdfs_main
OUTPUT_REPORT = SCRIPT_DIR / "output" / f"relatorio_cidades_diferenca_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

def carregar_cidades_json(caminho):
    """Carrega as cidades do arquivo JSON e retorna um conjunto (set) de tuplas (ESTADO, CIDADE)"""
    cidades_json = set()
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            dados = json.load(f)
            for estado, cidades in dados.items():
                for cidade in cidades:
                    # Garantir formato padrão: sem espaços extras e em maiúsculo
                    cidade_limpa = str(cidade).strip().upper()
                    estado_limpo = str(estado).strip().upper()
                    cidades_json.add((estado_limpo, cidade_limpa))
    except Exception as e:
        print(f"Erro ao ler o arquivo JSON: {e}")
    return cidades_json

def carregar_cidades_pdfs(diretorio):
    """Lê os arquivos PDF e retorna um conjunto (set) de tuplas (ESTADO, CIDADE)"""
    cidades_pdfs = set()
    try:
        for root, _, files in os.walk(diretorio):
            for file in files:
                if file.endswith('.pdf'):
                    # O formato do arquivo é: NOME_DA_CIDADE-UF.pdf
                    nome_arquivo = file.replace('.pdf', '')
                    
                    # Dividir pelo último hífen, pois a cidade pode ter hífen no nome
                    if '-' in nome_arquivo:
                        partes = nome_arquivo.rsplit('-', 1)
                        if len(partes) == 2:
                            cidade = partes[0].replace('_', ' ').strip().upper()
                            estado = partes[1].strip().upper()
                            cidades_pdfs.add((estado, cidade))
    except Exception as e:
        print(f"Erro ao ler o diretório de PDFs: {e}")
    return cidades_pdfs

def gerar_relatorio(cidades_json, cidades_pdfs, caminho_saida):
    """Compara os conjuntos e gera um relatório"""
    
    # Cidades no JSON que NÃO estão nos PDFs (Novas cidades a gerar PDF)
    novas_cidades = sorted(list(cidades_json - cidades_pdfs))
    
    # Cidades nos PDFs que NÃO estão no JSON (Cidades que não existem mais/removidas)
    cidades_removidas = sorted(list(cidades_pdfs - cidades_json))
    
    # Criar o diretório de saída se não existir
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    
    with open(caminho_saida, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write(f"RELATÓRIO DE COMPARAÇÃO DE CIDADES - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write("="*70 + "\n\n")
        
        f.write(f"Total de cidades no arquivo JSON (Atuais): {len(cidades_json)}\n")
        f.write(f"Total de cidades nos PDFs gerados (Antigos): {len(cidades_pdfs)}\n\n")
        
        f.write("-"*70 + "\n")
        f.write(f"NOVAS CIDADES ADICIONADAS ({len(novas_cidades)} cidades que estão no JSON mas não têm PDF):\n")
        f.write("-"*70 + "\n")
        if not novas_cidades:
            f.write("  Nenhuma nova cidade encontrada.\n")
        else:
            estado_atual = ""
            for estado, cidade in novas_cidades:
                if estado != estado_atual:
                    f.write(f"\n[{estado}]\n")
                    estado_atual = estado
                f.write(f"  - {cidade}\n")
                
        f.write("\n\n" + "-"*70 + "\n")
        f.write(f"CIDADES REMOVIDAS ({len(cidades_removidas)} cidades que têm PDF mas não estão mais no JSON):\n")
        f.write("-"*70 + "\n")
        if not cidades_removidas:
            f.write("  Nenhuma cidade foi removida.\n")
        else:
            estado_atual = ""
            for estado, cidade in cidades_removidas:
                if estado != estado_atual:
                    f.write(f"\n[{estado}]\n")
                    estado_atual = estado
                f.write(f"  - {cidade}\n")
                
    print(f"\n📊 Relatório gerado com sucesso em:\n{caminho_saida}")
    
    # Imprimir resumo no terminal
    print("\nRESUMO:")
    print(f"- Total atual no JSON: {len(cidades_json)}")
    print(f"- Total em PDFs gerados: {len(cidades_pdfs)}")
    print(f"- Novas cidades identificadas: {len(novas_cidades)}")
    print(f"- Cidades removidas/indisponíveis: {len(cidades_removidas)}")

def main():
    print("Iniciando comparação entre arquivo JSON e diretório de PDFs...")
    
    if not JSON_PATH.exists():
        print(f"Erro: Arquivo JSON não encontrado em {JSON_PATH}")
        return
        
    if not PDFS_DIR.exists():
        print(f"Erro: Diretório de PDFs não encontrado em {PDFS_DIR}")
        return
        
    cidades_json = carregar_cidades_json(JSON_PATH)
    cidades_pdfs = carregar_cidades_pdfs(PDFS_DIR)
    
    gerar_relatorio(cidades_json, cidades_pdfs, OUTPUT_REPORT)

if __name__ == "__main__":
    main()
