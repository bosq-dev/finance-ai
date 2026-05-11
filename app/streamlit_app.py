import os
import sys
from pathlib import Path

# Quando o Streamlit roda este arquivo diretamente ele o trata como `__main__`
# (sem __package__), então imports relativos quebram. Garantimos que a raiz do
# projeto está no sys.path e usamos import absoluto.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from app.crew import stream_crew  # noqa: E402

st.set_page_config(
    page_title="Valuation Multiagente",
    page_icon="📊",
    layout="wide",
)

# ---------- Estado ----------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent_log" not in st.session_state:
    st.session_state.agent_log = []

# ---------- Sidebar ----------
with st.sidebar:
    st.title("🤖 Agentes")
    st.caption("Histórico acumulado de steps. O andamento ao vivo aparece no chat.")

    api_key_env = os.getenv("ANTHROPIC_API_KEY", "")
    api_key_input = st.text_input(
        "ANTHROPIC_API_KEY",
        value="" if api_key_env else "",
        type="password",
        help="Necessária para Claude (LLM) e web_search nativo. Deixe vazio se já estiver em .env.",
    )
    if api_key_input:
        os.environ["ANTHROPIC_API_KEY"] = api_key_input

    st.divider()

    if st.button("🧹 Limpar conversa", use_container_width=True):
        st.session_state.messages = []
        st.session_state.agent_log = []
        st.rerun()

    st.divider()

    if not st.session_state.agent_log:
        st.info("Nenhuma atividade ainda. Faça uma pergunta no chat.")
    else:
        for i, step in enumerate(reversed(st.session_state.agent_log[-30:]), 1):
            agent = step.get("agent") or "?"
            tool = step.get("tool")
            label = (
                f"{agent} · {tool}" if tool else f"{agent} · {step.get('type', 'step')}"
            )
            with st.expander(
                f"#{len(st.session_state.agent_log) - i + 1} {label}", expanded=False
            ):
                if step.get("tool_input"):
                    st.markdown("**Input:**")
                    st.code(step["tool_input"], language="json")
                if step.get("output"):
                    st.markdown("**Output:**")
                    st.code(step["output"], language="json")

# ---------- Main ----------
st.title("📊 Valuation Multiagente")
st.warning(
    "⚠️ Este app é **apenas um módulo de teste de avaliação de ações**. "
    "**Não constitui recomendação de compra ou venda.** Os cálculos dependem de premissas "
    "(WACC, crescimento, etc.) e os dados podem estar desatualizados. Faça sua própria pesquisa."
)

with st.expander("ℹ️ Como usar"):
    st.markdown(
        """
**Métodos disponíveis:**
1. **DCF 3 estágios** — fluxo de caixa descontado (alto crescimento + transição + perpetuidade)
2. **Graham ajustado pela Selic** — Graham clássico ajustado ao juro brasileiro
3. **Bazin** — preço-teto baseado em dividendos
4. **Peter Lynch** — Fair Value via PEG implícito
5. **Gordon DDM** — Dividend Discount Model perpétuo

**Exemplos de prompt:**
- *"Avalie VALE3 pelo método de Bazin"*
- *"Qual o preço justo de PETR4 por DCF?"*
- *"ITUB4 pelo Graham"*
- *"Compare ITSA4 por Bazin e Gordon"*
"""
    )

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Sobre qual ação você quer conversar?")

if prompt:
    if not os.getenv("ANTHROPIC_API_KEY"):
        st.error(
            "ANTHROPIC_API_KEY não configurada. Preencha na sidebar ou no arquivo .env."
        )
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    ICONS = {
        "kickoff_start": "🚀",
        "kickoff_end": "🏁",
        "task_start": "📋",
        "task_end": "✓",
        "agent_start": "▶️",
        "agent_end": "⏹️",
        "tool_start": "🔧",
        "tool_end": "✅",
    }

    with st.chat_message("assistant"):
        status = st.status("🤖 Agentes trabalhando...", expanded=True)

        history_for_crew = st.session_state.messages[:-1]
        reply: str | None = None
        error_msg: str | None = None
        agent_log: list[dict] = []
        step_n = 0

        for ev in stream_crew(prompt, history_for_crew):
            kind = ev.get("kind")

            if kind == "result":
                reply = ev.get("reply") or ""
                continue
            if kind == "error":
                error_msg = ev.get("message") or "erro desconhecido"
                continue

            step_n += 1
            agent = ev.get("agent") or "?"
            tool = ev.get("tool")
            icon = ICONS.get(kind, "•")
            header = f"{icon} **{agent}**"
            if tool:
                header += f" · `{tool}`"
            else:
                header += f" · _{kind}_"

            with status:
                st.markdown(header)
                if ev.get("args"):
                    with st.expander("📥 args", expanded=False):
                        st.code(ev["args"], language="json")
                if ev.get("output") and kind in ("tool_end", "agent_end", "task_end"):
                    with st.expander("📤 output", expanded=False):
                        st.code(ev["output"], language="json")

            label_extra = f" · {tool}" if tool else ""
            status.update(
                label=f"{icon} {agent}{label_extra}", state="running"
            )

            agent_log.append(
                {
                    "agent": agent,
                    "tool": tool,
                    "type": kind,
                    "tool_input": ev.get("args"),
                    "output": ev.get("output"),
                }
            )

        if error_msg:
            status.update(label=f"❌ Erro: {error_msg}", state="error", expanded=True)
            reply = f"❌ Erro ao executar a Crew: `{error_msg}`"
        else:
            status.update(
                label=f"✅ Concluído ({step_n} eventos)",
                state="complete",
                expanded=False,
            )

        st.markdown(reply or "_(sem resposta)_")
        st.session_state.messages.append(
            {"role": "assistant", "content": reply or "_(sem resposta)_"}
        )
        st.session_state.agent_log.extend(agent_log)
        st.rerun()
