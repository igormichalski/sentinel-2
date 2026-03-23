# Dataset de Imagens de Satélite: Golfo de St. Lawrence (Sentinel-2)

## 📌 Visão Geral
Este dataset consiste em imagens multiespectrais provenientes do satélite **Sentinel-2 (Level-2A)**, processadas especificamente para a região do **Golfo de St. Lawrence, Canadá**. O objetivo deste conjunto de dados é fornecer insumos de alta qualidade para pesquisas em predição climática e modelos de Machine Learning.

Diferente dos dados brutos da ESA, este dataset passou por um pipeline de otimização que realiza o recorte espacial (cropping) e a conversão de formato para maximizar a performance de processamento.

---

## 🛠️ Pipeline de Processamento
O conjunto de dados foi gerado através de duas etapas principais:

1.  **Aquisição Automatizada (`satellite_downloader.py`):** Realiza a busca e o download seletivo de produtos `S2MSI2A` via API do *Copernicus Data Space Ecosystem*. O script garante downloads atômicos e validação de integridade por tamanho de arquivo.
2.  **Recorte e Padronização (`crop_pipeline.py`):** * **Cropping:** As imagens originais foram recortadas utilizando uma máscara vetorial manual do Golfo bem próxima a água (`map.geojson`).
    * **Conversão GeoTIFF:** O formato original JPEG2000 (.jp2) é convertido para **GeoTIFF (.tif)** utilizando compressão *Lossless Deflate* e preditor nível 2, garantindo que não haja perda de informação radiométrica.
    * **Recálculo de Metadados:** As porcentagens de cobertura de nuvens e *NoData* foram recalculadas com base exclusivamente na área recortada.
    * **Geração do Metadados pós-processamento (`cropped_metadata.xml`):** Os dados recalculados e alterados estão no arquivo `cropped_metadata.xml` para manter os aquivos de matadados originais das imagens intactos. 

---

## 📂 Estrutura de Arquivos e Caminhos
Os dados estão organizados por Ano e por pastas `.SAFE` individuais para cada cena, mantendo a nomenclatura original para rastreabilidade.

**Caminho Base:** `/meridian/sat_download/sentinel-2/`

### Exemplo de Estrutura de Diretórios:
```text
/sentinel-2/
│
├── inventario_cropped_teste_formatado.csv     # Catálogo completo (Nuvem, NoData, Tiles)
├── map.geojson                                # Polígono da área de interesse
│
└── [ANO]/                                     # Ex: 2016, 2022
    └── [NOME_DA_CENA].SAFE/                   # Pasta da cena (Ex: S2A_MSIL2A_20160106...)
        ├── MTD_MSIL2A.xml                     # Metadados originais da ESA
        ├── cropped_metadata.xml               # Metadados pós-processamento (Recálculo)
        │
        # --- IMAGENS GEOTIFF (RECORTE GOLFO) ---
        ├── [NOME]_B02_10m.tif                 # Banda Azul (490nm)
        ├── [NOME]_B03_10m.tif                 # Banda Verde (560nm)
        ├── [NOME]_B04_10m.tif                 # Banda Vermelha (665nm)
        ├── [NOME]_B08_10m.tif                 # NIR (842nm)
        ├── [NOME]_WVP_10m.tif                 # Water Vapor (Vapor de Água)
        ├── [NOME]_AOT_10m.tif                 # Aerosol Optical Thickness
        ├── [NOME]_SCL_20m.tif                 # Scene Classification Map
        ├── [NOME]_B01_60m.tif                 # Coastal Aerosol
        └── [NOME]_B09_60m.tif                 # Water Vapor
```
---

## 📋 Especificações das Bandas Extraídas
As seguintes bandas foram selecionadas por sua relevância técnica para a análise do Golfo:

| Banda | Descrição | Resolução Original |
| :--- | :--- | :--- |
| **B01** | Coastal Aerosol | 60m |
| **B02, B03, B04**| Blue, Green, Red | 10m |
| **B08** | NIR | 10m |
| **B09** | Water Vapor | 60m |
| **WVP** | **Water Vapor** | **10m** |
| **AOT** | **Aerosol Optical Thickness** | **10m** |
| **SCL** | Scene Classification | 20m |

---

## 🗺️ Mapa de Cobertura (Tiles Processados)
Abaixo estão os Tiles Sentinel-2 que compõem a cobertura deste dataset no Golfo de St. Lawrence:

| Zona | Tiles Disponíveis |
| :--- | :--- |
| **Oeste** | T19TGM, T19TGN, T19UDP, T19UDQ, T19UEP, T19UEQ, T19UFP, T19UFQ, T19UFR |
| **Central** | T19UGP, T19UGQ, T19UGR, T20TLR, T20TLS, T20TLT, T20TMR, T20TMS, T20TMT, T20ULA, T20ULU, T20ULV |
| **Leste** | T20TNR, T20TNS, T20TNT, T20TPR, T20TPS, T20TPT, T20TQS, T20TQT, T20UMA, T20UMU, T20UMV, T20UNA |
| **Extremo Leste** | T20UNU, T20UNV, T20UPA, T20UPU, T20UPV, T20UQA, T20UQB, T20UQU, T20UQV, T21TUM |
| **Norte/Leste** | T21TUN, T21TVN, T21UUP, T21UUQ, T21UUR, T21UUS, T21UVP, T21UVQ, T21UVR, T21UVS, T21UVT |

## Mapa dos Tiles
<img width="4200" height="2950" alt="mapa_cobertura_tiles" src="https://github.com/user-attachments/assets/f62d2025-ff29-4b03-8d13-3c8288b41f9c" />

## Foto real

<img width="1246" height="946" alt="image" src="https://github.com/user-attachments/assets/36beb637-847b-48a7-b085-b1500505c16c" />

---

## 📈 Estatísticas Atuais do Dataset
*Preencha as informações abaixo após a execução final do pipeline:*

* **Quantidade de Tiles:** `54`
* **Cenas Totais:** `______`
* **Período Temporal:** `______` a `______`
* **Espaço Total em Disco:** `______ GB`
* **Configuração de Compressão:** `GeoTIFF (Deflate, Predictor 2)`

---

## 🚀 Como Executar o Pipeline de Aquisição (`satellite_downloader.py`)

Esta seção descreve os passos necessários para configurar o ambiente e executar o script de download automatizado.

### 1. Pré-requisitos
O script utiliza a biblioteca **Rich** para interface visual e **Aiohttp/Aiofiles** para operações assíncronas de alta performance.

* **Python**: 3.10 ou superior.
* **Conta CDSE**: É necessário ter um cadastro no [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/).

### 2. Configuração do Ambiente Virtual (`venv`)
Recomenda-se o uso de um ambiente virtual para isolar as dependências:

```bash
# Criar o ambiente virtual
python3 -m venv venv

# Ativar o ambiente
# No Linux/macOS:
source venv/bin/activate
# No Windows:
.\venv\Scripts\activate

# Instalar as dependências
pip install requests aiohttp aiofiles rich
```
### 3. Configuração de Credenciais e Variáveis
Antes de rodar, abra o arquivo `satellite_downloader.py` e ajuste as seguintes constantes no bloco de `CONFIGURATION`:

* **`USERNAME` / `PASSWORD`**: Suas credenciais do portal Copernicus.
* **`DATE_START` / `DATE_END`**: O intervalo temporal desejado para a busca.
* **`DOWNLOAD_DIR`**: O caminho absoluto onde os dados serão salvos (Ex: `/meridian/sat_download/sentinel-2/2022`).
* **`CONCURRENCY_LIMIT`**: Número de downloads simultâneos (padrão: 4).

### 4. Execução em Segundo Plano (Background)
Em ambientes de servidor, é essencial que o script continue processando mesmo após o fechamento do terminal. Para isso, utilizamos o `nohup`.

#### 4.1 Executando com Logs por Ano
Para manter a organização, recomendamos redirecionar a saída para um arquivo de log específico para o ano correspondente:

```bash
# Executa o script ignorando o fechamento do terminal
# Substitua '2022' pelo ano configurado no seu script
nohup python3 satellite_downloader.py > log2022.txt 2>&1 &
```
#### 4.2 Comandos Úteis de Gerenciamento

| Objetivo | Comando |
| :--- | :--- |
| **Acompanhar o progresso** | `tail -f log2022.txt` |
| **Verificar se ainda está rodando** | `ps aux | grep satellite_downloader.py` |
| **Parar a execução** | `pkill -f satellite_downloader.py` |
| **Verificar tamanho do log** | `du -h log2022.txt` |

### 5. Tratamento de Erros e Validação
* **Falhas de Download**: Caso ocorram erros de rede ou timeout persistentes após as 20 tentativas configuradas, o script gerará um arquivo chamado `FAILED_[TIMESTAMP].txt` dentro do diretório de download com a lista de caminhos dos arquivos que falharam.
* **Validação de Integridade**: O script verifica automaticamente o tamanho do arquivo (`Content-Length`) antes de finalizar o download atômico. Se o tamanho baixado não coincidir com o esperado, o arquivo `.part` é descartado e o download é reiniciado.


**Responsável:** João Pedro Recalcatti and Igor Roberto Michalski 
**Instituição:** UEMS/BRAZIL  
**Data de Criação:** 21 de Março de 2026
