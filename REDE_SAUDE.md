# Rede Amil Saúde — extração por plano, cidade e categoria

Script próprio, independente do fluxo Dental (`scripts/amil_portable.py` não foi alterado).

| Arquivo | Papel |
|---|---|
| `config/saude_prata_qc.json` | plano, cidades e categorias (editável) |
| `src/scraper/amil_saude.py` | API dos menus, `AmilSaudeBot` (subclasse do `AmilBot`), consolidação |
| `scripts/amil_saude.py` | execução, tentativas, JSON por cidade e planilha |

## Como rodar

```powershell
# o que seria buscado em cada cidade (só API, sem navegador, ~1 min)
.\venv\Scripts\python.exe -u scripts/amil_saude.py --listar

# tudo, com o Chrome fora da tela (pula cidades já coletadas)
$env:AMIL_JANELA_OCULTA = "1"
.\venv\Scripts\python.exe -u scripts/amil_saude.py

# uma cidade / refazer / só a planilha
.\venv\Scripts\python.exe -u scripts/amil_saude.py --uf PE --cidade Recife
.\venv\Scripts\python.exe -u scripts/amil_saude.py --forcar
.\venv\Scripts\python.exe -u scripts/amil_saude.py --so-planilha

# acompanhar
Get-Content documentos\saude\prata_qc\logs\execucao.log -Wait -Tail 20 -Encoding UTF8
```

Saída (fora do git, em `documentos/`):

- `documentos/saude/prata_qc/cidades/<UF>/<CIDADE>-<UF>.json`: resultado de cada cidade, com status, consultas feitas e total que a API devolveu em cada uma
- `documentos/saude/prata_qc/rede_saude_prata_qc.xlsx`: aba **Resumo** (cidade × categoria), uma aba por categoria (UF, Cidade, Prestador, Bairro, Endereço, CEP, Telefones, WhatsApp, Especialidades, Tipo de serviço, Em descredenciamento, Código Amil) e a aba **Cidades vizinhas** (as mesmas colunas, mais a cidade pesquisada e a categoria)
- `documentos/saude/prata_qc/parciais/`: respostas já obtidas de uma cidade ainda incompleta; são apagadas quando a cidade termina
- `documentos/saude/prata_qc/logs/`: `execucao.log` (uma linha por cidade), `bot.log` (detalhe do navegador), `falhas.json`
- `documentos/saude/debug/`: print e HTML quando uma busca fica sem resposta

## Como o site funciona (mapeamento)

Mesma página do Dental (`/institucional/#/servicos/saude/rede-credenciada/amil/busca-avancada`), mesma API (`/institucional/api/InstitucionalMiddleware/`).

| | Dental | Saúde |
|---|---|---|
| Passo 1 | tipo `DENTAL`, plano `Amil Dental Nacional` | tipo `SAUDE`, plano entre ~2.700 (`Prata QC` = codigoRede **1078**) |
| Passo 2 | UF, município, `TODOS OS BAIRROS` | igual |
| Passo 3 | especialidade (`CLINICA GERAL`) | **tipo de serviço** + especialidade |
| Resultado | lido da tela | JSON completo da busca, **sem paginação** (a resposta traz todos) |

Chamadas (o `SAUDE` no caminho é o que o site envia):

| Menu | Endpoint | Akamai? |
|---|---|---|
| Planos | `GET RedeCredenciadaPlanos?operadora=SAUDE` | não |
| Municípios | `GET RedeCredenciadaMunicipio/{rede}/SAUDE/{UF}` | não |
| Tipos de serviço | `GET RedeCredenciadaTipoServico/{rede}/SAUDE/{UF}/{MUN}/TODOS OS BAIRROS` | não |
| Especialidades | `GET RedeCredenciadaEspecialidade/{rede}/SAUDE/{UF}/{MUN}/TODOS OS BAIRROS/{TIPO}` | não |
| **Busca** | `POST RedeCredenciadaCredenciado` (corpo abaixo) | **sim** |

```json
{"codigoRede": 1078, "uf": "PE", "municipio": "RECIFE", "bairro": "TODOS OS BAIRROS",
 "especialidade": "CARDIOLOGIA", "tipoServico": "CONSULTORIOS - CLINICAS - TERAPIAS",
 "operadora": "AMIL, AMIL_PLANOS", "modalidade": "SAUDE", "contexto": "AMIL"}
```

A resposta é uma lista de prestadores (`nomePrestador`, `codigoInterno`, `emDescredenciamento`...). Cada um tem uma lista `enderecoRedeCredenciada` com município, bairro, CEP, telefones e WhatsApp. A API responde **404 quando não há prestador**.

**Estratégia.** Os menus vêm direto da API, sem navegador: o script valida cidade e categoria antes de abrir o Chrome. A busca é protegida pelo Akamai. Um `fetch` da página dá 403 logo após carregar, e depois de uma busca feita pela tela passa só 1 ou 2 vezes antes de voltar o 403. Por isso **toda consulta passa pela tela**: Passo 3 → Alterar → tipo → especialidade → Buscar, com o mouse em curva do `AmilBot`. O JSON que o site recebe é lido por um gancho no `XMLHttpRequest`. Abre-se um Chrome por cidade; os passos 1 e 2 são feitos uma vez e o Passo 3 é repetido para cada consulta.

**Validação feita (28/10/2026).** Ribeirão Pires completa: 14 consultas em ~6 min, planilha gerada. São Paulo: 28 de 42 consultas antes de o IP ficar marcado, com respostas grandes (179 ginecologistas, 94 cardiologistas) e o total do JSON igual ao da tela. A retomada, os bloqueios e a 2ª passada foram testados sem navegador. A extração completa das 24 cidades **não** foi rodada.

**Travas** (se algo não bater, a tentativa é descartada e refeita):

- o resumo do Passo 1 precisa mostrar exatamente `Prata QC`. Existem dezenas de planos parecidos, como `Prata II QC` e `Adesão Prata SP QC`.
- o resumo do Passo 2 precisa mostrar `CIDADE (UF) - TODOS OS BAIRROS` (trava herdada do Dental)
- os menus de tipo e especialidade precisam mostrar o valor pedido
- o corpo que o site **enviou** precisa ser exatamente o pedido: rede, UF, município, tipo e especialidade

## Categorias (config)

| Categoria | Tipo de serviço / especialidade |
|---|---|
| GINECOLOGIA | CONSULTORIOS - CLINICAS - TERAPIAS / `GINECOLOGIA` + `GINECOLOGIA E OBSTETRICIA` |
| CARDIOLOGIA | CONSULTORIOS - CLINICAS - TERAPIAS / `CARDIOLOGIA` (sem a pediátrica) |
| LABORATORIOS | LABORATORIOS E EXAMES / `ANALISES CLINICAS` (o tipo também traz imagem, endoscopia etc., que ficam de fora) |
| HOSPITAIS / PRONTO-SOCORRO | HOSPITAIS PARA INTERNACAO / **todas** + PRONTO-SOCORRO 24H (URGENCIA E EMERGENCIA) / **todas** |

`"*"` no config significa todas as especialidades daquele tipo de serviço na cidade. O mesmo prestador no mesmo endereço vira **uma linha por categoria**, e a coluna Especialidades junta tudo em que ele apareceu. "PRONTO ATENDIMENTO - HORARIO COMERCIAL" não entra, porque não é pronto-socorro.

## Limitações

- **Brodowski e Rancharia (SP) não aparecem na lista de municípios do Prata QC** no site. Vão para o Resumo como `SEM REDE NO PLANO`.
- **Tatuí (SP)** só tem Laboratórios no plano, e **Araçoiaba da Serra (SP)** não tem hospital nem pronto-socorro. O Resumo mostra 0 e o motivo na coluna Observações.
- **Prestadores de outra cidade.** A busca por município também devolve endereços de cidades vizinhas (por exemplo, Olinda na busca de Recife). As abas de categoria ficam só com os endereços no município pedido. Os das cidades vizinhas vão para a aba **Cidades vizinhas**, com a cidade pesquisada e a categoria, e o Resumo mostra quantos são e de quais municípios. Em cidades pequenas isso pesa: em **Ribeirão Pires** todos os hospitais e prontos-socorros que o site lista ficam em outras cidades, e em **Várzea Grande** todos os ginecologistas e cardiologistas. Nesses casos a categoria sai com 0 na aba da cidade, e os prestadores aparecem em Cidades vizinhas.
- **Tempo.** São ~640 consultas pela tela, cerca de **25 s cada** (medido): **4 a 5 h** para as 24 cidades, sem contar as pausas por bloqueio. Quase metade vem de "Hospitais / Pronto-Socorro" com `"*"`. Para acelerar, troque o `"*"` por especialidades específicas, por exemplo `HOSPITAIS GERAIS` e `MATERNIDADES`.
- **Bloqueio (Akamai).** É o mesmo do Dental, e o IP é o mesmo: rodar a Saúde também desgasta o IP para o Dental. No teste em São Paulo a 1ª sessão fez 19 consultas antes do 403, e a 2ª fez 9. Como o script reage:
  - um 403 descarta a sessão, espera de 1 a 2 min e abre um Chrome novo. Enquanto cada sessão trouxer ao menos uma consulta nova, continua (até 15 sessões por cidade); só desiste depois de 3 sessões seguidas sem avanço, que é o sinal de IP marcado. Na 1ª execução (29/10) cada sessão rendeu 12 a 14 consultas, e o limite antigo de 3 sessões por cidade fez Recife falhar com 35 de 40 feitas;
  - cada resposta é gravada em `documentos/saude/prata_qc/parciais/` assim que chega, e a nova tentativa continua da consulta seguinte;
  - se a cidade falhar, o script faz uma pausa de `--pausa` minutos (padrão 15) antes da próxima, e as que falharam ganham uma 2ª passada no fim;
  - rodar de novo retoma pelos parciais; `--forcar` descarta tudo e recomeça.

  Se quase tudo der 403, o IP está marcado: pare e espere (30 min resolveram no teste) ou use outra rede (o 4G do celular foi o que funcionou no Dental).
- **Conferência de total.** Em cada busca, o total do JSON é comparado com o "Sua busca localizou N prestadores" da tela. Uma divergência sai como aviso no `bot.log`. Nos testes os totais sempre bateram, inclusive em São Paulo (179 em Ginecologia).
- **Sem PDF.** A saída é JSON e planilha. Os templates de PDF existentes são do Dental (logo e textos de odontologia).
