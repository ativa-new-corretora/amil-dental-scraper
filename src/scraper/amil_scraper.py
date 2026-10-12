import random
import time
import os
import shutil
from pathlib import Path
from typing import Any
import tempfile  # 🔥 NOVO

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.utils.delays import delay_humano
from src.utils.file_manager import get_pdf_path, REDE_COMPLETA_DIR
from src.scraper.anti_bot import (
    build_chrome_options,
    apply_stealth,
    detectar_versao_chrome,
    user_agent_para_versao,
    janela_oculta,
)
from src.scraper.navegacao import (
    aguardar_pagina_carregar,
)

from src.pdf.gerador_pdf import gerar_pdf_prestadores, gerar_pdf_sem_especialidade


# ============================================================
#  PROXIES OPCIONAIS (não usados se lista estiver vazia)
# ============================================================
PROXIES: list[str] = []


# ============================================================
#              BOT AMIL — ESTÁVEL FINAL (V.B)
# ============================================================
class AmilBot:
    def __init__(
        self,
        uf: str,
        pasta_base: Path | None = None,
        logger=None,
        proxies: list[str] | None = None,
        stop_flag=None,  # 🔥 NOVO
    ) -> None:

        self.uf = uf
        self.pasta_base = pasta_base or REDE_COMPLETA_DIR
        self.logger = logger
        self.stop_flag = stop_flag  # 🔥 NOVO
        self.gerar_pdf_vazio = True  # _passo3 gera o PDF "sem especialidade" (fluxo do main.py)

        self.driver = None
        self.wait: WebDriverWait | None = None
        self.wait_dropdown: WebDriverWait | None = None

        self.resultado_por_cidade = []
        self.cidades_com_erro = {}

        self.proxies = proxies if proxies is not None else PROXIES
        
        # Atributos internos
        self._perfil_temp = None
        self._cidades_processadas_uf = 0
        self._current_city = None

    # ---------------------- utils ----------------------

    def _log(self, msg: str) -> None:
        if self.logger:
            self.logger.info(msg)
        else:
            print(msg)

    def _sleep(self, seconds: float) -> None:
        """Dorme por X segundos, mas acorda se stop_flag for setado."""
        if self.stop_flag:
            self.stop_flag.wait(timeout=seconds)
        else:
            time.sleep(seconds)

    def _escolher_proxy(self) -> str | None:
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    def _cooldown(self) -> None:
        """Cooldown entre cidades para parecer humano."""
        # 🔥 OTIMIZADO: Cooldown reduzido - perfil único garante fingerprint diferente
        # Base: 3-6 segundos (reduzido de 5-10s)
        cooldown_base = 2.0
        
        # Cooldown progressivo: aumenta com o número de cidades processadas
        if self._cidades_processadas_uf > 0:
            cooldown_extra = min(self._cidades_processadas_uf * 0.15, 8)  # Reduzido de 0.2 para 0.15, max 8s
            cooldown_time = cooldown_base + cooldown_extra
        else:
            cooldown_time = cooldown_base
        
        self._log(f"⏳ Cooldown de {cooldown_time:.1f}s entre cidades...")
        self._sleep(cooldown_time)

        # Não precisa fazer scroll se não há driver (já foi fechado)
        if not self.driver:
            return

        # movimentos aleatórios mais realistas
        for _ in range(random.randint(3, 6)):
            try:
                if self.stop_flag and self.stop_flag.is_set(): break
                x = random.randint(0, 800)
                y = random.randint(0, 600)
                self.driver.execute_script(f"window.scrollTo({x}, {y});")
                self._sleep(random.uniform(0.3, 0.7))
            except:
                pass

    def _mover_mouse_curva(self, x: float, y: float) -> None:
        """
        Leva o ponteiro até (x, y) — coordenadas do viewport — por uma curva de
        Bézier com dezenas de pontos e aceleração/desaceleração.
        O sensor do Akamai Bot Manager no site da Amil pontua a sessão pelos
        mousemove: 2 saltos retos por clique (o que o ActionChains faz) é
        assinatura de robô e leva a 403 na busca de prestadores.
        """
        from selenium.webdriver.common.actions.action_builder import ActionBuilder

        largura, altura = self.driver.execute_script(
            "return [window.innerWidth, window.innerHeight];"
        )

        def dentro(px, py):
            return (min(max(int(px), 1), largura - 2), min(max(int(py), 1), altura - 2))

        x0, y0 = getattr(self, "_mouse_pos", None) or (
            random.randint(50, largura // 2), random.randint(50, altura // 2)
        )
        x, y = dentro(x, y)
        dx, dy = x - x0, y - y0
        c1 = (x0 + dx * random.uniform(0.2, 0.4) + random.randint(-90, 90),
              y0 + dy * random.uniform(0.2, 0.4) + random.randint(-90, 90))
        c2 = (x0 + dx * random.uniform(0.6, 0.8) + random.randint(-60, 60),
              y0 + dy * random.uniform(0.6, 0.8) + random.randint(-60, 60))

        passos = random.randint(22, 38)
        ab = ActionBuilder(self.driver, duration=random.randint(8, 18))
        for i in range(1, passos + 1):
            t = i / passos
            t = t * t * (3 - 2 * t)  # ease-in-out
            bx = (1 - t) ** 3 * x0 + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t ** 2 * c2[0] + t ** 3 * x
            by = (1 - t) ** 3 * y0 + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t ** 2 * c2[1] + t ** 3 * y
            ab.pointer_action.move_to_location(*dentro(bx, by))
        ab.perform()
        self._mouse_pos = (x, y)

    def _passear_mouse(self, vezes: int | None = None) -> None:
        """Movimentos à toa pela página, como alguém lendo antes de clicar."""
        try:
            largura, altura = self.driver.execute_script(
                "return [window.innerWidth, window.innerHeight];"
            )
            for _ in range(vezes or random.randint(1, 3)):
                self._mover_mouse_curva(random.randint(80, largura - 80), random.randint(80, altura - 80))
                self._sleep(random.uniform(0.2, 0.7))
        except Exception:
            pass

    def _clicar_humano(self, elemento, desvio: int = 4) -> None:
        """
        Move o mouse em curva até o elemento e clica — sem execute_script.
        Gera a cadeia completa de eventos do mouse que um humano produziria:
        mousemove (vários) → mouseover → mouseenter → mousedown → mouseup → click.
        """
        from selenium.webdriver.common.action_chains import ActionChains

        # Rolar suavemente até o elemento ficar visível (DOM, não JS click)
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});",
                elemento
            )
            self._sleep(random.uniform(0.3, 0.5))
        except Exception:
            pass

        try:
            js_rect = (
                "const r = arguments[0].getBoundingClientRect();"
                "return [r.left, r.top, r.width, r.height];"
            )
            # Em listas longas (157 cidades em MG, 239 em SP) a rolagem suave demora mais que
            # um tempo fixo: medir no meio dela fazia o clique cair fora da cidade, nada era
            # selecionado e o menu de Bairro nunca liberava. Esperar a posição parar de mudar.
            r = self.driver.execute_script(js_rect, elemento)
            for _ in range(20):
                self._sleep(0.15)
                r2 = self.driver.execute_script(js_rect, elemento)
                if r2 == r:
                    break
                r = r2

            alvo_x = r[0] + r[2] / 2 + random.uniform(-min(desvio, r[2] / 4), min(desvio, r[2] / 4))
            alvo_y = r[1] + r[3] / 2 + random.uniform(-min(desvio, r[3] / 4), min(desvio, r[3] / 4))

            # O ponto do clique precisa estar sobre o próprio elemento (não coberto/fora da lista)
            no_alvo = self.driver.execute_script(
                "const e = document.elementFromPoint(arguments[1], arguments[2]);"
                "return !!e && (e === arguments[0] || arguments[0].contains(e));",
                elemento, alvo_x, alvo_y,
            )
            if not no_alvo:
                raise Exception("ponto do clique fora do elemento")

            self._mover_mouse_curva(alvo_x, alvo_y)
            ActionChains(self.driver).pause(random.uniform(0.08, 0.2)).click().perform()
            return
        except Exception:
            pass  # cai no clique antigo abaixo

        try:
            actions = ActionChains(self.driver)
            # Primeiro move para ponto levemente deslocado (simula trajetória humana)
            actions.move_to_element_with_offset(
                elemento,
                random.randint(-desvio, desvio),
                random.randint(-desvio, desvio)
            )
            actions.pause(random.uniform(0.06, 0.14))
            # Depois centraliza no elemento
            actions.move_to_element(elemento)
            actions.pause(random.uniform(0.05, 0.10))
            actions.click()
            actions.perform()
        except Exception:
            # Fallback 1: clique nativo do Selenium (ainda gera eventos de mouse)
            try:
                elemento.click()
            except Exception:
                # Fallback 2: JS apenas como último recurso
                self.driver.execute_script("arguments[0].click();", elemento)

    # Verificar se há bloqueio/captcha
    def _verificar_bloqueio(self) -> bool:
        """Verifica se o site bloqueou ou pediu captcha."""
        try:
            # Verificar textos comuns de bloqueio
            bloqueios = [
                "captcha",
                "verificação",
                "bloqueado",
                "suspenso",
                "acesso negado",
                "too many requests",
                "rate limit",
            ]
            
            page_text = self.driver.page_source.lower()
            for bloqueio in bloqueios:
                if bloqueio in page_text:
                    self._log(f"⚠️ Possível bloqueio detectado: {bloqueio}")
                    return True
            
            # Verificar se há iframe de captcha
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    src = iframe.get_attribute("src") or ""
                    if "captcha" in src.lower() or "recaptcha" in src.lower():
                        self._log("⚠️ Captcha detectado!")
                        return True
            except:
                pass
                
            return False
        except:
            return False

    # 🔥 NOVO — Limpar completamente dados do navegador
    def _limpar_dados_navegador(self):
        """Limpa todos os dados do navegador antes de fechar."""
        if not self.driver:
            return
        
        try:
            # Limpar cookies
            self.driver.delete_all_cookies()
            self._log("🧹 Cookies limpos")
        except:
            pass
        
        try:
            # Limpar localStorage
            self.driver.execute_script("window.localStorage.clear();")
        except:
            pass
        
        try:
            # Limpar sessionStorage
            self.driver.execute_script("window.sessionStorage.clear();")
        except:
            pass
        
        try:
            # Limpar IndexedDB
            self.driver.execute_script("""
                if (window.indexedDB) {
                    indexedDB.databases().then(dbs => {
                        dbs.forEach(db => indexedDB.deleteDatabase(db.name));
                    });
                }
            """)
        except:
            pass

    def _fechar_navegador_completamente(self):
        """Fecha o navegador e limpa completamente todos os dados."""
        import shutil
        
        if self.driver:
            try:
                # Limpar dados do navegador
                self._limpar_dados_navegador()
                
                # Fechar navegador
                self.driver.quit()
                
                # 🔥 OTIMIZADO: Aguardar processo terminar (reduzido)
                self._sleep(random.uniform(1.0, 2.0))  # Reduzido de 2-4s para 1-2s
                
            except Exception as e:
                self._log(f"⚠️ Erro ao fechar navegador: {e}")
            finally:
                self.driver = None
                self.wait = None
                self.wait_dropdown = None
        
        # 🔥 NOVO — Limpar perfil temporário
        if hasattr(self, '_perfil_temp') and self._perfil_temp:
            try:
                import shutil
                if os.path.exists(self._perfil_temp):
                    shutil.rmtree(self._perfil_temp, ignore_errors=True)
                    self._log("🧹 Perfil temporário removido")
            except Exception as e:
                self._log(f"⚠️ Erro ao remover perfil: {e}")
            finally:
                self._perfil_temp = None

    # ---------------------- contexto ----------------------

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

    # ------------------------------------------------------
    #         ABRIR NAVEGADOR — SEMPRE LIMPO POR CIDADE
    # ------------------------------------------------------
    def _abrir_navegador(self):
        import tempfile
        import os
        
        # 🔥 CORREÇÃO — Tentar sem perfil temporário primeiro (pode estar causando problema)
        # Se continuar dando problema, podemos voltar a usar perfil temporário
        usar_perfil_temp = False  # 🔥 DESABILITADO temporariamente para testar
        
        if usar_perfil_temp:
            perfil_temp = tempfile.mkdtemp(prefix="chrome_profile_")
        else:
            perfil_temp = None
        
        # UA e version_main seguem o Chrome realmente instalado — versão diferente
        # gera mismatch detectável (UA x navigator.userAgentData) e falha no driver
        versao_chrome = detectar_versao_chrome()
        ua = user_agent_para_versao(versao_chrome)

        proxy = self._escolher_proxy()
        if proxy:
            self._log(f"🌐 Usando proxy: {proxy}")
        else:
            self._log("🌐 Conexão direta (sem proxy).")

        def get_fresh_options():
            options = build_chrome_options(user_agent=ua, proxy=proxy)
            if usar_perfil_temp and perfil_temp:
                options.add_argument(f"--user-data-dir={perfil_temp}")

            # Variação no viewport para parecer mais humano
            v_width = random.randint(1280, 1920)
            v_height = random.randint(720, 1080)
            options.add_argument(f"--window-size={v_width},{v_height}")
            return options

        # AMIL_DRIVER_EXE: cópia exclusiva do chromedriver (ver preparar_driver_proprio)
        driver_fixo = os.getenv("AMIL_DRIVER_EXE")
        paralelo = os.getenv("AMIL_PARALELO") == "1"

        def criar_driver(com_versao: bool):
            kwargs = {"options": get_fresh_options(), "use_subprocess": True}
            if com_versao and versao_chrome:
                kwargs["version_main"] = versao_chrome
            if com_versao and driver_fixo and os.path.exists(driver_fixo):
                kwargs["driver_executable_path"] = driver_fixo
            return uc.Chrome(**kwargs)

        # Funcoes de limpeza no fallback
        def limpar_processos_chrome():
            if paralelo:
                return  # mataria os navegadores dos outros processos
            try:
                import subprocess
                # Mata apenas o chromedriver do UC para não fechar o Chrome pessoal do usuário, 
                # ajudando a resolver 'invalid session id'
                subprocess.run(["taskkill", "/F", "/IM", "undetected_chromedriver.exe", "/T"], 
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except:
                pass

        def limpar_cache_uc():
            if paralelo:
                return  # apagaria o driver em uso pelos outros processos
            try:
                import shutil
                uc_dir = Path(os.getenv("APPDATA", "")) / "undetected_chromedriver"
                if uc_dir.exists():
                    shutil.rmtree(uc_dir, ignore_errors=True)
                    self._log("🧹 Cache do undetected_chromedriver limpo.")
            except:
                pass

        try:
            self._log(f"🚀 Inicializando Chrome (versão detectada: {versao_chrome or 'desconhecida'})...")
            self.driver = criar_driver(com_versao=True)
        except Exception as e:
            self._log(f"⚠️ Erro na inicialização do Chrome v{versao_chrome}: {e}")
            self._log("🔄 Tentativa 2: Limpando processos órfãos e tentando novamente...")

            limpar_processos_chrome()
            limpar_cache_uc()
            self._sleep(2.0)

            try:
                self.driver = criar_driver(com_versao=True)
            except Exception as e2:
                self._log(f"⚠️ Erro na segunda tentativa: {e2}")
                self._log("🔄 Tentativa final: Deixando UC resolver sem restrições...")
                limpar_processos_chrome()
                self.driver = criar_driver(com_versao=False)
        
        self.wait = WebDriverWait(self.driver, 25)
        self.wait_dropdown = WebDriverWait(self.driver, 15)

        # Guardar caminho do perfil para limpar depois
        self._perfil_temp = perfil_temp

        # CRÍTICO: stealth ANTES de driver.get() — Page.addScriptToEvaluateOnNewDocument
        # precisa ser registrado antes que qualquer página carregue para funcionar.
        try:
            apply_stealth(self.driver)
        except Exception as e:
            self._log(f"⚠️ Erro ao aplicar stealth: {e}")

        self._sleep(1.5)

        # 🔥 CORREÇÃO — Tentar carregar a página com retry
        max_tentativas_carregar = 3
        pagina_carregou = False
        
        for tentativa in range(max_tentativas_carregar):
            try:
                self._log(f"🌐 Tentando carregar página (tentativa {tentativa + 1}/{max_tentativas_carregar})...")
                
                self.driver.get(
                    "https://www.amil.com.br/institucional/#/servicos/saude/rede-credenciada/amil/busca-avancada"
                )

                # 🔥 CORREÇÃO — Melhorar verificação de carregamento para SPAs
                aguardar_pagina_carregar(self.driver, self.wait)
                
                # 🔥 NOVO — Aguardar mais tempo para JavaScript carregar
                self._sleep(2.0)
                
                # 🔥 CORREÇÃO — Verificar se a página não está em branco
                page_source = self.driver.page_source
                
                # Verificar tamanho mínimo
                if len(page_source) < 1000:
                    self._log(f"⚠️ Página muito pequena ({len(page_source)} chars), tentando recarregar...")
                    if tentativa < max_tentativas_carregar - 1:
                        # 🔥 NOVO — Pausa estratégica na segunda tentativa
                        if tentativa == 1:  # Segunda tentativa (índice 1)
                            from src.utils.delays import pausa_estrategica
                            self._log("⚠️ Segunda tentativa falhou - aplicando pausa estratégica...")
                            pausa_estrategica(self.stop_flag)
                        self._sleep(random.uniform(2.0, 4.0))
                        continue
                    else:
                        raise Exception("Página não carregou corretamente (muito pequena)")
                
                # Verificar se há conteúdo esperado
                page_lower = page_source.lower()
                if "amil" not in page_lower and "rede" not in page_lower and "credenciada" not in page_lower:
                    self._log("⚠️ Conteúdo da página não parece correto, tentando recarregar...")
                    if tentativa < max_tentativas_carregar - 1:
                        # 🔥 NOVO — Pausa estratégica na segunda tentativa
                        if tentativa == 1:  # Segunda tentativa (índice 1)
                            from src.utils.delays import pausa_estrategica
                            self._log("⚠️ Segunda tentativa falhou - aplicando pausa estratégica...")
                            pausa_estrategica(self.stop_flag)
                        self._sleep(random.uniform(2.0, 4.0))
                        continue
                    else:
                        raise Exception("Conteúdo da página não parece correto")
                
                # Verificar se há body com conteúdo
                try:
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text
                    if len(body_text.strip()) < 50:
                        self._log("⚠️ Body da página está vazio, tentando recarregar...")
                        if tentativa < max_tentativas_carregar - 1:
                            # 🔥 NOVO — Pausa estratégica na segunda tentativa
                            if tentativa == 1:  # Segunda tentativa (índice 1)
                                from src.utils.delays import pausa_estrategica
                                self._log("⚠️ Segunda tentativa falhou - aplicando pausa estratégica...")
                                pausa_estrategica(self.stop_flag)
                            self._sleep(random.uniform(2.0, 4.0))
                            continue
                except:
                    pass
                
                # Se chegou aqui, página carregou corretamente
                pagina_carregou = True
                self._log(f"✅ Página carregada com sucesso ({len(page_source)} chars)")
                break
                
            except Exception as e:
                self._log(f"⚠️ Erro ao carregar página (tentativa {tentativa + 1}): {e}")
                if tentativa < max_tentativas_carregar - 1:
                    # 🔥 NOVO — Pausa estratégica na segunda tentativa
                    if tentativa == 1:  # Segunda tentativa (índice 1)
                        from src.utils.delays import pausa_estrategica
                        self._log("⚠️ Segunda tentativa falhou - aplicando pausa estratégica...")
                        pausa_estrategica(self.stop_flag)
                    self._log("🔄 Tentando recarregar...")
                    self._sleep(random.uniform(3.0, 5.0))
                else:
                    raise Exception(f"Falha ao carregar página após {max_tentativas_carregar} tentativas: {e}")
        
        if not pagina_carregou:
            raise Exception("Página não carregou corretamente após todas as tentativas")
        
        self._sleep(1.5)

        try:
            self.wait.until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            ).click()
            time.sleep(random.uniform(1.0, 2.0))
        except:
            pass

        # Maximizar traria a janela oculta de volta para a tela
        if not janela_oculta():
            try:
                self.driver.maximize_window()
                time.sleep(random.uniform(1.0, 2.0))
            except:
                pass
        
        # Verificar bloqueio após abrir
        if self._verificar_bloqueio():
            self._log("⚠️ Bloqueio detectado após abrir navegador!")
            raise Exception("Site bloqueou o acesso")

    # ------------------------------------------------------
    #                   PROCESSAR CIDADE
    # ------------------------------------------------------
    def processar_cidade(self, cidade: str, _retries: int = 0) -> None:
        if self.stop_flag and self.stop_flag.is_set():
            self._log("⛔ Execução interrompida pelo usuário")
            raise Exception("Execução interrompida pelo usuário")

        caminho_pdf = get_pdf_path(self.uf, cidade, self.pasta_base)
        if caminho_pdf.exists():
            self._log(f"⏭️ PDF já existe — pulando {cidade}-{self.uf}")
            # 🔥 CORREÇÃO — Pular instantaneamente sem cooldown desnecessário
            return

        self._log(f"\n🔄 Processando {cidade}-{self.uf}")
        self._current_city = cidade

        # 🔥 OTIMIZADO: Cooldown maior antes de abrir navegador
        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        # 🔥 OTIMIZADO: Cooldown reduzido antes de abrir navegador
        # Cooldown antes de abrir navegador
        self._sleep(2.0)  # Reduzido de 2-5s para 2s

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        # navegador limpo sempre
        self._abrir_navegador()
        
        # Verificar bloqueio após abrir
        if self._verificar_bloqueio():
            self._log("⚠️ Bloqueio detectado! Aguardando muito mais tempo...")
            self._sleep(random.uniform(10, 20))  # Reduzido de 60-120s para 10-20s
            if self._verificar_bloqueio():
                raise Exception("Site bloqueou o acesso após espera")

        try:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            
            self._passo1()
            time.sleep(random.uniform(0.3, 0.6))
            
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            
            self._passo2(cidade)
            time.sleep(random.uniform(0.3, 0.6))
            
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            
            self._passo3(cidade)
            self._sleep(random.uniform(1.0, 2.0))
            
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            
            prestadores = self._capturar()

            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")

            # VALIDAÇÃO: só gera PDF se houver prestadores válidos
            if prestadores and len(prestadores) > 0:
                gerar_pdf_prestadores(self.uf, cidade, prestadores, self.pasta_base)
                self._log(f"📄 PDF gerado: {cidade}-{self.uf} ({len(prestadores)} prestadores)")
                
                self.resultado_por_cidade.append({
                    "cidade": cidade,
                    "uf": self.uf,
                    "prestadores": len(prestadores)
                })
                
                # 🔥 NOVO — Incrementar contador para cooldown progressivo
                if not hasattr(self, '_cidades_processadas_uf'):
                    self._cidades_processadas_uf = 0
                self._cidades_processadas_uf += 1
            else:
                self._log(f"⚠️ Nenhum prestador válido encontrado em {cidade}-{self.uf}. Tentando novamente...")
                raise Exception("Nenhum prestador válido encontrado")

        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                self._log("⛔ Execução interrompida pelo usuário")
                raise Exception("Execução interrompida pelo usuário")
            
            # 🔥 NOVO — Verificar se é exceção de especialidade não encontrada
            if "Especialidade não encontrada" in str(e):
                self._log(f"✅ PDF vazio gerado para {cidade}-{self.uf} (sem especialidade)")
                
                # Adicionar ao resultado com 0 prestadores
                self.resultado_por_cidade.append({
                    "cidade": cidade,
                    "uf": self.uf,
                    "prestadores": 0
                })
                
                # 🔥 NOVO — Incrementar contador para cooldown progressivo
                if not hasattr(self, '_cidades_processadas_uf'):
                    self._cidades_processadas_uf = 0
                self._cidades_processadas_uf += 1
                
                # Fechar navegador normalmente
                if self.driver:
                    try:
                        self._limpar_dados_navegador()
                        self.driver.quit()
                    except:
                        pass
                    finally:
                        self.driver = None
                        self.wait = None
                        self.wait_dropdown = None
                
                # Retornar normalmente (não fazer retry)
                return
            
            # Se não for exceção de especialidade, tratar como erro normal
            self._log(f"⚠️ Falha em {cidade}-{self.uf}: {e}")
            self._log("🛑 Fechando navegador antes do cooldown...")

            self._fechar_navegador_completamente()

            # Shadow block: espera maior + limpeza agressiva de processos Chrome
            eh_shadow = "prestador" in str(e).lower() or "resultado" in str(e).lower()
            cooldown = random.uniform(30, 45) if eh_shadow else random.uniform(10, 20)
            self._log(f"⏳ {'Shadow block detectado — ' if eh_shadow else ''}Aguardando {cooldown:.1f}s...")
            self._sleep(cooldown)

            if _retries < 2:  # máx 3 tentativas totais (0, 1, 2)
                self._log(f"🔁 Tentativa {_retries + 2}/3 — reabrindo navegador...")
                try:
                    return self.processar_cidade(cidade, _retries + 1)
                except Exception as e2:
                    self._log(f"❌ Falha definitiva em {cidade}-{self.uf}: {e2}")
            else:
                self._log(f"❌ Falha definitiva em {cidade}-{self.uf} após 3 tentativas: {e}")
                self.cidades_com_erro.setdefault(self.uf, []).append(cidade)

        finally:
            # 🔥 CORREÇÃO — Fechar navegador completamente
            self._fechar_navegador_completamente()
            
            # 🔥 OTIMIZADO: Cooldown reduzido no finally (ainda seguro)
            cooldown_final = random.uniform(2.0, 3.0)  # Reduzido para 2-3s
            self._log(f"⏳ Cooldown final de {cooldown_final:.1f}s...")
            self._sleep(cooldown_final)

            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
                # 🔥 OTIMIZADO: Reduzido (redundante com cooldown final)
                self._sleep(random.uniform(0.5, 1.0))  # Reduzido de 5-10s para 0.5-1s

    # ------------------------------------------------------
    #                     PASSO 1
    # ------------------------------------------------------
    def _passo1(self):
        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        w = self.wait_dropdown

        try:
            elem = w.until(EC.element_to_be_clickable((By.CLASS_NAME, "rw-dropdown-list-input")))
            self._clicar_humano(elem)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao clicar em dropdown: {e}")

        delay_humano(0.4, 0.9, self.stop_flag)

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        try:
            elem = w.until(EC.element_to_be_clickable((By.XPATH, "//li[text()='DENTAL']")))
            self._clicar_humano(elem)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao selecionar DENTAL: {e}")

        delay_humano(0.4, 0.9, self.stop_flag)

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        try:
            selects = w.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "rw-btn-select")))
            self._clicar_humano(selects[1])
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao clicar em selects: {e}")

        delay_humano(0.55, 1.1, self.stop_flag)

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        try:
            plano = w.until(EC.element_to_be_clickable((By.XPATH, "//li[text()='Amil Dental Nacional']")))
            self._clicar_humano(plano)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao selecionar plano: {e}")

        delay_humano(0.55, 1.1, self.stop_flag)

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        try:
            btn = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "test_btn_firststep_submit")))
            self._clicar_humano(btn)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao clicar em botão submit: {e}")

        delay_humano(0.7, 1.4, self.stop_flag)

    def _escape_xpath_text(self, text: str) -> str:
        """Permite usar texto com apóstrofos no XPATH."""
        if "'" not in text:
            return f"'{text}'"
        parts = text.split("'")
        return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"

    # ------------------------------------------------------
    #                     PASSO 2
    # ------------------------------------------------------
    def _passo2(self, cidade: str):
        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        w = self.wait_dropdown

        try:
            estado = w.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Estado')]/following::button[1]")))
            self._clicar_humano(estado)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao clicar em Estado: {e}")

        delay_humano(0.4, 0.9, self.stop_flag)

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        try:
            uf_op = w.until(EC.element_to_be_clickable((By.XPATH, f"//li[text()='{self.uf}']")))
            self._clicar_humano(uf_op)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao selecionar UF {self.uf}: {e}")

        delay_humano(0.4, 0.9, self.stop_flag)

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        try:
            muni = w.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Municipio')]/following::button[1]")))
            self._clicar_humano(muni)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao clicar em Município: {e}")

        delay_humano(0.55, 1.1, self.stop_flag)

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        xpath_cidade = self._escape_xpath_text(cidade)
        try:
            cidade_op = w.until(
                EC.element_to_be_clickable((By.XPATH, f"//li[text()={xpath_cidade}]"))
            )
            self._clicar_humano(cidade_op)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao selecionar cidade {cidade}: {e}")

        delay_humano(0.4, 0.9, self.stop_flag)

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        try:
            bairro = w.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Bairro')]/following::button[1]")))
            self._clicar_humano(bairro)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao clicar em Bairro: {e}")

        delay_humano(0.4, 0.9, self.stop_flag)

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        try:
            todos = w.until(EC.element_to_be_clickable((By.XPATH, "//li[text()='TODOS OS BAIRROS']")))
            self._clicar_humano(todos)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao selecionar TODOS OS BAIRROS: {e}")

        delay_humano(0.55, 1.1, self.stop_flag)

        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        try:
            cont = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.test_btn_secondstep_submit")))
            self._clicar_humano(cont)
        except Exception as e:
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            raise Exception(f"Erro ao clicar em botão continuar: {e}")

        delay_humano(0.7, 1.4, self.stop_flag)

    # ------------------------------------------------------
    #                     PASSO 3
    # ------------------------------------------------------
    def _passo3(self, cidade: str):
        w = self.wait_dropdown

        btn = w.until(
            EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Especialidade')]/following::button[1]"))
        )
        self._clicar_humano(btn)
        delay_humano(0.4, 0.9, self.stop_flag)

        w.until(EC.presence_of_element_located((By.XPATH, "//ul[contains(@id,'listbox')]//li")))

        candidatos = [
            "//li[text()='CLINICA GERAL']",
            "//li[contains(text(),'CLÍNICA GERAL')]",
            "//li[contains(text(),'CLINICA GERAL')]",
        ]

        op = None
        for xp in candidatos:
            try:
                op = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, xp))
                )
                break
            except:
                continue

        if not op:
            self._log(f"⚠️ Especialidade não encontrada em {cidade}-{self.uf}")
            # O scraper portátil gera os próprios PDFs em documentos/ — aqui só no fluxo do main.py
            if self.gerar_pdf_vazio:
                gerar_pdf_sem_especialidade(self.uf, cidade, self.pasta_base)
            raise Exception("Especialidade não encontrada")

        delay_humano(0.2, 0.45, self.stop_flag)
        self._clicar_humano(op)
        delay_humano(0.55, 1.1, self.stop_flag)

    # ------------------------------------------------------
    #          BUSCAR + CAPTURAR RESULTADOS
    # ------------------------------------------------------
    def _capturar(self) -> list[dict]:
        """
        Clica em Buscar e extrai os prestadores.
        Retorna [] se não vierem resultados — o retry fica no processar_cidade.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        import time as time_module
        
        # 🔥 NOVO — Timeout máximo total para evitar travamento infinito
        inicio_captura = time_module.time()
        timeout_maximo_total = 180  # 3 minutos máximo para toda a captura
        
        # 🔥 NOVO — Verificar stop_flag no início
        if self.stop_flag and self.stop_flag.is_set():
            raise Exception("Execução interrompida pelo usuário")

        # ============================================================
        #   TENTATIVA INICIAL (SEM FECHAR O NAVEGADOR)
        # ============================================================
        self._log("🔍 Tentativa inicial (sem restart)...")

        try:
            # 🔥 NOVO — Verificar timeout máximo
            if time_module.time() - inicio_captura > timeout_maximo_total:
                raise Exception("Timeout máximo atingido na captura")
            
            # Verificar bloqueio antes de buscar
            if self._verificar_bloqueio():
                self._log("⚠️ Bloqueio detectado antes de buscar!")
                raise Exception("Bloqueio detectado")

            # 🔥 NOVO — Verificar stop_flag antes de clicar
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")

            # 🔥 CORREÇÃO — Timeout menor e verificação de stop_flag durante espera
            try:
                btn = WebDriverWait(self.driver, 10).until(
                    lambda d: (
                        self.stop_flag.is_set() if self.stop_flag and self.stop_flag.is_set() else
                        EC.element_to_be_clickable((By.CLASS_NAME, "test_btn_thirdstep_submit"))(d)
                    )
                )
                if self.stop_flag and self.stop_flag.is_set():
                    raise Exception("Execução interrompida pelo usuário")
            except Exception as e:
                if "interrompida" in str(e):
                    raise
                # Se não encontrou o botão, tentar encontrar de outra forma
                try:
                    btn = self.driver.find_element(By.CLASS_NAME, "test_btn_thirdstep_submit")
                except:
                    raise Exception("Botão de buscar não encontrado")
            
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")

            self._clicar_humano(btn)

            self._log("⏳ Aguardando resultados aparecerem...")

            # Aguardar mais tempo para JavaScript carregar
            time.sleep(random.uniform(3.0, 5.0))

            # 🔥 NOVO — Verificar stop_flag durante espera
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            
            # 🔥 NOVO — Verificar timeout máximo
            if time_module.time() - inicio_captura > timeout_maximo_total:
                raise Exception("Timeout máximo atingido na captura")

            # Verificar bloqueio após buscar
            if self._verificar_bloqueio():
                self._log("⚠️ Bloqueio detectado após buscar!")
                raise Exception("Bloqueio após buscar")

            # 🔥 NOVO — Aguardar um pouco mais para JavaScript carregar
            time.sleep(2)

            # Mensagem de "sem resultados" numa cidade com Clínica Geral = shadow block.
            # (Antes o raise ficava dentro de um try/except: pass e era engolido.)
            mensagens_sem_resultado = [
                "//*[contains(text(), 'não localizou nenhum prestador')]",
                "//*[contains(text(), 'nenhum resultado')]",
                "//*[contains(text(), 'Nenhum resultado')]",
                "//*[contains(text(), 'não encontrado')]",
                "//*[contains(text(), 'Não encontrado')]",
            ]
            sem_resultado = False
            for xpath in mensagens_sem_resultado:
                try:
                    if any(el.is_displayed() for el in self.driver.find_elements(By.XPATH, xpath)):
                        sem_resultado = True
                        break
                except Exception:
                    continue
            if sem_resultado:
                self._log("⚠️ Site retornou mensagem de 'sem resultados' - possível bloqueio detectado")
                raise Exception("Site retornou 'nenhum resultado' - provável bloqueio ou falha parcial. Tentando novamente...")

            # 🔥 CORREÇÃO — Timeout menor e verificação de stop_flag
            try:
                WebDriverWait(self.driver, 15).until(  # Reduzido de 20 para 15
                    lambda d: (
                        self.stop_flag.is_set() if self.stop_flag and self.stop_flag.is_set() else
                        EC.any_of(
                            EC.presence_of_element_located((By.ID, "result-legend")),
                            EC.presence_of_element_located((By.CLASS_NAME, "accredited-network__result")),
                        )(d)
                    )
                )
                if self.stop_flag and self.stop_flag.is_set():
                    raise Exception("Execução interrompida pelo usuário")
            except Exception as e:
                if "interrompida" in str(e):
                    raise
                self._log("⚠️ Timeout aguardando indicadores de resultado")

            # 🔥 NOVO — Fazer scroll para carregar resultados (scroll infinito)
            try:
                # Scroll até o final da página para carregar todos os resultados
                last_height = self.driver.execute_script("return document.body.scrollHeight")
                scroll_attempts = 0
                max_scrolls = 5
                
                while scroll_attempts < max_scrolls:
                    # 🔥 NOVO — Verificar timeout máximo e stop_flag durante scroll
                    if time_module.time() - inicio_captura > timeout_maximo_total:
                        self._log("⚠️ Timeout máximo atingido durante scroll")
                        break
                    
                    if self.stop_flag and self.stop_flag.is_set():
                        raise Exception("Execução interrompida pelo usuário")
                    
                    # Scroll para baixo
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)  # Aguardar carregar
                    
                    # Verificar se a página cresceu (novos resultados carregados)
                    new_height = self.driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break  # Não há mais conteúdo para carregar
                    last_height = new_height
                    scroll_attempts += 1
                
                # Scroll de volta para o topo
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.5)
            except Exception as e:
                if "interrompida" in str(e):
                    raise
                self._log(f"⚠️ Erro ao fazer scroll: {e}")

            # 🔥 CORREÇÃO — Timeout menor e não bloquear se não encontrar
            try:
                WebDriverWait(self.driver, 10).until(  # Reduzido de 20 para 10
                    lambda d: (
                        self.stop_flag.is_set() if self.stop_flag and self.stop_flag.is_set() else
                        EC.presence_of_element_located((By.CLASS_NAME, "accredited-network__result"))(d)
                    )
                )
                if self.stop_flag and self.stop_flag.is_set():
                    raise Exception("Execução interrompida pelo usuário")
            except Exception as e:
                if "interrompida" in str(e):
                    raise
                self._log("⚠️ Timeout aguardando blocos de resultado - continuando mesmo assim")

            # 🔥 NOVO — Tentar múltiplos seletores (caso a classe tenha mudado)
            blocos = []
            seletores = [
                (By.CLASS_NAME, "accredited-network__result"),
                (By.CSS_SELECTOR, "[class*='accredited-network']"),
                (By.CSS_SELECTOR, "[class*='result']"),
            ]
            
            for by, selector in seletores:
                try:
                    blocos = self.driver.find_elements(by, selector)
                    if blocos:
                        self._log(f"✅ Encontrados {len(blocos)} blocos com seletor: {selector}")
                        break
                except:
                    continue

            # 🔥 NOVO — Debug: salvar screenshot se não encontrar resultados
            if not blocos:
                try:
                    screenshot_path = f"debug_no_results_{self.uf}_{self._current_city}.png"
                    self.driver.save_screenshot(screenshot_path)
                    self._log(f"📸 Screenshot salvo para debug: {screenshot_path}")
                    
                    # Salvar HTML da página para análise
                    html_path = f"debug_no_results_{self.uf}_{self._current_city}.html"
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                    self._log(f"📄 HTML salvo para debug: {html_path}")
                except:
                    pass

            if blocos:
                self._log(f"✅ Resultados carregados na tentativa inicial ({len(blocos)} blocos).")
                return self._extrair_prestadores(blocos)

            # nenhum bloco, mas tentativa feita → cai para retry
            self._log("⚠️ Nenhum bloco encontrado na tentativa inicial.")

        except Exception as e:
            # Se foi interrompido, não fazer retry
            if self.stop_flag and self.stop_flag.is_set():
                raise Exception("Execução interrompida pelo usuário")
            
            # 🔥 NOVO — Se timeout máximo atingido, não fazer retry
            if "Timeout máximo" in str(e):
                self._log(f"⏱️ {e}")
                return []
            
            self._log(f"⚠️ Tentativa inicial falhou: {e}")

        # Sem resultados: lista vazia faz o processar_cidade fechar o navegador,
        # esperar e tentar de novo com um Chrome limpo (até 3 vezes).
        return []


    def _extrair_prestadores(self, blocos):
        prestadores = []
        from selenium.webdriver.common.by import By

        for b in blocos:
            try: 
                nome = b.find_element(By.TAG_NAME, "h3").text.strip()
            except: 
                nome = "NOME NÃO ENCONTRADO"

            try: 
                endereco = b.find_element(
                    By.CSS_SELECTOR,
                    ".accredited-network__result__address-name p:nth-child(1)"
                ).text.strip()
            except: 
                endereco = "ENDEREÇO NÃO ENCONTRADO"

            try: 
                bairro = b.find_element(
                    By.CSS_SELECTOR,
                    ".accredited-network__result__neighbourhood p"
                ).text.strip()
            except: 
                bairro = "BAIRRO NÃO ENCONTRADO"

            try: 
                telefone = b.find_element(
                    By.CSS_SELECTOR,
                    ".accredited-network__result__address-name p:nth-child(3)"
                ).text.strip()
            except: 
                telefone = "TELEFONE NÃO ENCONTRADO"

            # 🔥 VALIDAÇÃO: só adiciona se for prestador válido
            textos_invalidos = [
                "NOME NÃO ENCONTRADO",
                "ENDEREÇO NÃO ENCONTRADO",
                "Sua busca não localizou nenhum prestador",
                "nenhum prestador",
                "Nenhum prestador",
                "Legenda de ícones",
                "",
            ]
            
            # Validar se é prestador válido
            if (nome not in textos_invalidos and 
                endereco not in textos_invalidos and
                len(nome) > 3 and
                len(endereco) > 5):
                
                prestadores.append({
                    "nome": nome,
                    "endereco": endereco,
                    "bairro": bairro if bairro != "BAIRRO NÃO ENCONTRADO" else "",
                    "telefone": telefone if telefone != "TELEFONE NÃO ENCONTRADO" else "",
                })

        return prestadores