import os
import sys
from pathlib import Path
import fitz  # PyMuPDF
import pdfkit
import re

# Adicionar o diretório raiz ao path para importar utils
SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from src.utils.file_manager import (
    DOCS_PDFS_DIR, SCRIPT_DIR, LOGO_AMIL, LOGO_ATIVA, TEMPLATES_DIR
)

# Configuração do wkhtmltopdf
WKHTMLTOPDF_PATH = os.getenv(
    "WKHTMLTOPDF_PATH",
    r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
)
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)


def _carregar_template(nome_arquivo: str) -> str:
    caminho = TEMPLATES_DIR / nome_arquivo
    with open(caminho, "r", encoding="utf-8") as f:
        return f.read()


def extrair_prestadores_do_pdf(caminho_pdf: Path) -> list[dict] | None:
    """
    Extrai a lista de prestadores de um PDF existente de forma mais robusta.
    Retorna None se o PDF é vazio (sem especialidade).
    """
    try:
        doc = fitz.open(caminho_pdf)
        
        # 🔥 MUDANÇA: Extrair TODO o texto do PDF de uma vez
        # Isso evita problemas com prestadores divididos entre páginas
        texto_completo = ""
        for pagina in doc:
            texto_completo += pagina.get_text()
        
        doc.close()
        
        # Verificar se é PDF vazio (sem especialidade)
        if "não possui a especialidade" in texto_completo.lower() or "especialidade não encontrada" in texto_completo.lower():
            return None
        
        prestadores = []
        
        # Dividir o texto em blocos por "Nome:"
        blocos = re.split(r'(?=Nome:\s*)', texto_completo)
        
        for bloco in blocos:
            bloco = bloco.strip()
            if not bloco or not bloco.startswith('Nome:'):
                continue
            
            # Extrair cada campo do bloco usando regex com DOTALL
            nome_match = re.search(r'Nome:\s*(.+?)(?=\s*(?:Bairro:|Endereço:|Telefone:|Nome:|$))', bloco, re.DOTALL)
            bairro_match = re.search(r'Bairro:\s*(.+?)(?=\s*(?:Endereço:|Telefone:|Nome:|$))', bloco, re.DOTALL)
            endereco_match = re.search(r'Endereço:\s*(.+?)(?=\s*(?:Telefone:|Nome:|$))', bloco, re.DOTALL)
            telefone_match = re.search(r'Telefone:\s*(.+?)(?=\s*(?:Nome:|$))', bloco, re.DOTALL)
            
            if nome_match:
                nome = nome_match.group(1).strip()
                nome = ' '.join(nome.split())  # Normalizar espaços e quebras de linha
                
                # Ignorar nomes inválidos
                if not nome or nome == 'NOME NÃO ENCONTRADO' or len(nome) < 3:
                    continue
                
                bairro = ''
                endereco = ''
                telefone = ''
                
                if bairro_match:
                    bairro = bairro_match.group(1).strip()
                    bairro = ' '.join(bairro.split())  # Normalizar espaços e quebras de linha
                
                if endereco_match:
                    endereco = endereco_match.group(1).strip()
                    endereco = ' '.join(endereco.split())  # Normalizar espaços e quebras de linha
                
                if telefone_match:
                    telefone = telefone_match.group(1).strip()
                    telefone = ' '.join(telefone.split())  # Normalizar espaços e quebras de linha
                
                prestador = {
                    'nome': nome,
                    'bairro': bairro,
                    'endereco': endereco,
                    'telefone': telefone
                }
                
                prestadores.append(prestador)
        
        return prestadores if prestadores else None
        
    except Exception as e:
        print(f"      ⚠️ Erro ao extrair prestadores de {caminho_pdf.name}: {e}")
        import traceback
        traceback.print_exc()
        return None


def gerar_pdf_sem_telefone(uf: str, cidade: str, prestadores: list[dict] | None, pasta_destino: Path) -> Path | None:
    """
    Gera PDF sem telefone com referência "Dezembro / 2025".
    Se prestadores é None, gera PDF vazio.
    """
    uf_dir = pasta_destino / uf
    uf_dir.mkdir(parents=True, exist_ok=True)
    
    nome_arquivo = f"{cidade}-{uf}".replace(" ", "_")
    pdf_path = uf_dir / f"{nome_arquivo}.pdf"
    
    if prestadores is None:
        # PDF vazio (sem especialidade)
        template = _carregar_template("sem_especialidade.html")
        mes_ano = "Dezembro / 2025"
        
        html = (
            template
            .replace("{{REFERENCIA}}", mes_ano)
            .replace("{{CIDADE}}", cidade)
            .replace("{{UF}}", uf)
        )
    else:
        # PDF com prestadores (SEM TELEFONE)
        template = _carregar_template("prestadores.html")
        
        # LOGOS
        logo_amil = LOGO_AMIL.resolve().as_uri()
        logo_ativa = LOGO_ATIVA.resolve().as_uri()
        
        mes_ano = "Dezembro / 2025"
        
        # Gera os blocos dos prestadores SEM A LINHA DE TELEFONE
        html_prestadores = []
        for p in prestadores:
            bloco = (
                "<div class='prestador'>"
                f"<strong>Nome:</strong> {p['nome']}<br>"
                f"<strong>Bairro:</strong> {p['bairro']}<br>"
                f"<strong>Endereço:</strong> {p['endereco']}"
                "</div>"
            )
            html_prestadores.append(bloco)
        
        # Insere tudo no template
        html = (
            template
            .replace("{{LOGO_AMIL}}", logo_amil)
            .replace("{{LOGO_ATIVA}}", logo_ativa)
            .replace("{{REFERENCIA}}", mes_ano)
            .replace("{{CIDADE}}", cidade)
            .replace("{{UF}}", uf)
            .replace("{{TOTAL_PRESTADORES}}", str(len(prestadores)))
            .replace("<!--PRESTADORES-->", "\n".join(html_prestadores))
        )
    
    options_pdf = {"enable-local-file-access": ""}
    
    try:
        pdfkit.from_string(html, str(pdf_path), configuration=PDFKIT_CONFIG, options=options_pdf)
        return pdf_path
    except Exception as e:
        print(f"      ❌ Erro ao gerar PDF {cidade}-{uf}: {e}")
        return None


def gerar_todos_pdfs_sem_telefone() -> None:
    """
    Gera todos os PDFs sem telefone e salva em docs/pdfs_sem_telefone.
    """
    pasta_origem = DOCS_PDFS_DIR
    pasta_destino = SCRIPT_DIR / "docs" / "pdfs_sem_telefone"
    
    if not pasta_origem.exists():
        print(f"⚠️  Pasta de origem não encontrada: {pasta_origem}")
        return
    
    # Criar pasta de destino se não existir
    pasta_destino.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📁 Gerando PDFs SEM TELEFONE")
    print(f"📂 Origem: {pasta_origem}")
    print(f"📂 Destino: {pasta_destino}")
    print(f"📅 Referência: Dezembro / 2025")
    print(f"📵 Telefones serão REMOVIDOS dos PDFs")
    
    total_gerados = 0
    total_erros = 0
    
    # Iterar por todos os UFs
    for uf in sorted(os.listdir(pasta_origem)):
        pasta_uf = pasta_origem / uf
        
        if not pasta_uf.is_dir() or uf == "planilhas":
            continue
        
        print(f"\n  📂 Processando {uf}...")
        pdfs_uf = 0
        erros_uf = 0
        
        # Iterar por todos os PDFs do UF
        for arquivo in sorted(os.listdir(pasta_uf)):
            if not arquivo.lower().endswith(".pdf"):
                continue
            
            caminho_pdf_origem = pasta_uf / arquivo
            
            try:
                # Extrair nome da cidade do nome do arquivo
                # Formato: CIDADE-UF.pdf
                nome_sem_ext = arquivo.replace('.pdf', '')
                partes = nome_sem_ext.rsplit('-', 1)
                if len(partes) == 2:
                    cidade = partes[0].replace('_', ' ')
                    uf_arquivo = partes[1]
                else:
                    print(f"      ⚠️ Formato de nome inválido: {arquivo}")
                    continue
                
                # Extrair prestadores do PDF existente
                prestadores = extrair_prestadores_do_pdf(caminho_pdf_origem)
                
                # Gerar novo PDF SEM TELEFONE
                pdf_path = gerar_pdf_sem_telefone(uf_arquivo, cidade, prestadores, pasta_destino)
                
                if pdf_path:
                    total_gerados += 1
                    pdfs_uf += 1
                    if pdfs_uf % 10 == 0:  # Log a cada 10 PDFs
                        print(f"    ✅ {pdfs_uf} PDFs gerados...")
                else:
                    erros_uf += 1
                    total_erros += 1
                    
            except Exception as e:
                print(f"    ❌ Erro ao processar {arquivo}: {e}")
                erros_uf += 1
                total_erros += 1
                import traceback
                traceback.print_exc()
        
        print(f"  ✅ {uf}: {pdfs_uf} PDFs gerados, {erros_uf} erros")
    
    print(f"\n" + "="*60)
    print(f"✅ Total de PDFs gerados SEM TELEFONE: {total_gerados}")
    print(f"❌ Total de erros: {total_erros}")
    print(f"📂 PDFs salvos em: {pasta_destino}")
    print("="*60)


if __name__ == "__main__":
    gerar_todos_pdfs_sem_telefone()
