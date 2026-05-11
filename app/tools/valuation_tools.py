import json
import math
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# =====================================================
# DCF 3 estágios
# =====================================================
class DcfInput(BaseModel):
    fcf_atual: float = Field(
        description="Fluxo de Caixa Livre do último ano fechado (R$, total da empresa).",
    )
    num_acoes: float = Field(description="Número total de ações em circulação.")
    wacc: float = Field(description="WACC em decimal. Ex: 11 para 11%.")
    crescimento_alto: float = Field(
        description="Crescimento no Estágio 1 em decimal. Ex: 15 para 15%."
    )
    anos_crescimento_alto: int = Field(5, description="Anos no Estágio 1.")
    anos_transicao: int = Field(5, description="Anos no Estágio 2 (transição linear).")
    crescimento_perpetuidade: float = Field(
        5,
        description="Crescimento perpétuo em decimal. Ex: 5 para 5%. Default 5, máx 7.",
    )
    divida_liquida: float = Field(0.0, description="Dívida Bruta - Caixa em R$.")


class DcfTool(BaseTool):
    name: str = "calcular_dcf"
    description: str = (
        "Calcula o preço justo de uma ação pelo método de Fluxo de Caixa Descontado "
        "em 3 estágios: alto crescimento + fase de transição (declínio linear) + perpetuidade. "
        "Use quando o usuário pedir DCF, DCF descontado ou avaliação por fluxo de caixa."
    )
    args_schema: Type[BaseModel] = DcfInput

    def _run(self, **kwargs) -> str:
        metodo = "DCF 3 estágios (alto + transição + perpetuidade)"
        fcf_atual: float = kwargs["fcf_atual"]
        num_acoes: float = kwargs["num_acoes"]
        wacc: float = kwargs["wacc"]
        crescimento_alto: float = kwargs["crescimento_alto"]
        anos_crescimento_alto: int = kwargs.get("anos_crescimento_alto", 5)
        anos_transicao: int = kwargs.get("anos_transicao", 5)
        crescimento_perpetuidade: float = kwargs.get("crescimento_perpetuidade", 5)
        divida_liquida: float = kwargs.get("divida_liquida", 0.0)

        if (
            fcf_atual is None
            or num_acoes is None
            or wacc is None
            or crescimento_alto is None
        ):
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "Parâmetros obrigatórios ausentes (fcf, num_acoes, wacc, g_alto)",
            }
        if num_acoes <= 0:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "Número de ações deve ser positivo",
            }
        if wacc <= crescimento_perpetuidade:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": f"WACC ({wacc:.2%}) deve ser maior que g_perpetuidade ({crescimento_perpetuidade:.2%})",
            }
        if crescimento_perpetuidade > 7:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "Crescimento na perpetuidade > 7% não é sustentável",
            }
        if anos_crescimento_alto < 1:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "anos_crescimento_alto deve ser >= 1",
            }
        if anos_transicao < 0:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "anos_transicao deve ser >= 0",
            }
        if crescimento_alto < crescimento_perpetuidade:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "g_alto deve ser >= g_perpetuidade (caso contrário inverte a lógica do modelo)",
            }

        wacc /= 100
        crescimento_alto /= 100
        crescimento_perpetuidade /= 100

        fcf = fcf_atual

        # ---------- Estágio 1: alto crescimento ----------
        vp_alto = 0.0
        for t in range(1, anos_crescimento_alto + 1):
            fcf *= 1 + crescimento_alto
            vp_alto += fcf / (1 + wacc) ** t

        # ---------- Estágio 2: transição linear ----------
        vp_transicao = 0.0
        if anos_transicao > 0:
            passo = (crescimento_alto - crescimento_perpetuidade) / anos_transicao
            for j in range(1, anos_transicao + 1):
                t = anos_crescimento_alto + j
                g_t = crescimento_alto - passo * j  # cai linearmente
                fcf *= 1 + g_t
                vp_transicao += fcf / (1 + wacc) ** t

        # ---------- Estágio 3: perpetuidade ----------
        fcf_terminal = fcf * (1 + crescimento_perpetuidade)
        valor_terminal = fcf_terminal / (wacc - crescimento_perpetuidade)
        anos_explicitos = anos_crescimento_alto + anos_transicao
        vp_terminal = valor_terminal / (1 + wacc) ** anos_explicitos

        valor_empresa = vp_alto + vp_transicao + vp_terminal
        equity = valor_empresa - (divida_liquida or 0.0)
        preco_justo = equity / num_acoes

        return json.dumps(
            {
                "preco_justo": round(preco_justo, 2),
                "valor_empresa": round(valor_empresa, 2),
                "vp_estagio1_alto": round(vp_alto, 2),
                "vp_estagio2_transicao": round(vp_transicao, 2),
                "vp_estagio3_terminal": round(vp_terminal, 2),
                "peso_terminal_pct": round(100 * vp_terminal / valor_empresa, 1),
                "metodo": metodo,
                "erro": None,
            },
            ensure_ascii=False,
        )


# =====================================================
# Graham ajustado pela Selic
# =====================================================
class GrahamSelicInput(BaseModel):
    lpa: float = Field(
        description="Lucro Por Ação dos últimos 12 meses (R$). Positivo."
    )
    vpa: float = Field(description="Valor Patrimonial por Ação (R$). Positivo.")
    selic: float = Field(
        14.5, description="Taxa Selic atual em decimal. Ex: 10.5 para 10,5%."
    )


class GrahamSelicTool(BaseTool):
    name: str = "calcular_graham_ajustado_selic"
    description: str = (
        "Calcula o preço justo pela fórmula de Graham ajustada à Selic atual. "
        "Use quando o usuário pedir Graham, número de Graham ou avaliação clássica de valor."
    )
    args_schema: Type[BaseModel] = GrahamSelicInput

    def _run(self, **kwargs) -> str:
        metodo = "Graham ajustado pela Selic"
        lpa: float = kwargs["lpa"]
        vpa: float = kwargs["vpa"]
        selic: float = kwargs.get("selic", 14.5)

        if lpa is None or vpa is None:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "LPA e VPA são obrigatórios",
            }
        if lpa <= 0:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "LPA deve ser positivo (Graham só se aplica a empresas lucrativas)",
            }
        if vpa <= 0:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "VPA deve ser positivo (patrimônio líquido positivo)",
            }
        if selic <= 0:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "Selic deve ser positiva",
            }

        pl_max = min(15.0, 1.0 / (selic / 100))
        pb_max = 1.5
        multiplicador = pl_max * pb_max

        preco_justo = math.sqrt(multiplicador * lpa * vpa)

        return json.dumps(
            {
                "preco_justo": round(preco_justo, 2),
                "multiplicador_usado": round(multiplicador, 2),
                "pl_max": round(pl_max, 2),
                "selic_usada": selic,
                "metodo": metodo,
                "erro": None,
            },
            ensure_ascii=False,
        )


# =====================================================
# Bazin
# =====================================================
class BazinInput(BaseModel):
    dpa_medio: float = Field(
        description="Dividendo Por Ação médio anual dos últimos 5 anos (R$). Positivo.",
    )
    dy_desejado: float = Field(
        6,
        description="Dividend yield mínimo aceitável em decimal. Default 6 (6%).",
    )


class BazinTool(BaseTool):
    name: str = "calcular_bazin"
    description: str = (
        "Calcula o preço-teto pelo método de Décio Bazin (foco em renda). "
        "Use quando o usuário pedir Bazin, preço-teto, ou avaliação por dividendos."
    )
    args_schema: Type[BaseModel] = BazinInput

    def _run(self, **kwargs) -> str:
        metodo = "Bazin (preço-teto)"
        dpa_medio: float = kwargs["dpa_medio"]
        dy_desejado: float = kwargs.get("dy_desejado", 6)

        if dpa_medio is None or dpa_medio <= 0:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "DPA médio inexistente ou não positivo. Bazin requer histórico consistente de proventos.",
            }
        if dy_desejado is None or dy_desejado <= 0:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "DY desejado deve ser positivo",
            }

        preco_teto = dpa_medio / (dy_desejado / 100)

        return json.dumps(
            {
                "preco_justo": round(preco_teto, 2),
                "dpa_usado": dpa_medio,
                "dy_desejado": dy_desejado,
                "metodo": metodo,
                "erro": None,
            },
            ensure_ascii=False,
        )


# =====================================================
# Peter Lynch
# =====================================================
class LynchInput(BaseModel):
    lpa: float = Field(
        description="Lucro Por Ação dos últimos 12 meses (R$). Positivo."
    )
    crescimento_lucros_pct: float = Field(
        description="Crescimento anual esperado de lucros em PERCENTUAL (ex: 15 para 15%, NÃO 0.15).",
    )


class LynchTool(BaseTool):
    name: str = "calcular_lynch"
    description: str = (
        "Calcula o preço justo pela fórmula de Peter Lynch (Fair Value: LPA * (8.5 + 2g)). "
        "Use quando o usuário pedir Lynch, Peter Lynch ou avaliação por PEG."
    )
    args_schema: Type[BaseModel] = LynchInput

    def _run(self, **kwargs) -> str:
        metodo = "Peter Lynch"
        lpa: float = kwargs["lpa"]
        crescimento_lucros_pct: float = kwargs["crescimento_lucros_pct"]

        if lpa is None or lpa <= 0:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "LPA deve ser positivo (Lynch não se aplica a empresas em prejuízo)",
            }
        if crescimento_lucros_pct is None:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "Crescimento de lucros é obrigatório",
            }
        if crescimento_lucros_pct < 0:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "Lynch não se aplica a empresas com crescimento negativo de lucros",
            }

        pl_justo = 8.5 + 2 * crescimento_lucros_pct
        pl_justo_cap = min(pl_justo, 40.0)
        capeado = pl_justo > 40.0

        preco_justo = lpa * pl_justo_cap
        peg = (
            pl_justo_cap / crescimento_lucros_pct
            if crescimento_lucros_pct > 0
            else None
        )

        return json.dumps(
            {
                "preco_justo": round(preco_justo, 2),
                "pl_justo": round(pl_justo_cap, 2),
                "peg_implicito": round(peg, 2) if peg else None,
                "capeado_em_40": capeado,
                "crescimento_usado_pct": crescimento_lucros_pct,
                "metodo": metodo,
                "erro": None,
            },
            ensure_ascii=False,
        )


# =====================================================
# Gordon (DDM)
# =====================================================
class GordonInput(BaseModel):
    dividendo_proximo_ano: float = Field(
        description="D1, dividendo esperado nos próximos 12 meses (R$). Positivo."
    )
    custo_capital: float = Field(
        description="k, retorno exigido pelo investidor em decimal. Ex: 0.12."
    )
    crescimento_dividendos: float = Field(
        description="g, crescimento anual perpétuo dos dividendos em decimal. Ex: 5.",
    )


class GordonTool(BaseTool):
    name: str = "calcular_gordon"
    description: str = (
        "Calcula o preço justo pelo Modelo de Crescimento de Gordon (DDM perpétuo: D1/(k-g)). "
        "Use para empresas maduras com dividendos crescentes a taxa constante."
    )
    args_schema: Type[BaseModel] = GordonInput

    def _run(self, **kwargs) -> str:
        metodo = "Gordon DDM"
        dividendo_proximo_ano: float = kwargs["dividendo_proximo_ano"]
        custo_capital: float = kwargs["custo_capital"]
        crescimento_dividendos: float = kwargs["crescimento_dividendos"]

        if dividendo_proximo_ano is None or dividendo_proximo_ano <= 0:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "Dividendo esperado (D1) deve ser positivo",
            }
        if custo_capital is None or crescimento_dividendos is None:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "Custo de capital e crescimento são obrigatórios",
            }
        if custo_capital <= crescimento_dividendos:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": f"Modelo diverge: k ({custo_capital:.2%}) <= g ({crescimento_dividendos:.2%})",
            }
        if crescimento_dividendos > 8:
            return {
                "preco_justo": None,
                "metodo": metodo,
                "erro": "Crescimento perpétuo > 8% é insustentável (acima do PIB real de longo prazo)",
            }

        crescimento_dividendos /= 100
        preco_justo = dividendo_proximo_ano / (custo_capital - crescimento_dividendos)

        return json.dumps(
            {
                "preco_justo": round(preco_justo, 2),
                "d1_usado": dividendo_proximo_ano,
                "k_usado": custo_capital,
                "g_usado": kwargs["crescimento_dividendos"],
                "spread_k_g": round(custo_capital - crescimento_dividendos, 4),
                "metodo": metodo,
                "erro": None,
            },
            ensure_ascii=False,
        )


def all_valuation_tools() -> list[BaseTool]:
    return [DcfTool(), GrahamSelicTool(), BazinTool(), LynchTool(), GordonTool()]
