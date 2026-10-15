# Contexto — rede Amil Dental, outubro/2026

Estado da atualização da rede credenciada feita entre 09 e 15/10/2026, para continuar o trabalho em outra máquina. Tudo que é saída (`documentos/`, `docs/`, logs) está no `.gitignore` e **não** vem com o `git pull`.

## Resumo

| Item | Situação |
|---|---|
| Cidades na lista (`config/estados_cidades_amil.json`, extraída do site em 09/10) | 957 |
| PDFs gerados nesta máquina | 899 (893 aprovados + 6 já refeitos das 64 abaixo) |
| **Para refazer** | **64** identificadas na auditoria — 58 sem PDF + 6 já refeitas aqui (lista na seção "Cidades para refazer") |
| PDFs por zona (SP e RJ, com sub-regiões do RJ) | corrigidos e regerados em 14/10 |
| Planilha `documentos/planilhas/planilha_simples.xlsx` | regerar depois das 58 |
| Mês de referência nos PDFs | "Referência: Outubro / 2026", canto superior direito |

## O que foi corrigido no código

1. **Bloqueio do site (Akamai Bot Manager).** A busca final (`RedeCredenciadaCredenciado`) volta 403 quando o sensor acha que é robô; a tela mostra "Sua busca não localizou nenhum prestador" (shadow block). O mouse agora se move em curva com dezenas de pontos (`_mover_mouse_curva` em `src/scraper/amil_scraper.py`).
2. **Versão do Chrome** detectada sozinha (antes fixa em 148); user-agent acompanha a versão real.
3. **Bug do clique (o erro grave).** O clique media a posição antes de a lista terminar de rolar e caía na opção vizinha. Em listas longas (MG, BA, GO) o site ficava com **outra cidade** e o PDF saía com o nome de uma cidade e os prestadores de outra (ex.: Juiz de Fora com 1 prestador de Lagamar; o certo são 84). Afetou só PDFs gerados em **09/10 entre 13:50 e 17:59**. Correção: esperar a rolagem parar e confirmar que o ponto do clique está sobre a opção (`_clicar_humano`).
4. **Travas de segurança** (novas, em `amil_scraper.py`): `_conferir_local` exige que o resumo do Passo 2 mostre `CIDADE (UF) - TODOS OS BAIRROS`; `_conferir_especialidade` exige `CLINICA GERAL` no campo de especialidade. Se não bater, a tentativa é descartada e refeita — o erro não passa mais em silêncio.
5. **Zonas.** O leitor de `scripts/gerar_pdfs_por_zona.py` grudava a linha "Referência: Outubro / 2026" no endereço do prestador anterior. Corrigido (a linha é descartada antes de ler os prestadores).
6. **Execução**: `scripts/rodar_paralelo.py` (N processos com Chrome oculto, dividindo as cidades) e `scripts/rodar_em_ciclos.py` (roda em ciclos e pausa sozinho quando o bloqueio dispara). Corrigido o `input()` final que travava processos em segundo plano.

## Cidades que estavam erradas (bug do clique)

A auditoria comparou os 265 PDFs gerados na janela do bug: lista idêntica à de outra cidade, ruas e bairros no ViaCEP e DDD dos telefones contra o DDD da cidade.

**40 confirmadas erradas** — se estiverem publicadas com a versão de 09/10, tirar do ar até refazer:

| UF | Cidade | Evidência |
|---|---|---|
| BA | SALVADOR | lista idêntica à de Santa Maria da Vitória e Santo Amaro (4 prestadores) |
| BA | SANTA MARIA DA VITORIA | idem |
| BA | SANTO AMARO | idem |
| BA | VITORIA DA CONQUISTA | lista idêntica à de Valença e Xique-Xique |
| BA | VALENCA | idem |
| BA | JEQUIE | lista idêntica à de Juazeiro |
| BA | JUAZEIRO | idem |
| BA | POJUCA | lista idêntica à de Porto Seguro |
| BA | PORTO SEGURO | idem |
| BA | LAURO DE FREITAS | lista idêntica à de Luís Eduardo Magalhães |
| BA | LUIS EDUARDO MAGALHAES | idem |
| BA | IPIAU | lista idêntica à de Ipirá |
| BA | IPIRA | idem |
| BA | MADRE DE DEUS | lista idêntica à de Maracás |
| BA | MARACAS | idem |
| BA | SANTO ESTEVAO | lista idêntica à de São Gonçalo dos Campos e São Sebastião do Passé |
| BA | SAO GONCALO DOS CAMPOS | idem |
| BA | SAO SEBASTIAO DO PASSE | idem |
| BA | RIACHAO DO JACUIPE | DDD 71 nos telefones, cidade é 75 |
| BA | SENHOR DO BONFIM | DDD 75 nos telefones, cidade é 74 |
| BA | SERRINHA | DDD 71 nos telefones, cidade é 75 |
| BA | SIMOES FILHO | DDD 73 nos telefones, cidade é 71 |
| BA | TEIXEIRA DE FREITAS | DDD 75 nos telefones, cidade é 73 |
| GO | PLANALTINA | lista idêntica à de Posse |
| GO | POSSE | idem |
| GO | SANTO ANTONIO DO DESCOBERTO | lista idêntica à de Senador Canedo |
| GO | SENADOR CANEDO | idem |
| MA | SANTA INES | DDD 99 nos telefones, cidade é 98 |
| MA | TIMON | DDD 86 nos telefones, cidade é 99 |
| MG | JUIZ DE FORA | lista idêntica à de Lagamar (1 prestador; o certo são 84) |
| MG | FRUTAL | lista idêntica à de Governador Valadares |
| MG | CONFINS | lista idêntica à de Congonhas |
| MG | IGUATAMA | lista idêntica à de Ipaba |
| MG | IPABA | idem |
| MG | ITANHANDU | lista idêntica à de Itapeva e Itaúna |
| MG | ITAPEVA | idem |
| MG | ITAUNA | idem |
| MG | ITURAMA | lista idêntica à de Jaboticatubas |
| MG | JACUTINGA | lista idêntica à de Janaúba |
| MG | LAVRAS | lista idêntica à de Machado |

Nos pares e trios, uma das cidades pode estar certa, mas não dá para saber qual — todas entram para refazer.

**Também refazer, por cautela** (não deu para confirmar): 4 suspeitas (nenhuma rua achada na cidade), 2 inconclusivas (cidade de CEP único), 8 "sem Clínica Geral" (0 prestadores, nada para conferir) e 10 em que só havia rua de nome comum. As outras 201 da janela foram aprovadas pela checagem (rua e/ou bairro conferem no ViaCEP e o DDD bate). Os 692 PDFs gerados depois da correção não têm o problema.

Ao todo são **64 cidades para refazer**. Seis delas já foram refeitas nesta máquina com as travas — Bom Jesus da Lapa, Brumado, Caetité, Capim Grosso, Conceição da Feira e Cruz das Almas (BA) —, mas entram na lista para serem refeitas junto com as outras.

## Zonas que estavam erradas

Nos PDFs por zona, 1 prestador por cidade saía com o endereço contaminado e, na versão **sem telefone**, com o telefone aparecendo dentro do endereço:

- **SÃO PAULO — Zona Norte**: CLÍNICA ODONTOLÓGICA NIPO BRASILEIRA ("AV PARADA PINTO, 1020 SOBRELOJA Telefone: 11 - 3851-2061 Referência: Outubro / 2026")
- **RIO DE JANEIRO — Zona Norte**: AT ODONTOLOGIA ("AV DOM HELDER CAMARA, 6644 SL 616 Telefone: 21 - 98142-6410 Referência: Outubro / 2026")

Substituir os 4 arquivos publicados (Zona Norte de SP e do RJ, com e sem telefone). Os demais PDFs de zona só foram regerados, sem mudança de conteúdo. Também foram classificados 22 bairros novos em `config/zonas_bairros.json`; nenhum prestador fica em "NÃO CLASSIFICADO".

## Cidades para refazer (64)

`*` = já refeita nesta máquina com as travas (entra de novo mesmo assim).

```
BA: BOM JESUS DA LAPA*, BRUMADO*, CAETITE*, CAPIM GROSSO*, CONCEICAO DA FEIRA*, CRUZ DAS ALMAS*,
    GUANAMBI, IPIAU, IPIRA, JEQUIE, JUAZEIRO, LAURO DE FREITAS, LUIS EDUARDO MAGALHAES, MADRE DE DEUS,
    MARACAS, POJUCA, PORTO SEGURO, RIACHAO DO JACUIPE, SALVADOR, SANTA MARIA DA VITORIA, SANTO AMARO,
    SANTO ANTONIO DE JESUS, SANTO ESTEVAO, SAO GONCALO DOS CAMPOS, SAO SEBASTIAO DO PASSE, SENHOR DO BONFIM,
    SERRINHA, SIMOES FILHO, TEIXEIRA DE FREITAS, VALENCA, VITORIA DA CONQUISTA
ES: ITAPEMIRIM
GO: ALEXANIA, ALTO HORIZONTE, CORUMBAIBA, IPAMERI, PLANALTINA, POSSE, RUBIATABA,
    SANTA TEREZINHA DE GOIAS, SANTO ANTONIO DO DESCOBERTO, SENADOR CANEDO
MA: COROATA, PACO DO LUMIAR, SANTA INES, TIMON
MG: CAMPO BELO, CONFINS, FRUTAL, IBIRITE, IGUATAMA, IPABA, ITANHANDU, ITAPEVA, ITAUNA, ITURAMA,
    JACUTINGA, JOAO PINHEIRO, JUIZ DE FORA, LAVRAS
MS: CORUMBA, MUNDO NOVO
MT: ALTA FLORESTA, LUCAS DO RIO VERDE
```

## Como terminar na outra máquina

**Pré-requisitos:** Python 3.11, Google Chrome e wkhtmltopdf em `C:\Program Files\wkhtmltopdf\bin\` (veja o README).

```powershell
git pull
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt setuptools
```

**1. Trazer os PDFs desta máquina.** Copie a pasta `documentos/` desta máquina para a raiz do projeto na outra.

> Se a outra máquina já tiver uma pasta `documentos/` antiga (de maio), **não** a use: os PDFs dela estão desatualizados e fariam o script pular cidades. Substitua pela desta máquina.

Os scripts pulam cidade que já tem PDF. Para refazer as 64, apague primeiro os PDFs delas (com e sem telefone) — na raiz do projeto:

```powershell
$cidades = @(
    "BOM_JESUS_DA_LAPA-BA", "BRUMADO-BA", "CAETITE-BA", "CAPIM_GROSSO-BA", "CONCEICAO_DA_FEIRA-BA",
    "CRUZ_DAS_ALMAS-BA", "GUANAMBI-BA", "IPIAU-BA", "IPIRA-BA", "JEQUIE-BA", "JUAZEIRO-BA",
    "LAURO_DE_FREITAS-BA", "LUIS_EDUARDO_MAGALHAES-BA", "MADRE_DE_DEUS-BA", "MARACAS-BA", "POJUCA-BA",
    "PORTO_SEGURO-BA", "RIACHAO_DO_JACUIPE-BA", "SALVADOR-BA", "SANTA_MARIA_DA_VITORIA-BA",
    "SANTO_AMARO-BA", "SANTO_ANTONIO_DE_JESUS-BA", "SANTO_ESTEVAO-BA", "SAO_GONCALO_DOS_CAMPOS-BA",
    "SAO_SEBASTIAO_DO_PASSE-BA", "SENHOR_DO_BONFIM-BA", "SERRINHA-BA", "SIMOES_FILHO-BA",
    "TEIXEIRA_DE_FREITAS-BA", "VALENCA-BA", "VITORIA_DA_CONQUISTA-BA", "ITAPEMIRIM-ES",
    "ALEXANIA-GO", "ALTO_HORIZONTE-GO", "CORUMBAIBA-GO", "IPAMERI-GO", "PLANALTINA-GO", "POSSE-GO",
    "RUBIATABA-GO", "SANTA_TEREZINHA_DE_GOIAS-GO", "SANTO_ANTONIO_DO_DESCOBERTO-GO", "SENADOR_CANEDO-GO",
    "COROATA-MA", "PACO_DO_LUMIAR-MA", "SANTA_INES-MA", "TIMON-MA", "CAMPO_BELO-MG", "CONFINS-MG",
    "FRUTAL-MG", "IBIRITE-MG", "IGUATAMA-MG", "IPABA-MG", "ITANHANDU-MG", "ITAPEVA-MG", "ITAUNA-MG",
    "ITURAMA-MG", "JACUTINGA-MG", "JOAO_PINHEIRO-MG", "JUIZ_DE_FORA-MG", "LAVRAS-MG", "CORUMBA-MS",
    "MUNDO_NOVO-MS", "ALTA_FLORESTA-MT", "LUCAS_DO_RIO_VERDE-MT"
)
foreach ($c in $cidades) {
    $uf = $c.Split("-")[-1]
    foreach ($pasta in "pdfs", "pdfs_sem_telefone") {
        Remove-Item "documentos\$pasta\$uf\$c.pdf" -ErrorAction SilentlyContinue
    }
}
"PDFs restantes: $((Get-ChildItem documentos\pdfs -Recurse -Filter *.pdf).Count)"   # deve dar 893
```

**2. Rodar as 64.** Um IP "novo" é o que faz diferença: este IP foi marcado pelo Akamai depois de dias de raspagem. VPN (IP de datacenter) não funcionou; o roteador do celular (4G) é a melhor opção.

```powershell
# teste rápido de 1 cidade (deve vir 84 prestadores)
.\venv\Scripts\python.exe -u scripts/amil_portable.py --uf MG --cidade "JUIZ DE FORA"

# as pendentes (pula quem já tem PDF); pausa sozinho se o bloqueio disparar
.\venv\Scripts\python.exe -u scripts/rodar_em_ciclos.py --workers 3 --pausa 45

# alternativa sem pausas automáticas
.\venv\Scripts\python.exe -u scripts/rodar_paralelo.py --workers 4

# acompanhar
Get-Content documentos\logs\execucao_parte1.log -Wait -Tail 20 -Encoding UTF8
```

Com IP bom, as 64 levam uns 45 minutos. Se quase toda tentativa vier "shadow block", pare e tente mais tarde ou em outra rede — insistir só piora a reputação do IP.

**3. Conferir que nada falta e regerar a planilha.** O `rodar_em_ciclos.py` e o `rodar_paralelo.py` já regeram a planilha no fim; para fazer à mão:

```powershell
.\venv\Scripts\python.exe scripts/comparar_cidades.py
.\venv\Scripts\python.exe -c "import sys; sys.path.insert(0, '.'); from scripts.amil_portable import gerar_planilha_final; gerar_planilha_final()"
```

> Não use `scripts/regenerar_planilha.py`: ele lê `docs/pdfs` (fluxo antigo do `main.py`), não `documentos/pdfs`.

**4. Zonas** (só se SÃO PAULO ou RIO DE JANEIRO forem refeitas; hoje estão corretas):

```powershell
.\venv\Scripts\python.exe scripts/mapear_zonas.py            # bairros novos sem zona
.\venv\Scripts\python.exe scripts/gerar_pdfs_por_zona.py --sub
```

## Onde ficam as coisas (nesta máquina, fora do git)

| Caminho | Conteúdo |
|---|---|
| `documentos/pdfs/`, `documentos/pdfs_sem_telefone/` | PDFs por cidade |
| `documentos/pdfs_por_zona/`, `documentos/pdfs_por_zona_sem_telefone/` | zonas de SP e RJ |
| `documentos/logs/auditoria_viacep.csv` | veredito de cada uma das 265 cidades da janela do bug |
| `documentos/logs/pendentes_auditoria.csv` | as 64 cidades para refazer, com o motivo de cada uma |
| `documentos/_backup_suspeitos_bug_clique/` | PDFs antigos da janela do bug, para comparação |
