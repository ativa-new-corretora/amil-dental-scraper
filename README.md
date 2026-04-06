# AmilBot - Scraper de Rede Credenciada

Automação para extrair prestadores da rede Amil Dental, gerar PDFs por cidade e consolidar em planilha Excel.

---

## Pré-requisitos

| Requisito | Versão | Link |
|---|---|---|
| Python | 3.10+ | [python.org](https://www.python.org/downloads/) |
| Google Chrome | Qualquer | Precisa estar instalado na máquina |
| Wkhtmltopdf | Qualquer | [wkhtmltopdf.org](https://wkhtmltopdf.org/downloads.html) |

O `wkhtmltopdf` precisa estar no PATH do Windows. Após instalar, confirme rodando `wkhtmltopdf --version` no terminal.

---

## Instalação

```bash
git clone https://github.com/ativa-new-corretora/amil-dental-scraper.git
cd amil-dental-scraper
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

---

## Extração Completa

Roda o scraping de todas as cidades configuradas em `config/estados_cidades_amil.json`. Gera PDFs em `docs/pdfs/` e consolida tudo em planilha Excel. Salva progresso automaticamente e retoma de onde parou em caso de queda.

```bash
python main.py
```

### Com Dashboard Web

Para acompanhar visualmente com interface no navegador (pausar, retomar, ver logs):

```bash
python src/web/app.py
```

Acesse `http://localhost:5000`.

---

## Scripts Auxiliares

### Extrator de Cidades

Extrai a lista de cidades disponíveis no site da Amil e atualiza `config/estados_cidades_amil.json`.

```bash
python scripts/extrair_cidades.py
```

### Comparador de Cidades

Compara as cidades do JSON com os PDFs já gerados. Identifica novas e removidas.

```bash
python scripts/comparar_cidades.py
```

### Gerador de PDFs sem Telefone

Gera cópias dos PDFs existentes sem o campo telefone.

```bash
python scripts/gerar_pdfs_sem_telefone.py
```

### Regenerador de PDFs

Regenera PDFs trocando o mês de referência sem refazer scraping.

```bash
python scripts/regenerar_pdfs_dezembro.py
```

### Regenerador de Planilha

Reconstrói a planilha Excel varrendo `docs/pdfs/`.

```bash
python scripts/regenerar_planilha.py
```

### Listador de Cidades Grandes

Lista cidades com mais de 11 prestadores.

```bash
python scripts/listar_cidades_grandes.py
```

### Smart Update

Compara quantidade de prestadores entre PDF local e site. Se igual, só atualiza data. Se diferente, faz scraping. Para atualizações pontuais.

```bash
python scripts/smart_update.py
python scripts/smart_update.py --uf AC AL BA
python scripts/smart_update.py --mes "Abril / 2026"
```

---

## Build do Executável (Portátil)

Empacota o bot em EXE para rodar sem Python instalado.

```bash
python build_exe.py
```

Uso:
```bash
amil_bot_portatil.exe
amil_bot_portatil.exe --uf SP RJ
amil_bot_portatil.exe --mes "Abril / 2026"
```

Requer `estados_cidades_amil.json` na mesma pasta do EXE.

---

## Estrutura

```
├── main.py                    # Extração completa (ponto de entrada)
├── build_exe.py               # Build do executável
├── requirements.txt           # Dependências
├── config/
│   └── estados_cidades_amil.json
├── src/
│   ├── scraper/
│   │   ├── amil_scraper.py    # Bot (Selenium)
│   │   ├── anti_bot.py        # Anti-detecção
│   │   └── navegacao.py       # Navegação
│   ├── pdf/
│   │   ├── gerador_pdf.py     # Geração de PDFs
│   │   └── templates/         # Templates HTML
│   ├── utils/
│   │   ├── delays.py
│   │   ├── file_manager.py
│   │   └── logger.py
│   └── web/
│       ├── app.py             # Dashboard Flask
│       ├── static/
│       └── templates/
├── scripts/                   # Scripts auxiliares
└── assets/                    # Logos
```

**Saídas (não versionadas):** `docs/`, `output/`, `logs/`