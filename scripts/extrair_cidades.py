"""
Script para extrair automaticamente a lista de cidades do site da Amil.

Este script:
1. Acessa o site da Amil
2. Navega até a página de busca avançada
3. Para cada estado, extrai todas as cidades disponíveis
4. Atualiza o arquivo estados_cidades_amil.json

Uso:
    python scripts/extrair_cidades.py

Tempo estimado: ~10-15 minutos (dependendo da velocidade da conexão)
"""

import json
import random
import time
from pathlib import Path
from typing import Dict, List
import sys

# Adicionar raiz do projeto ao path
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from src.scraper.anti_bot import build_chrome_options, apply_stealth
from src.scraper.navegacao import aguardar_pagina_carregar
from src.utils.delays import delay_humano

# URL do site
URL_BUSCA = "https://www.amil.com.br/institucional/#/servicos/saude/rede-credenciada/amil/busca-avancada"

# Lista de todos os estados brasileiros
ESTADOS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO"
]


def extrair_cidades_do_site() -> Dict[str, List[str]]:
    """
    Extrai todas as cidades disponíveis do site da Amil, organizadas por estado.
    
    Returns:
        Dict com chave sendo UF e valor sendo lista de cidades
    """
    print("🚀 Iniciando extração de cidades do site da Amil...")
    
    # Configurar Chrome
    ua = random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    ])
    
    options = build_chrome_options(user_agent=ua, proxy=None)
    options.add_argument("--headless")  # Rodar em background
    options.add_argument("--window-size=1920,1080")
    
    driver = None
    resultado = {}
    
    try:
        print("🌐 Abrindo navegador...")
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=145)
        wait = WebDriverWait(driver, 25)
        wait_dropdown = WebDriverWait(driver, 15)
        
        # Aplicar stealth
        apply_stealth(driver)
        
        # Carregar página
        print(f"📄 Carregando página: {URL_BUSCA}")
        driver.get(URL_BUSCA)
        aguardar_pagina_carregar(driver, wait)
        time.sleep(random.uniform(3.0, 5.0))
        
        print("✅ Página carregada!")
        
        # PASSO 1: Selecionar DENTAL e Amil Dental Nacional
        print("\n📋 Passo 1: Selecionando DENTAL e Amil Dental Nacional...")
        
        # Clicar no dropdown de tipo
        wait_dropdown.until(EC.element_to_be_clickable((By.CLASS_NAME, "rw-dropdown-list-input"))).click()
        delay_humano(0.2, 0.3)
        
        # Selecionar DENTAL
        wait_dropdown.until(EC.element_to_be_clickable((By.XPATH, "//li[text()='DENTAL']"))).click()
        delay_humano(0.2, 0.3)
        
        # Clicar no segundo select (plano)
        selects = wait_dropdown.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "rw-btn-select")))
        selects[1].click()
        delay_humano(0.2, 0.3)
        
        # Selecionar Amil Dental Nacional
        plano = wait_dropdown.until(EC.presence_of_element_located((By.XPATH, "//li[text()='Amil Dental Nacional']")))
        driver.execute_script("arguments[0].click();", plano)
        delay_humano(0.2, 0.3)
        
        # Clicar em continuar
        btn = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "test_btn_firststep_submit")))
        driver.execute_script("arguments[0].click();", btn)
        delay_humano(0.3, 0.5)
        
        print("✅ Passo 1 concluído!\n")
        
        # PASSO 2: Para cada estado, extrair cidades
        print("🔍 Iniciando extração de cidades por estado...\n")
        
        for idx, uf in enumerate(ESTADOS, 1):
            print(f"[{idx}/{len(ESTADOS)}] Processando {uf}...")
            
            try:
                # Clicar no dropdown de Estado
                estado_btn = wait_dropdown.until(
                    EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Estado')]/following::button[1]"))
                )
                estado_btn.click()
                delay_humano(0.2, 0.3)
                
                # Selecionar o estado
                uf_option = wait_dropdown.until(EC.element_to_be_clickable((By.XPATH, f"//li[text()='{uf}']")))
                uf_option.click()
                delay_humano(0.3, 0.5)
                
                # Clicar no dropdown de Município para ver as opções
                muni_btn = wait_dropdown.until(
                    EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Municipio')]/following::button[1]"))
                )
                muni_btn.click()
                delay_humano(0.3, 0.5)
                
                # Aguardar lista de cidades aparecer
                wait_dropdown.until(EC.presence_of_element_located((By.XPATH, "//ul[contains(@id,'listbox')]//li")))
                
                # Extrair todas as cidades da lista
                cidade_elements = driver.find_elements(By.XPATH, "//ul[contains(@id,'listbox')]//li")
                cidades = []
                
                for elem in cidade_elements:
                    cidade_texto = elem.text.strip()
                    if cidade_texto and cidade_texto.upper() != "TODOS OS MUNICÍPIOS":
                        cidades.append(cidade_texto.upper())
                
                # Fechar dropdown clicando novamente no botão ou pressionando ESC
                try:
                    muni_btn.click()
                except:
                    # Se não conseguir clicar, tentar ESC
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                delay_humano(0.2, 0.3)
                
                resultado[uf] = sorted(cidades)  # Ordenar alfabeticamente
                print(f"   ✅ {uf}: {len(cidades)} cidades encontradas")
                
                # Cooldown entre estados
                if idx < len(ESTADOS):
                    time.sleep(random.uniform(1.0, 2.0))
                    
            except TimeoutException as e:
                print(f"   ⚠️ Timeout ao processar {uf}: {e}")
                resultado[uf] = []
            except Exception as e:
                print(f"   ❌ Erro ao processar {uf}: {e}")
                resultado[uf] = []
        
        print("\n✅ Extração concluída!")
        return resultado
        
    except Exception as e:
        print(f"\n❌ Erro fatal durante extração: {e}")
        return resultado
        
    finally:
        if driver:
            print("\n🔒 Fechando navegador...")
            try:
                driver.quit()
            except:
                pass


def salvar_json(cidades_por_estado: Dict[str, List[str]], caminho_json: Path) -> None:
    """
    Salva o resultado no arquivo JSON.
    
    Args:
        cidades_por_estado: Dict com UF como chave e lista de cidades como valor
        caminho_json: Caminho do arquivo JSON para salvar
    """
    print(f"\n💾 Salvando resultado em {caminho_json}...")
    
    # Criar backup do arquivo antigo se existir
    if caminho_json.exists():
        backup_path = caminho_json.with_suffix('.json.backup')
        print(f"📦 Criando backup: {backup_path}")
        import shutil
        shutil.copy2(caminho_json, backup_path)
    
    # Salvar novo arquivo
    with open(caminho_json, 'w', encoding='utf-8') as f:
        json.dump(cidades_por_estado, f, ensure_ascii=False, indent=2)
    
    # Contar total de cidades
    total = sum(len(cidades) for cidades in cidades_por_estado.values())
    print(f"✅ Arquivo salvo! Total: {total} cidades em {len(cidades_por_estado)} estados")


def main():
    """Função principal."""
    print("=" * 60)
    print("🔍 EXTRAÇÃO DE CIDADES - SITE AMIL")
    print("=" * 60)
    print()
    
    # Caminho do arquivo JSON
    from src.utils.file_manager import CIDADES_JSON
    caminho_json = CIDADES_JSON
    
    # Extrair cidades
    cidades_por_estado = extrair_cidades_do_site()
    
    # Verificar se conseguiu extrair algo
    if not cidades_por_estado or sum(len(c) for c in cidades_por_estado.values()) == 0:
        print("\n❌ Nenhuma cidade foi extraída. Verifique sua conexão e tente novamente.")
        return
    
    # Salvar resultado
    salvar_json(cidades_por_estado, caminho_json)
    
    # Estatísticas
    print("\n" + "=" * 60)
    print("📊 ESTATÍSTICAS")
    print("=" * 60)
    total_cidades = sum(len(cidades) for cidades in cidades_por_estado.values())
    print(f"Total de estados: {len(cidades_por_estado)}")
    print(f"Total de cidades: {total_cidades}")
    print(f"\nCidades por estado:")
    for uf in sorted(cidades_por_estado.keys()):
        print(f"  {uf}: {len(cidades_por_estado[uf])}")
    print("=" * 60)
    print("\n✅ Processo concluído com sucesso!")


if __name__ == "__main__":
    main()

