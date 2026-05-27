# AmilBot - Scraper de Rede Credenciada

Automação para extrair prestadores da rede Amil Dental, gerar PDFs por cidade e consolidar em planilha Excel.

---

## Pré-requisitos

| Requisito | Versão | Link |
|---|---|---|
| Python | **3.11** (recomendado) | [python.org](https://www.python.org/downloads/) |
| Google Chrome | Qualquer | Precisa estar instalado na máquina |
| Wkhtmltopdf | Qualquer | [wkhtmltopdf.org](https://wkhtmltopdf.org/downloads.html) |

> **Atenção:** Use Python 3.11. O PyMuPDF (usado para leitura de PDFs) não tem wheel pré-compilado para versões mais novas e exigiria Visual Studio para compilar.

O `wkhtmltopdf` precisa estar no PATH do Windows. Após instalar, confirme rodando `wkhtmltopdf --version` no terminal.

---

## Instalação

```powershell
git clone https://github.com/ativa-new-corretora/amil-dental-scraper.git
cd amil-dental-scraper
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Scraper Portátil (uso principal)

Gera PDFs em `documentos/pdfs/` e `documentos/pdfs_sem_telefone/`. Pula automaticamente cidades que já têm PDF.

```powershell
# Rodar para todas as cidades (pula existentes)
.\venv\Scripts\python.exe scripts/amil_portable.py

# Rodar apenas cidades estratégicas — capitais + grandes cidades (~112 cidades)
# Sempre regenera, mesmo que o PDF já exista
.\venv\Scripts\python.exe scripts/amil_portable.py --estrategico

# Filtrar por estado(s)
.\venv\Scripts\python.exe scripts/amil_portable.py --uf SP RJ MG

# Filtrar por cidade específica
.\venv\Scripts\python.exe scripts/amil_portable.py --uf SP --cidade "SAO PAULO"

# Combinar: estado estratégico + estado específico
.\venv\Scripts\python.exe scripts/amil_portable.py --estrategico --uf SP
```

> O scraper abre um navegador Chrome por cidade (headless), faz 3 tentativas em caso de shadow block com espera progressiva e limpeza completa de cookies/cache entre tentativas.

---

## Extração Completa (main.py)

Roda o scraping de todas as cidades via `main.py`. Salva progresso e retoma de onde parou. Gera PDFs em `docs/pdfs/`.

```powershell
python main.py
```

### Com Dashboard Web

```powershell
python src/web/app.py
```

Acesse `http://localhost:5000`.

---

## Scripts de Manutenção

### Atualizar lista de cidades

Acessa o site da Amil e atualiza `config/estados_cidades_amil.json` com as cidades disponíveis. Execução: ~10-15 min.

```powershell
.\venv\Scripts\python.exe scripts/extrair_cidades.py
```

### Comparar cidades vs PDFs

Gera relatório mostrando quais cidades do JSON não têm PDF e quais PDFs não estão mais no JSON.

```powershell
.\venv\Scripts\python.exe scripts/comparar_cidades.py
```

### Limpar PDFs obsoletos

Remove PDFs de cidades que saíram do JSON. Sem flag = dry-run (só lista sem apagar).

```powershell
# Ver o que seria apagado
.\venv\Scripts\python.exe scripts/limpar_pdfs_obsoletos.py

# Apagar de verdade
.\venv\Scripts\python.exe scripts/limpar_pdfs_obsoletos.py --deletar
```

### Regenerar todos os PDFs

Relê os PDFs existentes e regenera com o template atual (útil após mudanças no layout).
Aceita `--uf` para filtrar por estado e `--dry-run` para só contar sem gerar.

```powershell
.\venv\Scripts\python.exe scripts/atualizar_referencia.py
.\venv\Scripts\python.exe scripts/atualizar_referencia.py --uf SP RJ
.\venv\Scripts\python.exe scripts/atualizar_referencia.py --dry-run
```

### Regenerar planilha Excel

Reconstrói a planilha varrendo `documentos/pdfs/`.

```powershell
.\venv\Scripts\python.exe scripts/regenerar_planilha.py
```

### Build do Executável (Portátil)

Empacota o bot em EXE para rodar sem Python instalado.

```powershell
python build_exe.py
```

---

## Fluxo de Atualização Mensal

```powershell
# 1. Atualizar lista de cidades do site Amil
.\venv\Scripts\python.exe scripts/extrair_cidades.py

# 2. Ver diferenças vs base de PDFs atual
.\venv\Scripts\python.exe scripts/comparar_cidades.py

# 3. Apagar PDFs obsoletos
.\venv\Scripts\python.exe scripts/limpar_pdfs_obsoletos.py --deletar

# 4. Gerar PDFs das cidades novas (pula existentes)
.\venv\Scripts\python.exe scripts/amil_portable.py

# 5. Regenerar todos com template atualizado
.\venv\Scripts\python.exe scripts/atualizar_referencia.py
```

---

## Estrutura

```
├── main.py                         # Extração completa
├── build_exe.py                    # Build do executável
├── requirements.txt
├── config/
│   ├── estados_cidades_amil.json   # Lista completa de cidades (~968)
│   └── cidades_estrategicas.json   # Capitais + grandes cidades (~112)
├── src/
│   ├── scraper/
│   │   ├── amil_scraper.py         # Bot Selenium (3 tentativas, shadow block aware)
│   │   ├── anti_bot.py             # Anti-detecção (stealth, canvas noise, WebGL)
│   │   └── navegacao.py
│   ├── pdf/
│   │   ├── gerador_pdf.py
│   │   └── templates/              # prestadores.html, sem_especialidade.html
│   ├── utils/
│   │   ├── delays.py
│   │   ├── file_manager.py
│   │   └── logger.py
│   └── web/
│       └── app.py                  # Dashboard Flask
├── scripts/
│   ├── amil_portable.py            # Scraper portátil (uso principal)
│   ├── extrair_cidades.py          # Atualiza JSON de cidades
│   ├── comparar_cidades.py         # Compara JSON vs PDFs
│   ├── limpar_pdfs_obsoletos.py    # Remove PDFs de cidades removidas
│   ├── atualizar_referencia.py     # Regenera PDFs com template atual
│   └── regenerar_planilha.py       # Reconstrói planilha Excel
└── assets/                         # Logos (amil_dental.jpg, logo_ativa.jpg)
```

**Saídas (não versionadas):** `documentos/`, `docs/`, `output/`, `logs/`
