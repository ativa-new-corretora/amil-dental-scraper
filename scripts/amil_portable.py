import os
import sys
import json
import time
import random
import argparse
import pandas as pd
from html import escape
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
    from src.scraper.anti_bot import preparar_driver_proprio
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

def _limpar_chrome(limpar_cache: bool = True):
    """Mata processos órfãos do Chrome/chromedriver e limpa cache do undetected_chromedriver."""
    import subprocess, shutil
    if os.getenv("AMIL_PARALELO") == "1":
        return  # em paralelo isso derrubaria os navegadores dos outros processos
    for proc in ("undetected_chromedriver.exe", "chromedriver.exe"):
        try:
            subprocess.run(["taskkill", "/F", "/IM", proc, "/T"],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass
    if not limpar_cache:
        return
    try:
        uc_cache = Path(os.getenv("APPDATA", "")) / "undetected_chromedriver"
        if uc_cache.exists():
            shutil.rmtree(uc_cache, ignore_errors=True)
    except Exception:
        pass


MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def _mes_atual() -> str:
    hoje = datetime.now()
    return f"{MESES[hoje.month - 1]} / {hoje.year}"


def _manter_pc_acordado() -> None:
    """Impede o Windows de suspender enquanto este processo roda (só a tela pode apagar)."""
    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:
        pass


class _Tee:
    """Espelha o console num arquivo UTF-8 — dá para acompanhar com Get-Content -Wait."""

    def __init__(self, console, arquivo):
        self.console, self.arquivo = console, arquivo

    def write(self, s):
        try:
            self.console.write(s)
        except Exception:
            pass
        self.arquivo.write(s)

    def flush(self):
        for f in (self.console, self.arquivo):
            try:
                f.flush()
            except Exception:
                pass


def _pausar_se_interativo(msg: str) -> None:
    """Rodando em segundo plano não há ninguém para apertar Enter."""
    # No Windows o NUL se diz "tty", por isso também tratar o EOF
    if sys.stdin and sys.stdin.isatty():
        try:
            input(msg)
        except EOFError:
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
        # Com prestadores — escapar "&", "<" etc. que aparecem em nomes de clínicas
        prestadores = [{k: escape(v or "") for k, v in p.items()} for p in prestadores]

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
#  SCRAPING DE UMA CIDADE
# ============================================================

class ShadowBlock(Exception):
    """Site respondeu sem prestadores numa cidade que tem Clínica Geral."""


MSGS_SEM_PRESTADOR = ("não localizou nenhum prestador", "Nenhum resultado")


def _sem_prestadores_na_tela(driver) -> bool:
    """O site mostra 'Sua busca não localizou nenhum prestador' — no shadow block também."""
    from selenium.webdriver.common.by import By
    for texto in MSGS_SEM_PRESTADOR:
        try:
            els = driver.find_elements(By.XPATH, f"//*[contains(text(),'{texto}')]")
            if any(e.is_displayed() for e in els):
                return True
        except Exception:
            continue
    return False


def _aguardar_resultados(driver, timeout: float = 90) -> None:
    """
    Espera a lista de prestadores parar de crescer. Cidades grandes (SP, RJ)
    levam bem mais que 5s para renderizar milhares de resultados; um sleep
    fixo cortava a lista no meio.
    """
    from selenium.webdriver.common.by import By

    time.sleep(5)  # dá tempo da mensagem antiga sumir e a busca de fato começar
    fim = time.time() + timeout
    anterior, estavel_desde = -1, time.time()
    while time.time() < fim:
        n = len(driver.find_elements(By.CLASS_NAME, "accredited-network__result"))
        if n == 0 and _sem_prestadores_na_tela(driver):
            return
        if n != anterior:
            anterior, estavel_desde = n, time.time()
        elif n > 0 and time.time() - estavel_desde >= 4:
            return
        # Se a lista carregar sob demanda ao rolar, isto dispara o próximo lote
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass
        time.sleep(1)


def processar_cidade(uf: str, cidade: str, mes: str, logger) -> int:
    """
    Faz o scraping de uma cidade e gera os dois PDFs.
    Retorna o número de prestadores (0 = cidade sem Clínica Geral).
    Levanta exceção se falhar — quem chama decide se tenta de novo.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    bot = AmilBot(uf, logger=logger)
    bot.gerar_pdf_vazio = False  # os PDFs são gerados aqui, em documentos/
    try:
        bot._abrir_navegador()

        bot._passo1()
        time.sleep(1)
        bot._passo2(cidade)
        time.sleep(1)

        try:
            bot._passo3(cidade)
        except Exception as e:
            if "Especialidade" not in str(e):
                raise
            # Cidade sem Clínica Geral — não é erro, gera o PDF "sem especialidade"
            gerar_pdfs_cidade(uf, cidade, None, mes)
            return 0

        bot._passear_mouse()

        # Clicar Buscar — clique humano (mouse em curva), nunca JS
        btn = WebDriverWait(bot.driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "test_btn_thirdstep_submit"))
        )
        bot._clicar_humano(btn)
        _aguardar_resultados(bot.driver)

        blocos = bot.driver.find_elements(By.CLASS_NAME, "accredited-network__result")
        blocos = [b for b in blocos if b.text.strip()]
        prestadores = bot._extrair_prestadores(blocos) if blocos else []

        if not prestadores:
            raise ShadowBlock("site não retornou prestadores")

        gerar_pdfs_cidade(uf, cidade, prestadores, mes)
        return len(prestadores)
    finally:
        try:
            bot._fechar_navegador_completamente()
        except Exception:
            pass


def processar_com_tentativas(uf: str, cidade: str, mes: str, logger,
                             max_tentativas: int = 3) -> tuple[bool, str]:
    """Até 3 tentativas, cada uma com um Chrome novo. Retorna (sucesso, mensagem)."""
    ultimo_erro = ""
    for tentativa in range(1, max_tentativas + 1):
        try:
            n = processar_cidade(uf, cidade, mes, logger)
            return True, f"OK ({n} prestadores)" if n else "OK (sem Clínica Geral — PDF vazio)"
        except Exception as e:
            ultimo_erro = str(e).splitlines()[0][:150] if str(e) else type(e).__name__
            if tentativa == max_tentativas:
                break
            eh_shadow = isinstance(e, ShadowBlock)
            espera = random.uniform(30, 45) if eh_shadow else random.uniform(8, 15)
            print(f"(T{tentativa} {'shadow block' if eh_shadow else 'erro'}: {ultimo_erro[:60]}; "
                  f"aguardando {espera:.0f}s)", end=" ", flush=True)
            # Shadow block é do site: o driver está bom, não precisa baixá-lo de novo
            _limpar_chrome(limpar_cache=not eh_shadow)
            time.sleep(espera)
    return False, f"FALHA: {ultimo_erro}"


def _rodar_lista(lista: list[tuple[str, str]], mes: str, logger, rotulo: str) -> list[tuple[str, str]]:
    """Processa (uf, cidade) em sequência. Retorna as que falharam."""
    falhas = []
    falhas_seguidas = 0
    total = len(lista)
    inicio = time.time()

    for i, (uf, cidade) in enumerate(lista, start=1):
        decorrido = time.time() - inicio
        restante = decorrido / (i - 1) * (total - i + 1) if i > 1 else 0
        eta = f" | faltam ~{restante / 3600:.1f}h" if i > 1 else ""
        print(f"  [{rotulo} {i}/{total}{eta}] {datetime.now():%H:%M} {cidade}-{uf}...",
              end=" ", flush=True)

        ok, msg = processar_com_tentativas(uf, cidade, mes, logger)
        print(msg, flush=True)

        if ok:
            falhas_seguidas = 0
        else:
            falhas.append((uf, cidade))
            falhas_seguidas += 1
            # Muitas falhas seguidas = IP queimado pelo anti-robô. Insistir só piora.
            if falhas_seguidas >= 4:
                pausa = 15 * 60
                print(f"  !! {falhas_seguidas} falhas seguidas — provável bloqueio. "
                      f"Pausando {pausa // 60} min ({datetime.now():%H:%M})...", flush=True)
                time.sleep(pausa)
                falhas_seguidas = 0

        # Cooldown entre cidades
        time.sleep(random.uniform(2, 4))

    return falhas


# ============================================================
#  MAIN LOOP
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Amil Scraper Portatil")
    parser.add_argument("--uf", nargs="*", help="Filtrar por UFs (ex: --uf AC AL)")
    parser.add_argument("--cidade", nargs="*", help="Filtrar por cidades (ex: --cidade \"RIO BRANCO\")")
    parser.add_argument("--mes", default=_mes_atual(), help="Mes de referencia no PDF (padrão: mês atual)")
    parser.add_argument("--estrategico", action="store_true",
                        help="Usar apenas cidades estratégicas (capitais + grandes cidades ~112 cidades)")
    parser.add_argument("--forcar", action="store_true",
                        help="Refazer também as cidades que já têm PDF")
    parser.add_argument("--parte", default="1/1",
                        help="Divide a lista entre processos paralelos: --parte 2/3 = 2º de 3")
    args = parser.parse_args()

    parte, n_partes = (int(x) for x in args.parte.split("/"))
    sufixo = f"_parte{parte}" if n_partes > 1 else ""
    if n_partes > 1:
        os.environ["AMIL_PARALELO"] = "1"

    ensure_dir(LOGS_DIR)
    sys.stdout = _Tee(sys.stdout, open(LOGS_DIR / f"execucao{sufixo}.log", "a", encoding="utf-8"))

    print("============================================================")
    print(f"      AMIL SCRAPER PORTATIL — início {datetime.now():%d/%m/%Y %H:%M}")
    print("============================================================")

    # Selecionar JSON de cidades
    if args.estrategico:
        json_path = ESTRATEGICO_JSON_LOCAL
        if not json_path.exists():
            print(f"ERRO: Arquivo {json_path.name} nao encontrado!")
            print("Execute sem --estrategico ou crie o arquivo config/cidades_estrategicas.json.")
            _pausar_se_interativo("\nPressione Enter para sair...")
            sys.exit(1)
    else:
        json_path = CIDADES_JSON_LOCAL
        if not json_path.exists():
            print(f"ERRO: Arquivo {json_path.name} nao encontrado na pasta do executavel!")
            print("Por favor, coloque o arquivo JSON de cidades junto com este EXE.")
            _pausar_se_interativo("\nPressione Enter para sair...")
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

    todas = [(uf, cidade) for uf, cidades in mapa.items() for cidade in cidades]
    if not todas:
        print("Nenhuma cidade encontrada com os filtros informados.")
        sys.exit(0)

    # Forçar re-processamento quando o usuário especificou quais cidades/estados quer rodar
    # ou quando usou --estrategico (intenção é sempre scraping fresco das cidades prioritárias)
    force_rerun = bool(args.forcar or args.uf or args.cidade or args.estrategico)

    def _pdf(uf, cidade):
        return PDFS_DIR / uf / (f"{cidade}-{uf}".replace(" ", "_") + ".pdf")

    # Dividir a lista COMPLETA (estável) e só depois pular quem já tem PDF — dividir
    # as pendentes faria processos que sobem em momentos diferentes se sobreporem.
    # Intercalado (e não em blocos) para cada processo pegar uma mistura de UFs.
    minha_parte = todas[parte - 1::n_partes]
    pendentes = minha_parte if force_rerun else [(uf, c) for uf, c in minha_parte if not _pdf(uf, c).exists()]

    print(f"Parte: {parte}/{n_partes}")
    print(f"Total de cidades na lista: {len(todas)}")
    print(f"A processar agora:        {len(pendentes)}")
    print(f"Mes de referencia: {args.mes}")
    print(f"Lista: {'ESTRATÉGICA (~112 cidades)' if args.estrategico else 'COMPLETA'}")
    print(f"Modo: {'Sobrescrever existentes' if force_rerun else 'Apenas novas (pular existentes)'}")
    print("Saida: pasta 'documentos/'")
    print("-" * 60, flush=True)

    # Garantir pastas de saída
    ensure_dir(DOCUMENTOS_DIR)
    ensure_dir(LOGS_DIR)
    _manter_pc_acordado()

    logger = setup_logger("amil_portable", LOGS_DIR / "bot.log")
    # O detalhe do bot vai só para o arquivo; o console fica com uma linha por cidade
    for h in list(logger.handlers):
        if type(h).__name__ == "StreamHandler":
            logger.removeHandler(h)

    driver_exe = preparar_driver_proprio(f"parte{parte}")
    if driver_exe:
        os.environ["AMIL_DRIVER_EXE"] = driver_exe

    falhas = _rodar_lista(pendentes, args.mes, logger, "1a passada")

    # Segunda passada nas que falharam, depois de um respiro para o anti-robô esfriar
    if falhas:
        print(f"\n{len(falhas)} cidades falharam. Aguardando 1 min e tentando de novo...", flush=True)
        time.sleep(60)
        falhas = _rodar_lista(falhas, args.mes, logger, "2a passada")

    caminho_falhas = LOGS_DIR / f"falhas{sufixo}.json"
    with open(caminho_falhas, "w", encoding="utf-8") as f:
        json.dump([{"uf": uf, "cidade": c} for uf, c in falhas], f, ensure_ascii=False, indent=2)

    # Gerar Planilha ao final
    print("\nGerando planilha Excel final...")
    gerar_planilha_final()

    print("\n" + "=" * 60)
    print("Processo concluído!")
    print(f"Cidades OK:    {len(pendentes) - len(falhas)}/{len(pendentes)}")
    if falhas:
        print(f"Falharam ({len(falhas)}): {', '.join(f'{c}-{uf}' for uf, c in falhas)}")
        print(f"Lista salva em {caminho_falhas}. Rode o script de novo para tentar só as que faltam.")
    print(f"Verifique a pasta: {DOCUMENTOS_DIR}")
    print("=" * 60, flush=True)

    # Pausa para o usuário ver o resultado se estiver rodando manual
    _pausar_se_interativo("\nPressione Enter para fechar...")

if __name__ == "__main__":
    main()
