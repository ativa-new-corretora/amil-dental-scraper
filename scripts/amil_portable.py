import os
import sys
import json
import time
import random
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime

# Configuração para PyInstaller: encontrar arquivos embutidos
if hasattr(sys, '_MEIPASS'):
    BASE_PATH = Path(sys._MEIPASS)
else:
    BASE_PATH = Path(__file__).resolve().parent.parent

# Adicionar o diretório de execução ao sys.path para importações internas se necessário
# No EXE, o sys.path já costuma estar ok, mas vamos garantir.
sys.path.insert(0, str(BASE_PATH))

# Importações do projeto
try:
    from src.scraper.amil_scraper import AmilBot
    from src.utils.logger import setup_logger
    from src.utils.file_manager import ensure_dir
    import pdfkit
except ImportError as e:
    print(f"Erro ao importar módulos: {e}")
    sys.exit(1)

# ============================================================
#  CONFIGURAÇÃO DE CAMINHOS PORTÁTEIS
# ============================================================

EXE_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent

# JSON de Cidades: ao rodar como .exe, deve estar na mesma pasta; como script, está em config/
if getattr(sys, 'frozen', False):
    CIDADES_JSON_LOCAL     = EXE_DIR / "estados_cidades_amil.json"
    ESTRATEGICO_JSON_LOCAL = EXE_DIR / "cidades_estrategicas.json"
else:
    CIDADES_JSON_LOCAL     = EXE_DIR / "config" / "estados_cidades_amil.json"
    ESTRATEGICO_JSON_LOCAL = EXE_DIR / "config" / "cidades_estrategicas.json"

# Pasta de Documentos (Saída)
DOCUMENTOS_DIR = EXE_DIR / "documentos"
PDFS_DIR = DOCUMENTOS_DIR / "pdfs"
PDFS_SEM_TEL_DIR = DOCUMENTOS_DIR / "pdfs_sem_telefone"
PLANILHAS_DIR = DOCUMENTOS_DIR / "planilhas"
LOGS_DIR = DOCUMENTOS_DIR / "logs"

# WKHTMLTOPDF
# No EXE, vamos tentar pegar o que está embutido ou se o usuário colocou no bin/
WKHTMLTOPDF_EMBEDDED = BASE_PATH / "bin" / "wkhtmltopdf.exe"
WKHTMLTOPDF_LOCAL = EXE_DIR / "bin" / "wkhtmltopdf.exe"

if WKHTMLTOPDF_EMBEDDED.exists():
    WK_PATH = str(WKHTMLTOPDF_EMBEDDED)
elif WKHTMLTOPDF_LOCAL.exists():
    WK_PATH = str(WKHTMLTOPDF_LOCAL)
else:
    # Fallback para o caminho padrão de instalação
    WK_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"

PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WK_PATH)

# LOGOS (Embutidos no EXE)
LOGO_AMIL = BASE_PATH / "assets" / "amil_dental.jpg"
LOGO_ATIVA = BASE_PATH / "assets" / "logo_ativa.jpg"
TEMPLATES_DIR = BASE_PATH / "src" / "pdf" / "templates"

# ============================================================
#  FUNÇÕES DE SUPORTE
# ============================================================

def _limpar_chrome():
    """Mata processos órfãos do Chrome/chromedriver e limpa cache do undetected_chromedriver."""
    import subprocess, shutil
    for proc in ("undetected_chromedriver.exe", "chromedriver.exe"):
        try:
            subprocess.run(["taskkill", "/F", "/IM", proc, "/T"],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass
    try:
        uc_cache = Path(os.getenv("APPDATA", "")) / "undetected_chromedriver"
        if uc_cache.exists():
            shutil.rmtree(uc_cache, ignore_errors=True)
    except Exception:
        pass


def _carregar_template(nome_arquivo: str) -> str:
    caminho = TEMPLATES_DIR / nome_arquivo
    with open(caminho, "r", encoding="utf-8") as f:
        return f.read()

def gerar_pdfs_cidade(uf: str, cidade: str, prestadores: list[dict], mes_referencia: str):
    """Gera tanto o PDF normal quanto o sem telefone."""
    
    # Criar pastas
    ensure_dir(PDFS_DIR / uf)
    ensure_dir(PDFS_SEM_TEL_DIR / uf)
    
    nome_base = f"{cidade}-{uf}".replace(" ", "_")
    path_normal = PDFS_DIR / uf / f"{nome_base}.pdf"
    path_sem_tel = PDFS_SEM_TEL_DIR / uf / f"{nome_base}.pdf"
    
    # Logos as URI para o HTML (pdfkit precisa disso para acesso local)
    logo_amil_uri = LOGO_AMIL.resolve().as_uri()
    logo_ativa_uri = LOGO_ATIVA.resolve().as_uri()
    
    # Preparar Mes (escapar Março)
    mes_html = mes_referencia.replace("Março", "Mar&ccedil;o")
    
    options_pdf = {
        "enable-local-file-access": "",
        "encoding": "utf-8",
        "quiet": ""
    }
    
    # --- PDF NORMAL ---
    template_p = _carregar_template("prestadores.html")
    
    if not prestadores:
        # Vazio
        template_v = _carregar_template("sem_especialidade.html")
        html = (template_v
                .replace("{{LOGO_AMIL}}", logo_amil_uri)
                .replace("{{LOGO_ATIVA}}", logo_ativa_uri)
                .replace("{{REFERENCIA}}", mes_html)
                .replace("{{CIDADE}}", cidade)
                .replace("{{UF}}", uf))
        pdfkit.from_string(html, str(path_normal), configuration=PDFKIT_CONFIG, options=options_pdf)
        # Sem telefone (vazio também)
        pdfkit.from_string(html, str(path_sem_tel), configuration=PDFKIT_CONFIG, options=options_pdf)
    else:
        # Com prestadores
        # 1. Normal
        html_p = []
        for p in prestadores:
            bloco = (
                "<div class='prestador'>"
                f"<strong>Nome:</strong> {p['nome']}<br>"
                f"<strong>Bairro:</strong> {p['bairro']}<br>"
                f"<strong>Endereço:</strong> {p['endereco']}<br>"
                f"<strong>Telefone:</strong> {p['telefone']}"
                "</div>"
            )
            html_p.append(bloco)
        
        html = (
            template_p
            .replace("{{LOGO_AMIL}}", logo_amil_uri)
            .replace("{{LOGO_ATIVA}}", logo_ativa_uri)
            .replace("{{REFERENCIA}}", mes_html)
            .replace("{{CIDADE}}", cidade)
            .replace("{{UF}}", uf)
            .replace("{{TOTAL_PRESTADORES}}", str(len(prestadores)))
            .replace("<!--PRESTADORES-->", "\n".join(html_p))
        )
        pdfkit.from_string(html, str(path_normal), configuration=PDFKIT_CONFIG, options=options_pdf)
        
        # 2. Sem Telefone
        html_st = []
        for p in prestadores:
            bloco = (
                "<div class='prestador'>"
                f"<strong>Nome:</strong> {p['nome']}<br>"
                f"<strong>Bairro:</strong> {p['bairro']}<br>"
                f"<strong>Endereço:</strong> {p['endereco']}"
                "</div>"
            )
            html_st.append(bloco)
            
        html_sem_tel = (
            template_p
            .replace("{{LOGO_AMIL}}", logo_amil_uri)
            .replace("{{LOGO_ATIVA}}", logo_ativa_uri)
            .replace("{{REFERENCIA}}", mes_html)
            .replace("{{CIDADE}}", cidade)
            .replace("{{UF}}", uf)
            .replace("{{TOTAL_PRESTADORES}}", str(len(prestadores)))
            .replace("<!--PRESTADORES-->", "\n".join(html_st))
        )
        pdfkit.from_string(html_sem_tel, str(path_sem_tel), configuration=PDFKIT_CONFIG, options=options_pdf)

def gerar_planilha_final():
    """Gera a planilha Excel com base nos PDFs gerados."""
    ensure_dir(PLANILHAS_DIR)
    output_file = PLANILHAS_DIR / "planilha_simples.xlsx"
    
    dados = []
    
    if not PDFS_DIR.exists():
        return
        
    for root, dirs, files in os.walk(PDFS_DIR):
        for file in files:
            if file.lower().endswith(".pdf"):
                uf = os.path.basename(root)
                filename = file
                cidade_nome = os.path.splitext(filename)[0]
                if cidade_nome.endswith(f"-{uf}"):
                     cidade_nome = cidade_nome[:-(len(uf)+1)]
                
                url = f"https://odontoplanos.online/rede/{uf}/{filename}"
                
                dados.append({
                    "Cidade": cidade_nome.replace("_", " "),
                    "UF": uf,
                    "Link": url
                })
    
    if not dados:
        print("Nenhum PDF encontrado para gerar a planilha.")
        return

    df = pd.DataFrame(dados)
    df = df.sort_values(by=["UF", "Cidade"])
    df.insert(0, 'Id', range(1, len(df) + 1))
    
    try:
        df.to_excel(output_file, index=False)
        print(f"Planilha gerada em: {output_file}")
    except Exception as e:
        print(f"Erro ao gerar planilha: {e}")

# ============================================================
#  MAIN LOOP
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Amil Scraper Portatil")
    parser.add_argument("--uf", nargs="*", help="Filtrar por UFs (ex: --uf AC AL)")
    parser.add_argument("--cidade", nargs="*", help="Filtrar por cidades (ex: --cidade \"RIO BRANCO\")")
    parser.add_argument("--mes", default="Maio / 2026", help="Mes de referencia no PDF")
    parser.add_argument("--estrategico", action="store_true",
                        help="Usar apenas cidades estratégicas (capitais + grandes cidades ~112 cidades)")
    args = parser.parse_args()

    print("============================================================")
    print("      AMIL SCRAPER PORTATIL - Headless Edition")
    print("============================================================")
    
    # Selecionar JSON de cidades
    if args.estrategico:
        json_path = ESTRATEGICO_JSON_LOCAL
        if not json_path.exists():
            print(f"ERRO: Arquivo {json_path.name} nao encontrado!")
            print("Execute sem --estrategico ou crie o arquivo config/cidades_estrategicas.json.")
            input("\nPressione Enter para sair...")
            sys.exit(1)
    else:
        json_path = CIDADES_JSON_LOCAL
        if not json_path.exists():
            print(f"ERRO: Arquivo {json_path.name} nao encontrado na pasta do executavel!")
            print("Por favor, coloque o arquivo JSON de cidades junto com este EXE.")
            input("\nPressione Enter para sair...")
            sys.exit(1)

    # Carregar Cidades
    with open(json_path, 'r', encoding='utf-8') as f:
        mapa = json.load(f)

    # Filtros
    if args.uf:
        filtro_ufs = [u.upper() for u in args.uf]
        mapa = {uf: cidades for uf, cidades in mapa.items() if uf in filtro_ufs}
    
    if args.cidade:
        filtro_cids = [c.upper() for c in args.cidade]
        nova_mapa = {}
        for uf, cidades in mapa.items():
            cids_filtradas = [c for c in cidades if c.upper() in filtro_cids]
            if cids_filtradas:
                nova_mapa[uf] = cids_filtradas
        mapa = nova_mapa

    total_cidades = sum(len(c) for c in mapa.values())
    if total_cidades == 0:
        print("Nenhuma cidade encontrada com os filtros informados.")
        sys.exit(0)

    # Forçar re-processamento quando o usuário especificou quais cidades/estados quer rodar
    # ou quando usou --estrategico (intenção é sempre scraping fresco das cidades prioritárias)
    force_rerun = True if (args.uf or args.cidade or args.estrategico) else False

    print(f"Total de cidades a processar: {total_cidades}")
    print(f"Mes de referencia: {args.mes}")
    print(f"Lista: {'ESTRATÉGICA (~112 cidades)' if args.estrategico else 'COMPLETA'}")
    print(f"Modo: {'Sobrescrever existentes' if force_rerun else 'Apenas novas (pular existentes)'}")
    print("Saida: pasta 'documentos/'")
    print("-" * 60)

    # Garantir pastas de saída
    ensure_dir(DOCUMENTOS_DIR)
    ensure_dir(LOGS_DIR)
    
    logger = setup_logger("amil_portable", LOGS_DIR / "bot.log")
    contador = 0

    for uf, cidades in mapa.items():
        print(f"\n[{uf}] - {len(cidades)} cidades")
        for cidade in cidades:
            contador += 1
            
            # --- NOVO: Verificar se PDF já existe (e se não estamos forçando) ---
            nome_base = f"{cidade}-{uf}".replace(" ", "_")
            path_pdf = PDFS_DIR / uf / f"{nome_base}.pdf"
            
            if not force_rerun and path_pdf.exists():
                print(f"  [{contador}/{total_cidades}] {cidade}: Pulando (PDF já existe)")
                continue

            print(f"  [{contador}/{total_cidades}] Processando {cidade}...", end=" ", flush=True)
            
            tentativa = 0
            sucesso = False
            MAX_TENTATIVAS = 3
            while tentativa < MAX_TENTATIVAS and not sucesso:
                tentativa += 1
                bot = None
                try:
                    bot = AmilBot(uf, logger=logger)
                    bot._abrir_navegador()

                    # Fluxo rápido de extração
                    bot._passo1()
                    time.sleep(1)
                    bot._passo2(cidade)
                    time.sleep(1)

                    try:
                        bot._passo3(cidade)
                        time.sleep(2)

                        # Clicar Buscar — clique humano (ActionChains), nunca JS
                        from selenium.webdriver.common.by import By
                        from selenium.webdriver.support.ui import WebDriverWait
                        from selenium.webdriver.support import expected_conditions as EC

                        btn = WebDriverWait(bot.driver, 10).until(
                            EC.element_to_be_clickable((By.CLASS_NAME, "test_btn_thirdstep_submit"))
                        )
                        bot._clicar_humano(btn)
                        time.sleep(5)

                        # Extrair blocos
                        blocos = bot.driver.find_elements(By.CLASS_NAME, "accredited-network__result")
                        blocos = [b for b in blocos if b.text.strip()]

                        prestadores = bot._extrair_prestadores(blocos) if blocos else None

                        if not prestadores:
                            try:
                                msg = bot.driver.find_elements(By.XPATH, "//*[contains(text(),'Nenhum resultado')]")
                                if msg:
                                    raise Exception("Shadow block: site retornou 'Nenhum resultado'")
                            except Exception as _e:
                                if "Shadow block" in str(_e): raise _e
                            raise Exception("Shadow block: nenhum prestador encontrado")

                    except Exception as e:
                        if "Especialidade" in str(e):
                            prestadores = None  # cidade sem especialidade — não é erro
                        else:
                            raise e

                    # Gerar PDFs
                    gerar_pdfs_cidade(uf, cidade, prestadores, args.mes)

                    print(f"OK ({len(prestadores) if prestadores else 0} prestadores)")
                    sucesso = True

                except Exception as e:
                    e_str = str(e)
                    if tentativa < MAX_TENTATIVAS:
                        eh_shadow = "Shadow block" in e_str or "prestador" in e_str.lower()
                        espera = 35 if eh_shadow else 8
                        print(f"(T{tentativa} — {'shadow block' if eh_shadow else 'erro'}; aguardando {espera}s)",
                              end=" ", flush=True)
                        # Fechar browser antes de limpar para evitar processos órfãos
                        if bot:
                            try: bot._fechar_navegador_completamente()
                            except: pass
                            bot = None
                        _limpar_chrome()
                        time.sleep(espera)
                    else:
                        print(f"FALHA definitiva: {e_str[:100]}")

                finally:
                    if bot:
                        try:
                            bot._fechar_navegador_completamente()
                        except:
                            pass
            
            # Cooldown entre cidades
            time.sleep(random.uniform(2, 4))

    # Gerar Planilha ao final
    print("\nGerando planilha Excel final...")
    gerar_planilha_final()
    
    print("\n" + "=" * 60)
    print("Processo concluído!")
    print(f"Verifique a pasta: {DOCUMENTOS_DIR}")
    print("=" * 60)
    
    # Pausa para o usuário ver o resultado se estiver rodando manual
    input("\nPressione Enter para fechar...")

if __name__ == "__main__":
    main()
