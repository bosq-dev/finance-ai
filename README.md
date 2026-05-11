# Valuation Multiagente

App de chat **open-source** para testes de avaliação de ações usando uma equipe de agentes (orquestrador + pesquisador + calculador) construídos com [CrewAI](https://github.com/crewAIInc/crewAI), [Claude](https://docs.anthropic.com/) e [Streamlit](https://streamlit.io/).

> ⚠️ **Disclaimer**: este projeto é um **módulo de teste de avaliação de ações**. Os cálculos dependem de premissas (WACC, crescimento, etc.) e os dados podem estar desatualizados. **Não constitui recomendação de compra ou venda.** Faça sua própria pesquisa.

## Como funciona

A conversa do usuário passa por uma Crew com 3 papéis:

1. **Orquestrador** — entende o pedido (ticker + método), conduz a conversa e pede ao usuário os parâmetros que faltarem.
2. **Pesquisador** — busca dados fundamentais na internet usando o `web_search` server-tool nativo da API Anthropic (sem chave externa).
3. **Calculador** — invoca uma das 5 funções puras de [`valuation.py`](valuation.py):
   - DCF 3 estágios (`calcular_dcf_simples`)
   - Graham ajustado pela Selic (`calcular_graham_ajustado_selic`)
   - Bazin (`calcular_bazin`)
   - Peter Lynch (`calcular_lynch`)
   - Gordon DDM (`calcular_gordon`)

A UI Streamlit exibe o chat principal e uma **sidebar** com o log de cada step dos agentes.

## Setup

Pré-requisitos: Python ≥ 3.11 e [`uv`](https://docs.astral.sh/uv/).

```bash
# 1. Instalar dependências
uv sync

# 2. Configurar variáveis de ambiente
cp .env.example .env
# edite .env e coloque sua ANTHROPIC_API_KEY

# 3. Rodar o app (escolha uma forma)
uv run valuation-app                # via script registrado em [project.scripts]
```

Abra http://localhost:8501.

Qualquer flag do Streamlit pode ser passada depois — ex: `uv run python -m app --server.port 9000 --server.headless true`.

## Variáveis de ambiente

| Variável | Default | Descrição |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Obrigatória.** Usada pelo LLM dos agentes e pelo `web_search`. |
| `CREWAI_MODEL` | `anthropic/claude-sonnet-4-6` | Modelo dos agentes CrewAI. |
| `ANTHROPIC_SEARCH_MODEL` | `claude-sonnet-4-6` | Modelo da tool de `web_search`. |
| `WEB_SEARCH_MAX_USES` | `5` | Máximo de buscas por chamada do `web_search`. |

## Estrutura

```
.
├── valuation.py                # 5 funções puras de valuation
├── app/
│   ├── streamlit_app.py        # UI Streamlit
│   ├── crew.py                 # Crew, tasks, run_crew
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── search_agent.py
│   │   └── valuation_agent.py
│   └── tools/
│       ├── web_search.py       # CrewAI Tool com web_search Anthropic
│       └── valuation_tools.py  # 5 CrewAI Tools wrappando valuation.py
├── pyproject.toml
└── uv.lock
```

## Exemplos de prompt

- *"Avalie VALE3 pelo método de Bazin"*
- *"Qual o preço justo de PETR4 por DCF?"*
- *"ITUB4 pelo Graham"*
- *"Compare ITSA4 por Bazin e Gordon"*

Se faltar algum parâmetro (ex: WACC para DCF, crescimento esperado para Lynch), o orquestrador **pergunta no chat** antes de calcular — em vez de inventar valores.

## Licença

MIT. Veja [LICENSE](LICENSE) se aplicável.
