import os
import sys
from pathlib import Path
import fitz  # PyMuPDF
import re

# Adicionar o diretório raiz ao path
SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from src.utils.file_manager import DOCS_PDFS_DIR


def contar_prestadores_no_pdf(caminho_pdf: Path) -> int:
    """
    Conta o número de prestadores em um PDF.
    """
    try:
        doc = fitz.open(caminho_pdf)
        total_prestadores = 0
        
        for pagina in doc:
            texto = pagina.get_text()
            
            # Verificar se é PDF vazio
            if "não possui a especialidade" in texto.lower() or "especialidade não encontrada" in texto.lower():
                doc.close()
                return 0
            
            # Contar ocorrências de "Nome:" (cada prestador tem um "Nome:")
            total_prestadores += texto.count("Nome:")
        
        doc.close()
        
        # Descontar 1 se houver cabeçalho que também tem "Nome:"
        # (geralmente o template não tem, mas garantir)
        return max(0, total_prestadores)
        
    except Exception as e:
        print(f"⚠️ Erro ao processar {caminho_pdf.name}: {e}")
        return 0


def listar_cidades_grandes(min_prestadores: int = 11) -> None:
    """
    Lista todas as cidades com mais de X prestadores, agrupadas por estado.
    """
    pasta_pdfs = DOCS_PDFS_DIR
    
    if not pasta_pdfs.exists():
        print(f"⚠️ Pasta não encontrada: {pasta_pdfs}")
        return
    
    print(f"\n{'='*80}")
    print(f"📊 Cidades com MAIS DE {min_prestadores} prestadores")
    print(f"{'='*80}\n")
    
    # Dicionário para armazenar por UF
    cidades_por_uf = {}
    total_cidades_grandes = 0
    
    # Iterar por todos os UFs
    for uf in sorted(os.listdir(pasta_pdfs)):
        pasta_uf = pasta_pdfs / uf
        
        if not pasta_uf.is_dir() or uf == "planilhas" or uf == "pdfs_sem_telefone":
            continue
        
        cidades_uf = []
        
        # Iterar por todos os PDFs do UF
        for arquivo in sorted(os.listdir(pasta_uf)):
            if not arquivo.lower().endswith(".pdf"):
                continue
            
            caminho_pdf = pasta_uf / arquivo
            
            # Contar prestadores
            num_prestadores = contar_prestadores_no_pdf(caminho_pdf)
            
            if num_prestadores > min_prestadores:
                # Extrair nome da cidade
                nome_sem_ext = arquivo.replace('.pdf', '')
                partes = nome_sem_ext.rsplit('-', 1)
                if len(partes) == 2:
                    cidade = partes[0].replace('_', ' ')
                    cidades_uf.append((cidade, num_prestadores))
        
        if cidades_uf:
            cidades_por_uf[uf] = cidades_uf
            total_cidades_grandes += len(cidades_uf)
    
    # Exibir resultados
    for uf in sorted(cidades_por_uf.keys()):
        print(f"📍 {uf}:")
        for cidade, num in sorted(cidades_por_uf[uf], key=lambda x: x[1], reverse=True):
            print(f"   • {cidade}: {num} prestadores")
        print()
    
    print(f"{'='*80}")
    print(f"✅ Total de cidades com mais de {min_prestadores} prestadores: {total_cidades_grandes}")
    print(f"{'='*80}\n")
    
    # Também salvar em arquivo txt
    arquivo_saida = SCRIPT_DIR / "cidades_grandes.txt"
    with open(arquivo_saida, "w", encoding="utf-8") as f:
        f.write(f"Cidades com MAIS DE {min_prestadores} prestadores\n")
        f.write("="*80 + "\n\n")
        
        for uf in sorted(cidades_por_uf.keys()):
            f.write(f"{uf}:\n")
            for cidade, num in sorted(cidades_por_uf[uf], key=lambda x: x[1], reverse=True):
                f.write(f"  • {cidade}: {num} prestadores\n")
            f.write("\n")
        
        f.write("="*80 + "\n")
        f.write(f"Total: {total_cidades_grandes} cidades\n")
    
    print(f"📄 Lista salva em: {arquivo_saida}")


if __name__ == "__main__":
    # Você pode mudar o número mínimo de prestadores aqui
    listar_cidades_grandes(min_prestadores=11)
