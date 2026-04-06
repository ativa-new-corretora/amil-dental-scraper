import os
import pandas as pd
from urllib.parse import quote

def regenerar_planilha():
    base_dir = os.path.join("docs", "pdfs")
    output_file = os.path.join("docs", "planilhas", "planilha_simples.xlsx")
    
    # Lista para armazenar os dados
    dados = []
    
    print(f"Varrendo diretório: {base_dir}...")
    
    # Varre o diretório base (docs/pdfs)
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.lower().endswith(".pdf"):
                # Obtém o nome da pasta (UF) e o nome do arquivo
                uf = os.path.basename(root)
                filename = file
                
                # Assume que o UF é o nome da pasta onde o arquivo está
                # Ex: docs/pdfs/SP/SAO_PAULO-SP.pdf -> UF = SP
                
                # Extrai a cidade do nome do arquivo (opcional, dependendo do formato exato desejado na planilha)
                # Se o arquivo for "CIDADE-UF.pdf", podemos tentar limpar
                cidade_nome = os.path.splitext(filename)[0]
                # Remove o sufixo -UF se existir, para deixar só o nome da cidade mais limpo na coluna Cidade, se preferir
                # Mas o usuário pediu para "regenerar a planilha", então vamos manter simples ou tentar inferir.
                # Geralmente o nome do arquivo já é a cidade formatada.
                # Vamos manter o nome base do arquivo como "Cidade" por enquanto, ou limpar o sufixo.
                if cidade_nome.endswith(f"-{uf}"):
                     cidade_nome = cidade_nome[:-(len(uf)+1)]
                
                # Constrói o link
                # URL Base: https://odontoplanos.online/rede/
                # Formato: https://odontoplanos.online/rede/{UF}/{Filename}
                # Importante: quote para lidar com espaços e caracteres especiais se houver
                # Mas o exemplo dado era "CIDADE-UF.pdf", então talvez não precise de muito encode, mas é boa prática.
                
                # O usuário reclamou que não é 'rede-porto', é 'rede'.
                url = f"https://odontoplanos.online/rede/{uf}/{filename}"
                
                dados.append({
                    "Cidade": cidade_nome.replace("_", " "), # Remove underscores para ficar mais bonito
                    "UF": uf,
                    "Link": url
                })
    
    # Cria o DataFrame
    df = pd.DataFrame(dados)
    
    # Ordena por UF e Cidade
    if not df.empty:
        df = df.sort_values(by=["UF", "Cidade"])
        
        # Adiciona coluna Id sequencial (começando de 1)
        # Insere na primeira posição
        df.insert(0, 'Id', range(1, len(df) + 1))
    
    print(f"Encontrados {len(df)} arquivos PDF.")
    
    # Garante que o diretório de destino existe
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Salva em Excel
    try:
        df.to_excel(output_file, index=False)
        print(f"Planilha salva com sucesso em: {output_file}")
    except Exception as e:
        print(f"Erro ao salvar a planilha: {e}")

if __name__ == "__main__":
    # Ajusta o diretório de trabalho para a raiz do projeto se necessário
    # Assumindo que o script é rodado da raiz ou que os caminhos são relativos corretamente
    # Se rodar de 'scripts/', precisa subir um nível para achar 'docs/'
    if os.path.basename(os.getcwd()) == "scripts":
        os.chdir("..")
        
    regenerar_planilha()
