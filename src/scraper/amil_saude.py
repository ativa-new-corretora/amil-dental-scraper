"""
Rede Amil SAÚDE — busca avançada do site da Amil para planos de saúde.

O que muda em relação ao Dental (src/scraper/amil_scraper.py):
- Passo 1: tipo "SAUDE" e um plano entre ~2.700 (ex.: "Prata QC", codigoRede 1078);
- Passo 3: há "Tipo de serviço" antes da "Especialidade";
- a busca (POST RedeCredenciadaCredenciado) devolve a lista inteira em JSON, sem paginação.

Os menus (municípios, tipos de serviço, especialidades) são GETs abertos e são
lidos direto pela API, sem navegador. Só o POST da busca passa pelo Akamai: fora
de uma busca "humana" pela tela ele dá 403 — um fetch da própria página passa no
máximo 2 vezes depois de uma busca pela tela. Por isso toda consulta é feita
pela interface (Passo 3 -> Alterar -> tipo -> especialidade -> Buscar, com mouse
em curva como no Dental) e o JSON que o próprio site recebe é lido por um gancho
no XMLHttpRequest — mais completo e confiável que ler a tela.
"""
import json
import random
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from src.scraper.amil_scraper import AmilBot
from src.utils.delays import delay_humano

API = "https://www.amil.com.br/institucional/api/InstitucionalMiddleware/"
TODOS_BAIRROS = "TODOS OS BAIRROS"
UA_API = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36")


class Bloqueio(Exception):
    """Akamai recusou a busca (403) — a sessão do navegador foi marcada como robô."""


def normalizar(texto: str) -> str:
    """'Santa Bárbara d'Oeste' -> 'SANTA BARBARA DOESTE' (para casar com a lista do site)."""
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", s)).strip()


# ============================================================
#  MENUS — GETs abertos (sem Akamai), lidos sem navegador
# ============================================================

def _get(*partes: str, query: str = ""):
    url = API + "/".join(urllib.parse.quote(str(p), safe="") for p in partes) + query
    erro = None
    for tentativa in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA_API, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []  # a API responde 404 quando a lista está vazia
            erro = e
        except Exception as e:  # 408/timeout da API acontecem de vez em quando
            erro = e
        time.sleep(2 + 3 * tentativa)
    raise RuntimeError(f"API de menus falhou ({'/'.join(partes)}): {erro}")


def buscar_plano(nome: str) -> dict:
    """Plano de saúde pelo nome exato — há dezenas parecidos ('Prata II QC', 'Adesão Prata SP QC'...)."""
    planos = _get("RedeCredenciadaPlanos", query="?operadora=SAUDE")
    achados = [p for p in planos if p["nomeDoPlano"].strip() == nome.strip()]
    if len(achados) != 1:
        raise RuntimeError(f"Plano '{nome}': {len(achados)} correspondências exatas no site (esperado 1)")
    return achados[0]


def listar_municipios(rede: int, uf: str) -> list[str]:
    return [m["Municipio"] for m in _get("RedeCredenciadaMunicipio", rede, "SAUDE", uf)]


def listar_tipos_servico(rede: int, uf: str, municipio: str) -> list[str]:
    return [t["NIVEL1_CAPITULO"] for t in _get("RedeCredenciadaTipoServico", rede, "SAUDE", uf, municipio, TODOS_BAIRROS)]


def listar_especialidades(rede: int, uf: str, municipio: str, tipo: str) -> list[str]:
    return [e["NIVEL2_ELEMENTODIVULGACAO"]
            for e in _get("RedeCredenciadaEspecialidade", rede, "SAUDE", uf, municipio, TODOS_BAIRROS, tipo)]


def planejar_consultas(rede: int, uf: str, municipio: str,
                       categorias: dict[str, list[list[str]]]) -> tuple[list[dict], list[str]]:
    """
    Converte as categorias do config em consultas (categoria, tipo, especialidade)
    que existem nesta cidade. Especialidade "*" = todas as do tipo de serviço.
    Retorna (consultas, avisos) — aviso para o que o plano não oferece na cidade.
    """
    tipos = listar_tipos_servico(rede, uf, municipio)
    cache: dict[str, list[str]] = {}
    consultas, avisos = [], []
    for categoria, pares in categorias.items():
        n_antes = len(consultas)
        for tipo, esp in pares:
            if tipo not in tipos:
                aviso = f"{categoria}: tipo '{tipo}' não existe na cidade"
                if aviso not in avisos:
                    avisos.append(aviso)
                continue
            if tipo not in cache:
                cache[tipo] = listar_especialidades(rede, uf, municipio, tipo)
            disponiveis = cache[tipo]
            alvo = disponiveis if esp == "*" else [esp]
            for e in alvo:
                if e in disponiveis:
                    consultas.append({"categoria": categoria, "tipo": tipo, "especialidade": e})
                else:
                    avisos.append(f"{categoria}: '{e}' não existe em '{tipo}' na cidade")
        if len(consultas) == n_antes:
            avisos.append(f"{categoria}: nada disponível no plano nesta cidade")
    return consultas, avisos


# ============================================================
#  NAVEGADOR — reaproveita o AmilBot (stealth, mouse em curva, travas)
# ============================================================

# Guarda o POST da busca que o próprio site faz (corpo enviado + resposta).
# Instalado depois de a página carregar: o axios do site cria um XMLHttpRequest
# novo a cada chamada, então o protótipo alterado já vale para as buscas.
JS_GANCHO = """
if (!window.__buscas) {
  window.__buscas = [];
  const abrir = XMLHttpRequest.prototype.open, enviar = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__m = m; this.__u = u; return abrir.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (corpo) {
    const x = this;
    if (x.__m === 'POST' && /RedeCredenciadaCredenciado$/.test(x.__u || '')) {
      x.addEventListener('loadend', function () {
        window.__buscas.push({status: x.status, corpo: corpo || '', resposta: x.responseText || ''});
      });
    }
    return enviar.apply(this, arguments);
  };
}
"""


class AmilSaudeBot(AmilBot):
    """AmilBot com os passos 1 e 3 da Saúde. Os passos do Dental continuam intactos na classe base."""

    def __init__(self, uf: str, plano: dict, logger=None):
        super().__init__(uf, logger=logger)
        self.plano = plano
        self.gerar_pdf_vazio = False

    def _li_exato(self, texto: str):
        xp = f"//ul[contains(@id,'listbox')]//li[normalize-space(text())={self._escape_xpath_text(texto)}]"
        return self.wait_dropdown.until(EC.element_to_be_clickable((By.XPATH, xp)))

    def _passo1(self):
        w = self.wait_dropdown
        self._clicar_humano(w.until(EC.element_to_be_clickable((By.CLASS_NAME, "rw-dropdown-list-input"))))
        delay_humano(0.4, 0.9)
        self._clicar_humano(self._li_exato("SAUDE"))
        delay_humano(0.55, 1.1)

        selects = w.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "rw-btn-select")))
        self._clicar_humano(selects[1])
        delay_humano(0.8, 1.4)  # a lista de planos tem ~2.700 itens
        self._clicar_humano(self._li_exato(self.plano["nomeDoPlano"]))
        delay_humano(0.55, 1.1)

        self._clicar_humano(self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "test_btn_firststep_submit"))))
        delay_humano(0.7, 1.4)
        self._conferir_plano()

    def _conferir_plano(self) -> None:
        """Trava: o resumo do Passo 1 precisa mostrar exatamente o plano pedido."""
        nome = self.plano["nomeDoPlano"].strip()
        fim = time.time() + 10
        while time.time() < fim:
            linhas = [l.strip() for l in self.driver.find_element(By.TAG_NAME, "body").text.splitlines()]
            if nome in linhas:
                return
            self._sleep(0.5)
        raise Exception(f"Plano selecionado não confere: esperado '{nome}'")

    def _escolher_no_menu(self, rotulo: str, texto: str) -> None:
        xp_btn = f"//label[contains(text(),'{rotulo}')]/following::button[1]"
        self._clicar_humano(self.wait_dropdown.until(EC.element_to_be_clickable((By.XPATH, xp_btn))))
        delay_humano(0.6, 1.2)
        self._clicar_humano(self._li_exato(texto))
        delay_humano(0.55, 1.1)

        # Trava: clique na opção vizinha traria outra especialidade sem nenhum aviso
        xp_val = (f"//label[contains(text(),'{rotulo}')]"
                  "/following::*[contains(@class,'rw-dropdown-list') or contains(@class,'rw-widget')][1]")
        fim = time.time() + 6
        valor = ""
        while time.time() < fim:
            try:
                valor = self.driver.find_element(By.XPATH, xp_val).text.strip()
            except Exception:
                valor = ""
            if valor == texto:
                return
            self._sleep(0.5)
        raise Exception(f"'{rotulo}' não confere: esperado '{texto}', site mostra '{valor or 'vazio'}'")

    def _abrir_passo3(self) -> None:
        """Depois de uma busca o Passo 3 vira um resumo com 'Alterar' — reabre o formulário."""
        xp_form = "//label[contains(text(),'Tipo de servi')]"
        if any(e.is_displayed() for e in self.driver.find_elements(By.XPATH, xp_form)):
            return
        xp_alterar = ("//*[contains(normalize-space(.),'Passo 3')]"
                      "/following::*[normalize-space(text())='Alterar'][1]")
        self._clicar_humano(self.wait.until(EC.element_to_be_clickable((By.XPATH, xp_alterar))))
        self.wait.until(lambda d: any(e.is_displayed() for e in d.find_elements(By.XPATH, xp_form)))
        delay_humano(0.6, 1.2)

    def _salvar_debug(self, nome: str) -> None:
        """Print + HTML em documentos/saude/debug/ para entender uma falha estranha."""
        try:
            from src.utils.file_manager import SCRIPT_DIR
            pasta = SCRIPT_DIR / "documentos" / "saude" / "debug"
            pasta.mkdir(parents=True, exist_ok=True)
            base = pasta / f"{time.strftime('%Y%m%d_%H%M%S')}_{self.uf}_{re.sub(r'[^A-Za-z0-9]+', '_', nome)}"
            self.driver.save_screenshot(str(base.with_suffix(".png")))
            base.with_suffix(".html").write_text(self.driver.page_source, encoding="utf-8")
            self._log(f"📸 debug salvo: {base}")
        except Exception:
            pass

    def buscar(self, municipio: str, tipo: str, especialidade: str) -> list[dict]:
        """
        Uma consulta pela tela. Devolve a lista de prestadores do JSON que o site
        recebeu. 404 = nenhum prestador (o site trata assim); 403 = Bloqueio.
        """
        self.driver.execute_script(JS_GANCHO + "window.__buscas.length = 0;")
        self._log(f"   > {especialidade}: abrindo Passo 3")
        self._abrir_passo3()
        self._escolher_no_menu("Tipo de servi", tipo)
        self._escolher_no_menu("Especialidade", especialidade)
        if random.random() < 0.4:
            self._passear_mouse(1)
        self._log(f"   > {especialidade}: Buscar")
        self._clicar_humano(self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "test_btn_thirdstep_submit"))))

        fim = time.time() + 120  # São Paulo tem respostas grandes
        buscas = []
        while time.time() < fim and not buscas:
            self._sleep(1.0)
            buscas = self.driver.execute_script("return window.__buscas || null;")
            if buscas is None:  # página recarregou e levou o gancho junto
                raise Exception("página recarregou durante a busca")
        if not buscas:
            self._salvar_debug(f"sem_resposta_{especialidade}")
            raise Exception(f"busca sem resposta em 120s: {especialidade}")
        b = buscas[-1]

        # Trava: a busca enviada pelo site tem que ser exatamente a pedida
        try:
            corpo = json.loads(b["corpo"] or "{}")
        except ValueError:
            corpo = {}
        enviado = (corpo.get("codigoRede"), corpo.get("uf"), corpo.get("municipio"),
                   corpo.get("tipoServico"), corpo.get("especialidade"))
        pedido = (self.plano["codigoRede"], self.uf, municipio, tipo, especialidade)
        if enviado != pedido:
            raise Exception(f"busca enviada não confere: {enviado} != {pedido}")

        if b["status"] == 403:
            raise Bloqueio(f"403 em {especialidade}")
        if b["status"] == 404:
            return []
        if b["status"] != 200:
            raise Exception(f"HTTP {b['status']} em {especialidade}")
        dados = json.loads(b["resposta"] or "[]")
        dados = dados if isinstance(dados, list) else []

        # Conferência: o JSON tem que trazer o mesmo total que a tela anuncia (não há paginação)
        fim = time.time() + 15
        while time.time() < fim:
            achado = re.search(r"localizou (\d+) prestador", self.driver.find_element(By.TAG_NAME, "body").text)
            if achado:
                if int(achado.group(1)) != len(dados):
                    self._log(f"⚠️ {especialidade}: tela diz {achado.group(1)}, JSON tem {len(dados)}")
                break
            self._sleep(1.0)
        return dados


def coletar_cidade(plano: dict, uf: str, municipio: str, consultas: list[dict],
                   feitas: dict, logger=None, ao_concluir=None) -> None:
    """
    Executa as consultas ainda não presentes em `feitas` ({(tipo, esp): prestadores})
    numa sessão nova de navegador. Preenche `feitas` à medida que avança, para que
    uma nova tentativa depois de um bloqueio continue de onde parou.
    `ao_concluir(feitas)` é chamado após cada consulta (para gravar o parcial em disco).
    """
    pendentes = [c for c in consultas if (c["tipo"], c["especialidade"]) not in feitas]
    if not pendentes:
        return
    bot = AmilSaudeBot(uf, plano, logger=logger)
    etapa = "abrir navegador"
    try:
        bot._abrir_navegador()
        etapa = "passo 1 (plano)"
        bot._passo1()
        etapa = "passo 2 (local)"
        bot._passo2(municipio)  # inclui a trava "CIDADE (UF) - TODOS OS BAIRROS"
        for c in pendentes:
            etapa = f"busca {c['especialidade']}"
            chave = (c["tipo"], c["especialidade"])
            feitas[chave] = bot.buscar(municipio, *chave)
            bot._log(f"   {c['categoria']} / {c['especialidade']}: {len(feitas[chave])} da API")
            if ao_concluir:
                ao_concluir(feitas)
            # "Lendo" o resultado antes da próxima busca — o Akamai pontua o ritmo da sessão
            bot._passear_mouse(random.randint(1, 2))
            bot._sleep(random.uniform(2.0, 5.0))
    except Bloqueio:
        raise
    except Exception as e:
        msg = (getattr(e, "msg", None) or str(e)).strip()  # TimeoutException do Selenium vem sem texto
        msg = msg.splitlines()[0] if msg else type(e).__name__
        raise Exception(f"{etapa}: {msg}") from e
    finally:
        try:
            bot._fechar_navegador_completamente()
        except Exception:
            pass


# ============================================================
#  NORMALIZAÇÃO — uma linha por prestador + endereço, só do município pedido
# ============================================================

def _fone(ddd_numero: str) -> str:
    """'81-30032613' -> '81 - 3003-2613' (mesmo formato dos PDFs do Dental)."""
    ddd, _, num = ddd_numero.strip().partition("-")
    num = re.sub(r"\D", "", num)
    if not num:
        return ""
    if len(num) >= 8:
        num = f"{num[:-4]}-{num[-4:]}"
    return f"{ddd} - {num}" if ddd else num


def _lista_fones(texto: str | None) -> str:
    vistos = []
    for parte in (texto or "").split(";"):
        f = _fone(parte) if parte.strip() else ""
        if f and f not in vistos:
            vistos.append(f)
    return " / ".join(vistos)


def _endereco(e: dict) -> str:
    rua = " ".join(x for x in (e.get("tipoLogradouro"), e.get("logradouro")) if x).strip()
    numero = e.get("numero")
    s = f"{rua}, {numero}" if numero not in (None, 0, "0", "") else f"{rua}, S/N"
    if e.get("complemento"):
        s += f" {str(e['complemento']).strip()}"
    return re.sub(r"\s+", " ", s)


def _cep(cep) -> str:
    d = re.sub(r"\D", "", str(cep or "")).zfill(8)
    return f"{d[:5]}-{d[5:]}" if d.strip("0") else ""


def consolidar(uf: str, municipio: str, consultas: list[dict], feitas: dict) -> tuple[list[dict], dict]:
    """
    Junta as respostas por categoria. A busca por município devolve também
    prestadores de cidades vizinhas (ex.: Olinda na busca de Recife): só ficam
    os endereços no município pedido. O mesmo prestador/endereço que aparece
    em várias especialidades da categoria vira uma linha só.
    Retorna (linhas, {municipio: endereços descartados}).
    """
    linhas: dict[tuple, dict] = {}
    fora = set()
    for c in consultas:
        for p in feitas.get((c["tipo"], c["especialidade"]), []):
            for e in p.get("enderecoRedeCredenciada") or []:
                if normalizar(e.get("municipio") or "") != normalizar(municipio) or (e.get("uf") or uf) != uf:
                    fora.add((f"{e.get('municipio')}-{e.get('uf')}", p.get("codigoInterno"), _endereco(e)))
                    continue
                chave = (c["categoria"], p.get("codigoInterno"), _cep(e.get("cep")), _endereco(e))
                linha = linhas.get(chave)
                if not linha:
                    linha = linhas[chave] = {
                        "uf": uf,
                        "municipio": municipio,
                        "categoria": c["categoria"],
                        "prestador": re.sub(r"\s+", " ", (p.get("nomePrestador") or "").strip()),
                        "bairro": (e.get("bairroRedeCredenciada") or p.get("bairro") or "").strip(),
                        "endereco": _endereco(e),
                        "cep": _cep(e.get("cep")),
                        "telefones": _lista_fones(e.get("telefones")) or _lista_fones(
                            f"{e.get('ddd1') or ''}-{e.get('fone1') or ''}"),
                        "whatsapp": _lista_fones(e.get("whatsapps")),
                        "tipos_servico": set(),
                        "especialidades": set(),
                        "em_descredenciamento": "SIM" if p.get("emDescredenciamento") == "S" else "",
                        "codigo_amil": p.get("codigoInterno"),
                    }
                linha["tipos_servico"].add(c["tipo"])
                linha["especialidades"].add(c["especialidade"])
    resultado = []
    for l in linhas.values():
        l["tipos_servico"] = "; ".join(sorted(l["tipos_servico"]))
        l["especialidades"] = "; ".join(sorted(l["especialidades"]))
        resultado.append(l)
    resultado.sort(key=lambda l: (l["categoria"], l["bairro"], l["prestador"]))
    por_municipio: dict[str, int] = {}
    for m, *_ in fora:
        por_municipio[m] = por_municipio.get(m, 0) + 1
    return resultado, dict(sorted(por_municipio.items(), key=lambda x: -x[1]))
