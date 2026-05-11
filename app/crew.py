import os
import queue
import threading
from typing import Any, Iterator

from crewai import LLM, Crew, Process, Task
from crewai.events import crewai_event_bus
from crewai.events.types.agent_events import (
    AgentExecutionCompletedEvent,
    AgentExecutionStartedEvent,
)
from crewai.events.types.crew_events import (
    CrewKickoffCompletedEvent,
    CrewKickoffStartedEvent,
)
from crewai.events.types.task_events import TaskCompletedEvent, TaskStartedEvent
from crewai.events.types.tool_usage_events import (
    ToolUsageFinishedEvent,
    ToolUsageStartedEvent,
)

from .agents.orchestrator import build_orchestrator
from .agents.search_agent import build_search_agent
from .agents.valuation_agent import build_valuation_agent

DEFAULT_MODEL = os.getenv("CREWAI_MODEL", "anthropic/claude-sonnet-4-6")

# Sentinel para sinalizar fim do stream.
_DONE = object()


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(nenhuma — primeira mensagem)"
    linhas = []
    for msg in history:
        papel = "Usuário" if msg["role"] == "user" else "Assistente"
        linhas.append(f"{papel}: {msg['content']}")
    return "\n".join(linhas)


def _truncate(s: Any, n: int = 1500) -> str:
    if s is None:
        return ""
    text = str(s)
    return text if len(text) <= n else text[:n] + "…"


def _build_crew(user_message: str, history: list[dict]) -> Crew:
    llm = LLM(model=DEFAULT_MODEL, temperature=0.2)

    orchestrator = build_orchestrator(llm)
    search_agent = build_search_agent(llm)
    valuation_agent = build_valuation_agent(llm)

    history_text = _format_history(history)

    task = Task(
        description=(
            "Conversa até agora:\n"
            f"{history_text}\n\n"
            "Mensagem atual do usuário:\n"
            f'"""{user_message}"""\n\n'
            "Siga o fluxo do orquestrador: identifique ticker e método, delegue ao "
            "Pesquisador a busca dos dados, pergunte ao usuário qualquer parâmetro essencial "
            "que ainda falte, e só então delegue ao Calculador para obter o preço justo. "
            "Quando faltar parâmetro, NÃO chame o Calculador — responda diretamente ao "
            "usuário com a pergunta. Lembre o usuário do disclaimer (não é recomendação)."
        ),
        expected_output=(
            "Texto em português direcionado ao usuário. Se faltar parâmetro, uma pergunta "
            "clara e objetiva. Se houver resultado, o preço justo formatado, o método "
            "usado, as premissas adotadas, as fontes consultadas e o disclaimer."
        ),
    )

    return Crew(
        agents=[search_agent, valuation_agent],
        tasks=[task],
        manager_agent=orchestrator,
        process=Process.hierarchical,
        verbose=True,
    )


def stream_crew(user_message: str, history: list[dict]) -> Iterator[dict]:
    """Executa a Crew em uma thread worker e yielda eventos em tempo real.

    Eventos têm a forma:
        {"kind": "agent_start"|"agent_end"|"tool_start"|"tool_end"|"task_start"|...,
         "agent": str, "tool": str|None, "args": str|None, "output": str|None}

    O último evento é sempre {"kind": "result", "reply": str} (ou "error" com "message").
    """
    q: queue.Queue = queue.Queue()

    def emit(payload: dict) -> None:
        q.put(payload)

    # Subscribers — registrados em escopo isolado para que outras execuções não interfiram.
    def _register_handlers() -> None:
        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def _(source, event):
            emit({"kind": "kickoff_start", "agent": "Crew", "tool": None})

        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def _(source, event):
            emit({"kind": "kickoff_end", "agent": "Crew", "tool": None})

        @crewai_event_bus.on(TaskStartedEvent)
        def _(source, event):
            emit(
                {
                    "kind": "task_start",
                    "agent": getattr(event, "agent_role", None) or "?",
                    "tool": None,
                    "output": _truncate(
                        getattr(event, "task_name", None)
                        or getattr(event, "task_id", None)
                    ),
                }
            )

        @crewai_event_bus.on(TaskCompletedEvent)
        def _(source, event):
            emit(
                {
                    "kind": "task_end",
                    "agent": getattr(event, "agent_role", None) or "?",
                    "tool": None,
                    "output": _truncate(getattr(event, "output", None)),
                }
            )

        @crewai_event_bus.on(AgentExecutionStartedEvent)
        def _(source, event):
            emit(
                {
                    "kind": "agent_start",
                    "agent": getattr(event, "agent_role", None) or "?",
                    "tool": None,
                    "output": _truncate(getattr(event, "task_prompt", None), 400),
                }
            )

        @crewai_event_bus.on(AgentExecutionCompletedEvent)
        def _(source, event):
            emit(
                {
                    "kind": "agent_end",
                    "agent": getattr(event, "agent_role", None) or "?",
                    "tool": None,
                    "output": _truncate(getattr(event, "output", None)),
                }
            )

        @crewai_event_bus.on(ToolUsageStartedEvent)
        def _(source, event):
            emit(
                {
                    "kind": "tool_start",
                    "agent": getattr(event, "agent_role", None) or "?",
                    "tool": getattr(event, "tool_name", None),
                    "args": _truncate(getattr(event, "tool_args", None)),
                }
            )

        @crewai_event_bus.on(ToolUsageFinishedEvent)
        def _(source, event):
            emit(
                {
                    "kind": "tool_end",
                    "agent": getattr(event, "agent_role", None) or "?",
                    "tool": getattr(event, "tool_name", None),
                    "output": _truncate(getattr(event, "output", None)),
                }
            )

    def worker() -> None:
        try:
            with crewai_event_bus.scoped_handlers():
                _register_handlers()
                crew = _build_crew(user_message, history)
                result = crew.kickoff()
                reply = getattr(result, "raw", None) or str(result)
                emit({"kind": "result", "reply": reply})
        except Exception as e:  # noqa: BLE001
            emit({"kind": "error", "message": str(e), "type": type(e).__name__})
        finally:
            q.put(_DONE)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    while True:
        item = q.get()
        if item is _DONE:
            break
        yield item

    t.join(timeout=1.0)
