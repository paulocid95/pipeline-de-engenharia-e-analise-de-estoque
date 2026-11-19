# 📦 Supply Intelligence

**Português** · [English](README.en.md)

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://estoque-dashboard-live.streamlit.app)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?logo=pandas&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-336791?logo=postgresql&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Google%20Gemini-4285F4?logo=googlegemini&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-reserva-F55036)
![statsmodels](https://img.shields.io/badge/statsmodels-previsão-4C72B0)
![Testes](https://img.shields.io/badge/testes-200%2B%20pytest-0A9EDC?logo=pytest&logoColor=white)
[![Licença](https://img.shields.io/badge/Licença-MIT-green)](LICENSE)

**Sua planilha bagunçada vira decisão de compra.** Envie o Excel ou CSV do jeito que sai do sistema da loja: o Supply Intelligence limpa e padroniza os dados, mostra a saúde do estoque, ranqueia os fornecedores por preço, prazo e confiabilidade, prevê a demanda de cada produto e gera o pedido de compra pronto para enviar, com um assistente de IA para tirar dúvidas.

### 🚀 [Abrir a demonstração ao vivo](https://estoque-dashboard-live.streamlit.app)

![Demonstração: enviar planilha, ver a análise, prever a demanda e baixar o pedido de compra](docs/img/demonstracao.gif)

---

## ✨ Destaques

| Recurso | O que faz |
| :--- | :--- |
| 🧹 **Higienização automática** | Reconhece as colunas mesmo com nomes diferentes, converte preços, quantidades e datas bagunçados, unifica grafias de fornecedores e mostra um relatório de tudo o que corrigiu. [Saiba mais](docs/higienizacao.md) |
| 🛡️ **Ranking de fornecedores** | Nota de 0 a 100 por preço, prazo, lote mínimo e histórico de problemas (atrasos, defeitos, processos). Classifica em 🟢 Bom, 🟡 Médio ou 🔴 Perigoso e nunca recomenda um 🔴. [Saiba mais](docs/fornecedores-e-ia.md) |
| 📈 **Previsão de demanda** | Detecta o calendário da loja e faz 4 modelos competirem por produto (Holt-Winters, Croston, média móvel e ingênuo sazonal). Mostra quando o estoque acaba, com faixa de incerteza e nível de confiança. [Saiba mais](docs/previsao-de-demanda.md) |
| 📝 **Pedido de compra** | Tabela editável e Excel com uma aba por fornecedor: quantidade arredondada pelo lote, preço, subtotal, chegada prevista e motivo da compra. |
| 🤖 **Assistente de IA** | Google Gemini com reserva gratuita no Groq, respondendo com base nos dados reais do painel (estoque, ranking, previsão). [Saiba mais](docs/fornecedores-e-ia.md#-assistente-de-ia--inteligência-de-compras-google-gemini--reserva-groq) |
| 🔒 **Privacidade** | A planilha enviada fica só na sessão do navegador e some ao fechar a página. Nada é gravado no banco. |

## 🖼️ Telas

| Página inicial | Visão geral |
| :---: | :---: |
| ![Página inicial](docs/img/inicio.png) | ![Visão geral do estoque](docs/img/visao-geral.png) |
| **Previsão de demanda** | **Pedido de compra** |
| ![Previsão de demanda de um produto](docs/img/previsao.png) | ![Pedido de compra editável](docs/img/pedido-compra.png) |
| **Fornecedores: ofertas não recomendadas** | **Assistente de IA** |
| ![Ofertas com fornecedor perigoso em vermelho](docs/img/ofertas-fornecedores.png) | ![Assistente de IA](docs/img/assistente-ia.png) |

## 🏗️ Como é construído

```text
Planilha do usuário ──▶ higienizacao/ ──┐            (só na sessão do navegador)
                                         ├──▶ Painel Streamlit (7 abas) ◀──▶ Gemini → reserva Groq
Pipeline ETL (demo) ──▶ Neon PostgreSQL ─┘         │
  (profiling, limpeza, Star Schema)                ├── regras_fornecedores.py (nota e risco)
                                                   ├── previsao_demanda.py   (competição de modelos)
                                                   └── pedido_compra.py      (Excel por fornecedor)
```

* **Engenharia de dados:** pipeline ETL em Python e Pandas com profiling, schema canônico, carga em *Star Schema* no Neon PostgreSQL (SQLAlchemy, upsert idempotente, `CHECK constraints`) e orquestração com logs. [Arquitetura completa](docs/arquitetura.md)
* **Regras de negócio isoladas e testadas:** estoque, fornecedores, previsão e pedido ficam em módulos sem acesso ao banco, cobertos por mais de 200 testes com `pytest`.
* **IA resiliente:** cascata de modelos do Gemini com tempo limite, reserva no Groq com contexto enxuto, limite de perguntas por sessão e erros sem expor dados.
* **Interface:** Streamlit com CSS próprio, tema claro/escuro, layout para celular e gráficos Plotly.

## 📚 Documentação

* [🏗️ Arquitetura e engenharia de dados](docs/arquitetura.md): problema de negócio, pipeline, banco, decisões técnicas e estrutura de pastas.
* [🧹 Envio e higienização de planilhas](docs/higienizacao.md)
* [🛡️ Fornecedores e assistente de IA](docs/fornecedores-e-ia.md)
* [🔮 Previsão de demanda e pedido de compra](docs/previsao-de-demanda.md)
* [🚀 Como executar localmente](docs/como-executar.md)

## ⚡ Rodar localmente

```bash
git clone https://github.com/paulocid95/supply-intelligence.git
cd supply-intelligence
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

A demonstração lê os dados do PostgreSQL e o assistente usa as chaves de IA, ambos configurados em `.streamlit/secrets.toml` (modelo em `.streamlit/secrets.toml.example`). Veja o [passo a passo completo](docs/como-executar.md), incluindo como criar e carregar o banco com o pipeline.

## 👨‍💻 Autor

Desenvolvido por **Paulo Cid** · Engenharia e Análise de Dados com Python, PostgreSQL e Streamlit · GitHub: [@paulocid95](https://github.com/paulocid95)

Licença [MIT](LICENSE).
