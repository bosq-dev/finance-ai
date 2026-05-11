import os
from typing import Type

import anthropic
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

SEARCH_MODEL = os.getenv("ANTHROPIC_SEARCH_MODEL", "claude-sonnet-4-6")
MAX_USES = int(os.getenv("WEB_SEARCH_MAX_USES", "5"))

SYSTEM_PROMPT = """Você é um pesquisador de dados fundamentalistas da bolsa brasileira (B3) e EUA.

Sua tarefa: dado um ticker e/ou um método de valuation, buscar na web os dados fundamentais
necessários. Priorize fontes confiáveis: StatusInvest, Fundamentus, RI da própria empresa, B3,
CVM, Investing.com, Yahoo Finance, Banco Central.

Sempre responda em JSON válido (sem markdown ou texto extra antes/depois), com as chaves que
conseguiu encontrar. Use `null` quando não achar. Inclua sempre a chave `fontes` listando as URLs
consultadas e a chave `data_referencia` com a data do dado mais recente.

Esquema sugerido (omita chaves que não fizerem sentido para o método pedido):
{
  "ticker": "VALE3",
  "empresa": "Vale S.A.",
  "preco_atual": 65.20,
  "lpa_12m": 7.10,
  "vpa": 38.50,
  "dpa_medio_5a": 4.20,
  "dividendo_proximo_ano": 4.50,
  "fcf_atual": 50000000000,
  "num_acoes": 4500000000,
  "divida_liquida": 15000000000,
  "crescimento_lucros_pct_esperado": 8,
  "selic_atual": 0.105,
  "fontes": ["https://..."],
  "data_referencia": "2026-04"
}
"""


class WebSearchInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "Descrição do que buscar. Inclua o ticker e o método de valuation alvo, ex: "
            "'dados fundamentalistas de VALE3 para método de Bazin (DPA médio 5a)'."
        ),
    )


class WebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = (
        "Busca dados fundamentalistas atualizados de ações na internet usando o web_search "
        "nativo da Anthropic. Retorna JSON com LPA, VPA, DPA, FCF, dívida líquida, Selic e "
        "outras métricas conforme disponíveis, com as fontes citadas."
    )
    args_schema: Type[BaseModel] = WebSearchInput

    def _run(self, query: str) -> str:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=SEARCH_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": MAX_USES,
                }
            ],
            messages=[{"role": "user", "content": query}],
        )

        chunks = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        text = "\n".join(chunks).strip()
        return text or "{}"
