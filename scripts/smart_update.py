"""
Smart Update - Atualização Inteligente de PDFs da Rede Amil

Fluxo:
1. Para cada cidade, abre o navegador e consulta o site
2. Compara a quantidade de prestadores do site com o PDF local
3. Se IGUAL → só atualiza a data do PDF (rápido, sem scrap)
4. Se DIFERENTE → aproveita o navegador JÁ ABERTO, extrai os dados e gera novo PDF
5. Gera relatório final em output/

Uso:
    python scripts/smart_update.py                      # Roda todas as cidades
    python scripts/smart_update.py --uf AC AL           # Roda apenas AC e AL
    python scripts/smart_update.py --cidade "RIO BRANCO" # Roda apenas uma cidade
    python scripts/smart_update.py --mes "Março / 2026" # Define o mês de referência
"""

import os
import sys
import json
import time
import random
from pathlib import Path
from datetime import datetime

# Adicionar o diretório raiz ao path
SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from src.utils.file_manager import (
    CIDADES_JSON, DOCS_PDFS_DIR, OUTPUT_DIR, LOGS_DIR, get_pdf_path
)
from src.utils.logger import setup_logger
from scripts.regenerar_pdfs_dezembro import (
    extrair_prestadores_do_pdf, gerar_pdf_com_referencia_fixa
)


# ============================================================
#  CONFIGURAÇÃO
# ============================================================
MES_REFERENCIA_PADRAO = "Março / 2026"


def carregar_cidades_alvo() -> dict:
    """Carrega estados e cidades do JSON oficial."""
    with open(CIDADES_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)


def contar_prestadores_pdf(uf: str, cidade: str) -> int:
    """Conta quantos prestadores tem no PDF local. Retorna -1 se não existir."""
    caminho_pdf = get_pdf_path(uf, cidade, DOCS_PDFS_DIR)
    
    if not caminho_pdf.exists():
        return -1
    
    prestadores = extrair_prestadores_do_pdf(caminho_pdf)
    if prestadores is None:
        return 0  # PDF existe mas sem especialidade
    return len(prestadores)


def verificar_e_processar_cidade(bot, cidade: str, uf: str, mes_referencia: str):
    """
    Abre o navegador UMA VEZ, consulta o site, compara com o PDF e decide:
    - Se igual: fecha o navegador e só atualiza a data
    - Se diferente: MANTÉM o navegador aberto, extrai os dados e gera PDF novo
    
    Retorna um dict com o resultado da operação.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    
    qtde_pdf = contar_prestadores_pdf(uf, cidade)
    
    try:
        # Abrir navegador e navegar até a cidade
        bot._abrir_navegador()
        
        # Passo 1 (Tipo/Plano)
        bot._passo1()
        time.sleep(random.uniform(0.3, 0.6))
        
        # Passo 2 (UF/Cidade/Bairro)
        bot._passo2(cidade)
        time.sleep(random.uniform(0.3, 0.6))
        
        # Passo 3 (Especialidade - Clínica Geral)
        try:
            bot._passo3(cidade)
        except Exception as e:
            if "Especialidade" in str(e):
                return {
                    "uf": uf, "cidade": cidade,
                    "acao": "SEM_ESPECIALIDADE",
                    "qtde_pdf": qtde_pdf, "qtde_site": 0
                }
            # Se for outro erro (ex: clique interceptado), deixa subir para o retry do loop principal
            raise Exception(f"Erro no Passo 3: {str(e)}")
        
        time.sleep(random.uniform(1.5, 2.5))
        
        # Clicar em Buscar
        btn = WebDriverWait(bot.driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "test_btn_thirdstep_submit"))
        )
        bot.driver.execute_script("arguments[0].click();", btn)
        
        # Aguardar resultados
        time.sleep(4.0)
        
        # Verificar "nenhum resultado"
        # Se chegou aqui, não houve "Nenhum resultado" detectado via texto
        # Agora vamos tentar encontrar os blocos de resultados
        # Scroll para carregar tudo (scroll infinito)
        try:
            last_height = bot.driver.execute_script("return document.body.scrollHeight")
            for _ in range(5):
                bot.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)
                new_height = bot.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            bot.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
        except:
            pass
        
        # Contar blocos de resultados
        blocos = []
        seletores = [
            (By.CLASS_NAME, "accredited-network__result"),
            (By.CSS_SELECTOR, "[class*='accredited-network']"),
        ]
        for by, sel in seletores:
            try:
                encontrados = bot.driver.find_elements(by, sel)
                encontrados = [b for b in encontrados if b.text.strip()]
                if encontrados:
                    blocos = encontrados
                    break
            except:
                continue
        
        qtde_site = len(blocos)

        # Se qtde_site for 0, também levantamos erro para retry (pois no Passo 3 garantimos Clínica Geral)
        if qtde_site == 0:
            raise Exception("Nenhum prestador encontrado no grid - possivel falha de carregamento ou bloqueio. Tentando novamente...")
        
        # ============================
        #  DECISÃO
        # ============================
        
        if qtde_pdf == -1:
            # PDF não existe → gerar do zero usando os dados JÁ CARREGADOS
            if qtde_site > 0 and blocos:
                prestadores = bot._extrair_prestadores(blocos)
                if prestadores:
                    gerar_pdf_com_referencia_fixa(
                        uf, cidade, prestadores, DOCS_PDFS_DIR,
                        mes_referencia=mes_referencia
                    )
                    return {
                        "uf": uf, "cidade": cidade,
                        "acao": "NOVO_PDF",
                        "qtde_pdf": -1, "qtde_site": len(prestadores)
                    }
            elif qtde_site == 0:
                gerar_pdf_com_referencia_fixa(
                    uf, cidade, None, DOCS_PDFS_DIR,
                    mes_referencia=mes_referencia
                )
                return {
                    "uf": uf, "cidade": cidade,
                    "acao": "SEM_ESPECIALIDADE",
                    "qtde_pdf": -1, "qtde_site": 0
                }
            
            return {
                "uf": uf, "cidade": cidade,
                "acao": "ERRO",
                "qtde_pdf": -1, "qtde_site": qtde_site,
                "erro": "Falha ao gerar PDF"
            }
        
        elif qtde_pdf == qtde_site:
            # Quantidades IGUAIS → só atualizar a data do PDF existente
            # Fecha o navegador primeiro (não precisa mais dele)
            try:
                bot._fechar_navegador_completamente()
            except:
                pass
            
            # Regenerar PDF com a nova data
            caminho_pdf = get_pdf_path(uf, cidade, DOCS_PDFS_DIR)
            prestadores_pdf = extrair_prestadores_do_pdf(caminho_pdf)
            resultado = gerar_pdf_com_referencia_fixa(
                uf, cidade, prestadores_pdf, DOCS_PDFS_DIR, mes_referencia=mes_referencia
            )
            
            if resultado:
                return {
                    "uf": uf, "cidade": cidade,
                    "acao": "DATA_ATUALIZADA",
                    "qtde_pdf": qtde_pdf, "qtde_site": qtde_site
                }
            else:
                return {
                    "uf": uf, "cidade": cidade,
                    "acao": "ERRO",
                    "qtde_pdf": qtde_pdf, "qtde_site": qtde_site,
                    "erro": "Falha ao atualizar data"
                }
        
        else:
            # Quantidades DIFERENTES → extrair dados do navegador JÁ ABERTO
            if qtde_site > 0 and blocos:
                prestadores = bot._extrair_prestadores(blocos)
                if prestadores:
                    gerar_pdf_com_referencia_fixa(
                        uf, cidade, prestadores, DOCS_PDFS_DIR,
                        mes_referencia=mes_referencia
                    )
                    return {
                        "uf": uf, "cidade": cidade,
                        "acao": "SCRAP_COMPLETO",
                        "qtde_pdf": qtde_pdf, "qtde_site": len(prestadores)
                    }
            elif qtde_site == 0:
                gerar_pdf_com_referencia_fixa(
                    uf, cidade, None, DOCS_PDFS_DIR,
                    mes_referencia=mes_referencia
                )
                return {
                    "uf": uf, "cidade": cidade,
                    "acao": "SCRAP_COMPLETO",
                    "qtde_pdf": qtde_pdf, "qtde_site": 0
                }
            
            return {
                "uf": uf, "cidade": cidade,
                "acao": "ERRO",
                "qtde_pdf": qtde_pdf, "qtde_site": qtde_site,
                "erro": "Falha no scraping"
            }
    
    except Exception as e:
        return {
            "uf": uf, "cidade": cidade,
            "acao": "ERRO",
            "qtde_pdf": qtde_pdf if 'qtde_pdf' in dir() else -1,
            "qtde_site": -1,
            "erro": str(e)
        }
    finally:
        try:
            bot._fechar_navegador_completamente()
        except OSError:
            pass  # WinError 6 esperado no Windows
        except:
            pass


def gerar_relatorio(resultados: list[dict], caminho_saida: Path):
    """Gera o relatório final do Smart Update."""
    
    iguais = [r for r in resultados if r["acao"] == "DATA_ATUALIZADA"]
    diferentes = [r for r in resultados if r["acao"] == "SCRAP_COMPLETO"]
    novos = [r for r in resultados if r["acao"] == "NOVO_PDF"]
    erros = [r for r in resultados if r["acao"] == "ERRO"]
    sem_esp = [r for r in resultados if r["acao"] == "SEM_ESPECIALIDADE"]
    
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    
    with open(caminho_saida, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write(f"RELATORIO SMART UPDATE - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")
        
        f.write(f"Total de cidades verificadas: {len(resultados)}\n")
        f.write(f"  OK  Quantidade igual (so atualizou data): {len(iguais)}\n")
        f.write(f"  >>  Quantidade diferente (scrap completo): {len(diferentes)}\n")
        f.write(f"  ++  PDFs novos gerados: {len(novos)}\n")
        f.write(f"  !!  Sem especialidade: {len(sem_esp)}\n")
        f.write(f"  XX  Erros: {len(erros)}\n\n")
        
        if iguais:
            f.write("-" * 70 + "\n")
            f.write(f"[OK] CIDADES COM DATA ATUALIZADA ({len(iguais)}):\n")
            f.write("     (Mesma quantidade - apenas mes foi atualizado)\n")
            f.write("-" * 70 + "\n")
            uf_atual = ""
            for r in sorted(iguais, key=lambda x: (x["uf"], x["cidade"])):
                if r["uf"] != uf_atual:
                    f.write(f"\n  [{r['uf']}]\n")
                    uf_atual = r["uf"]
                f.write(f"    - {r['cidade']} ({r['qtde_pdf']} prestadores)\n")
        
        if diferentes:
            f.write("\n" + "-" * 70 + "\n")
            f.write(f"[>>] CIDADES COM SCRAPING COMPLETO ({len(diferentes)}):\n")
            f.write("     (Quantidade mudou - PDF atualizado com dados novos do site)\n")
            f.write("-" * 70 + "\n")
            uf_atual = ""
            for r in sorted(diferentes, key=lambda x: (x["uf"], x["cidade"])):
                if r["uf"] != uf_atual:
                    f.write(f"\n  [{r['uf']}]\n")
                    uf_atual = r["uf"]
                f.write(f"    - {r['cidade']}: PDF={r['qtde_pdf']} -> Site={r['qtde_site']}\n")
        
        if novos:
            f.write("\n" + "-" * 70 + "\n")
            f.write(f"[++] NOVOS PDFs GERADOS ({len(novos)}):\n")
            f.write("-" * 70 + "\n")
            uf_atual = ""
            for r in sorted(novos, key=lambda x: (x["uf"], x["cidade"])):
                if r["uf"] != uf_atual:
                    f.write(f"\n  [{r['uf']}]\n")
                    uf_atual = r["uf"]
                f.write(f"    - {r['cidade']} ({r.get('qtde_site', '?')} prestadores)\n")
        
        if sem_esp:
            f.write("\n" + "-" * 70 + "\n")
            f.write(f"[!!] SEM ESPECIALIDADE ({len(sem_esp)}):\n")
            f.write("-" * 70 + "\n")
            for r in sorted(sem_esp, key=lambda x: (x["uf"], x["cidade"])):
                f.write(f"    - {r['cidade']}-{r['uf']}\n")
        
        if erros:
            f.write("\n" + "-" * 70 + "\n")
            f.write(f"[XX] ERROS ({len(erros)}):\n")
            f.write("-" * 70 + "\n")
            for r in sorted(erros, key=lambda x: (x["uf"], x["cidade"])):
                f.write(f"    - {r['cidade']}-{r['uf']}: {r.get('erro', 'Desconhecido')}\n")
        
        f.write("\n" + "=" * 70 + "\n")
        f.write("FIM DO RELATORIO\n")
        f.write("=" * 70 + "\n")
    
    return caminho_saida


# ============================================================
#  MAIN
# ============================================================
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Smart Update - Atualizacao Inteligente de PDFs")
    parser.add_argument("--uf", nargs="*", help="Filtrar por UFs (ex: --uf AC AL BA)")
    parser.add_argument("--cidade", nargs="*", help="Filtrar por cidades específicas (ex: --cidade \"RIO BRANCO\")")
    parser.add_argument("--mes", default=MES_REFERENCIA_PADRAO, help=f"Mes de referencia (padrao: {MES_REFERENCIA_PADRAO})")
    args = parser.parse_args()
    
    mes_referencia = args.mes
    filtro_ufs = [u.upper() for u in args.uf] if args.uf else None
    filtro_cidades = [c.upper() for c in args.cidade] if args.cidade else None
    
    print("=" * 60)
    print("  SMART UPDATE - Atualizacao Inteligente de PDFs")
    print("=" * 60)
    print(f"  Mes de referencia: {mes_referencia}")
    if filtro_ufs:
        print(f"  Filtrando UFs: {', '.join(filtro_ufs)}")
    if filtro_cidades:
        print(f"  Filtrando Cidades: {', '.join(filtro_cidades)}")
    print()
    
    mapa = carregar_cidades_alvo()
    
    if filtro_ufs:
        mapa = {uf: cidades for uf, cidades in mapa.items() if uf in filtro_ufs}
    
    if filtro_cidades:
        nova_mapa = {}
        for uf, cidades in mapa.items():
            cidades_filtradas = [c for c in cidades if c.upper() in filtro_cidades]
            if cidades_filtradas:
                nova_mapa[uf] = cidades_filtradas
        mapa = nova_mapa
    
    total_cidades = sum(len(c) for c in mapa.values())
    print(f"  Total de cidades a verificar: {total_cidades}")
    print()
    
    logger = setup_logger("smart_update", LOGS_DIR / "smart_update.log")
    
    from src.scraper.amil_scraper import AmilBot
    
    resultados = []
    contador = 0
    
    for uf, cidades in mapa.items():
        print(f"\n  [{uf}] - {len(cidades)} cidades")
        print("-" * 40)
        
        for cidade in cidades:
            contador += 1
            progresso = f"[{contador}/{total_cidades}]"
            
            print(f"  {progresso} {cidade}...", end=" ", flush=True)
            
            # Lógica de retry interno por cidade
            tentativa = 0
            max_tentativas = 3
            resultado = None
            
            while tentativa < max_tentativas:
                tentativa += 1
                try:
                    bot = AmilBot(uf, pasta_base=DOCS_PDFS_DIR, logger=logger)
                    resultado = verificar_e_processar_cidade(bot, cidade, uf, mes_referencia)
                    
                    if resultado["acao"] != "ERRO":
                        break # Sucesso
                    
                    if tentativa < max_tentativas:
                        print(f"(tentativa {tentativa} falhou, tentando novamente...)", end=" ", flush=True)
                        time.sleep(5) # Espera técnica antes de tentar de novo
                except Exception as e:
                    if tentativa == max_tentativas:
                        resultado = {
                            "uf": uf, "cidade": cidade,
                            "acao": "ERRO", "qtde_pdf": -1, "qtde_site": -1,
                            "erro": str(e)
                        }
            
            resultados.append(resultado)
            
            acao = resultado["acao"]
            if acao == "DATA_ATUALIZADA":
                print(f"OK (igual: {resultado['qtde_site']} prestadores, data atualizada)")
            elif acao == "SCRAP_COMPLETO":
                print(f"ATUALIZADO (PDF={resultado['qtde_pdf']} -> Site={resultado['qtde_site']})")
            elif acao == "NOVO_PDF":
                print(f"NOVO ({resultado['qtde_site']} prestadores)")
            elif acao == "SEM_ESPECIALIDADE":
                print(f"SEM ESPECIALIDADE")
            elif acao == "ERRO":
                print(f"ERRO: {resultado.get('erro', '?')}")
            
            # Cooldown entre cidades
            time.sleep(random.uniform(2.0, 4.0))
    
    # Gerar relatório
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_relatorio = OUTPUT_DIR / f"smart_update_{timestamp}.txt"
    gerar_relatorio(resultados, caminho_relatorio)
    
    print("\n" + "=" * 60)
    print("  RESUMO FINAL")
    print("=" * 60)
    
    iguais = len([r for r in resultados if r["acao"] == "DATA_ATUALIZADA"])
    diferentes = len([r for r in resultados if r["acao"] == "SCRAP_COMPLETO"])
    novos = len([r for r in resultados if r["acao"] == "NOVO_PDF"])
    erros = len([r for r in resultados if r["acao"] == "ERRO"])
    
    print(f"  Data atualizada (sem mudanca): {iguais}")
    print(f"  Scrap completo (mudou quantidade): {diferentes}")
    print(f"  PDFs novos: {novos}")
    print(f"  Erros: {erros}")
    print(f"\n  Relatorio salvo em: {caminho_relatorio}")
    print("=" * 60)


if __name__ == "__main__":
    main()
