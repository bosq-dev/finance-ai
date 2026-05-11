from crewai import LLM, Agent

from app.tools.web_search import WebSearchTool


def build_search_agent(llm: LLM) -> Agent:
    return Agent(
        role="Pesquisador de dados fundamentalistas",
        goal=(
            "Dado um ticker e o método de valuation alvo, buscar na internet os dados "
            "fundamentais necessários (LPA, VPA, DPA, FCF, dívida líquida, num_acoes, Selic, "
            "etc.) e devolvê-los em JSON com as fontes citadas."
        ),
        backstory=(
            "Você é um analista de research com acesso a buscas web. Você conhece bem "
            "StatusInvest, Fundamentus, RI das empresas, B3, CVM, Investing.com e Yahoo "
            "Finance. Sempre cita as fontes e a data do dado. Quando o dado não existir "
            "publicamente, retorna `null` em vez de inventar.\n\n"
            "IMPORTANTE: sua saída deve ser SEMPRE um JSON válido, sem texto extra antes ou "
            "depois, sem blocos de markdown. Inclua sempre as chaves `fontes` (lista de URLs) "
            "e `data_referencia` (mês/ano do dado mais recente)."
        ),
        tools=[WebSearchTool()],
        llm=llm,
        allow_delegation=False,
        verbose=True,
    )
