[← Voltar ao README](../README.md)

# 🚀 Como executar localmente

Siga o passo a passo abaixo para clonar, configurar e executar todos os estágios do pipeline e o dashboard localmente:

### 1. Clonar o Repositório

```bash
git clone https://github.com/paulocid95/supply-intelligence.git
cd supply-intelligence
```

### 2. Configurar o Ambiente Virtual

* **No Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```

* **No Linux / macOS:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Instalar Dependências

```bash
pip install -r requirements.txt
```

> As versões das bibliotecas são fixadas no `requirements.txt` para garantir que o projeto rode igual em qualquer máquina e no Streamlit Cloud (requer Python 3.11 ou mais novo).

### 4. Configurar as Variáveis de Ambiente e Segredos

O sistema suporta credenciais tanto por arquivo `.env` quanto pelo arquivo de segredos nativo do Streamlit (`.streamlit/secrets.toml`).

#### Opção A: Configuração via `.env` (Execução Geral e Scripts Locais)
Crie um arquivo `.env` na raiz do projeto contendo as credenciais de banco e IA:

```env
# Banco de Dados PostgreSQL (Neon Serverless)
DATABASE_URL="postgresql://<usuario>:<senha>@<host>/<database>?sslmode=require"

# Chave de API do Google Gemini (obtenha em: https://aistudio.google.com/app/apikey)
GEMINI_API_KEY="AIzaSy..."

# (Opcional) Reserva gratuita do Groq (obtenha em: https://console.groq.com/keys)
GROQ_API_KEY="gsk_..."
```

#### Opção B: Configuração via `.streamlit/secrets.toml` (Streamlit Local e Nuvem)
Para o Dashboard Streamlit e o Assistente de IA, utilize o modelo disponibilizado em `.streamlit/secrets.toml.example`:

1. Crie o arquivo `.streamlit/secrets.toml`:
   ```toml
   # .streamlit/secrets.toml
   GEMINI_API_KEY = "AIzaSy..."
   GROQ_API_KEY = "gsk_..."          # opcional: reserva gratuita
   DATABASE_URL = "postgresql://<usuario>:<senha>@<host>/<database>?sslmode=require"
   ```

2. **No Streamlit Community Cloud (Deploy em Produção):**
   Acesse as configurações do seu aplicativo em **Settings ➔ Secrets** e cole o conteúdo acima. O Streamlit gerenciará essas credenciais de forma segura sem expô-las no repositório público.

### 5. Executar os Scripts na Ordem Correta

Para processar os dados locais, sincronizar com o banco relacional e carregar as cotações concorrentes, execute:

```bash
# 1. Simular e criar os dados brutos com inconsistências (pasta dados_brutos/)
python gerar_dados_brutos.py

# 2. Executar o diagnóstico exploratório de dados e profiling de inconsistências
python exploracao_diagnostico.py

# 3. Executar o pipeline de limpeza, padronização e consolidação (salva em dados_processados/)
python limpeza_padronizacao.py

# 4. Calcular métricas financeiras de negócio, alertas de ruptura e exportar KPIs
python analise_negocio.py

# 5. Gerar e salvar os gráficos executivos em alta resolução (pasta graficos/)
python visualizacao_graficos.py

# 6. Provisionar o schema relacional e as tabelas (incluindo cotações) no PostgreSQL
python criar_tabelas.py

# 7. Executar a ingestão dimensional com lógica de Upsert no banco de dados
python carregar_dados.py

# 8. Simular a matriz de cotações dos fornecedores e alimentar o banco de dados
python gerar_cotacoes_fornecedores.py

# 9. Gerar o histórico de ocorrências com fornecedores (ranking e risco)
python gerar_ocorrencias_fornecedores.py

# 10. Executar validações, consultas analíticas de auditoria e o ranking de fornecedores
python consultar_banco.py
```

> 💡 **Execução Automatizada:** Você também pode rodar toda a esteira de engenharia de dados com o orquestrador unificado:
> ```bash
> python pipeline_completo.py
> ```

> 🧪 **Testes Automatizados:** mais de 200 testes com `pytest` cobrem a limpeza do pipeline e das planilhas enviadas, o status de reposição, a nota e a classificação dos fornecedores, a previsão de demanda, o pedido de compra e o assistente de IA (incluindo a reserva Groq):
> ```bash
> pip install -r requirements-dev.txt
> pytest
> ```

### 6. Iniciar o Dashboard Interativo Localmente

Para rodar o painel analítico localmente consumindo a base do Neon:

```powershell
streamlit run app.py
```

A aplicação será aberta automaticamente em seu navegador padrão no endereço `http://localhost:8501`.

> 🚀 **Prefere testar sem instalar nada?** Acesse a versão já implantada em produção no [Streamlit Community Cloud](https://estoque-dashboard-live.streamlit.app).
