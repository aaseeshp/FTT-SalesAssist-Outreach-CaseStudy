"""Offline checks of the Claude -> CrewAI adapter (no network: the SDK client is stubbed)."""
from types import SimpleNamespace

import pytest

from app.services.llm import ClaudeCrewLLM, RefusalError


class StubMessages:
    def __init__(self, stop_reason="end_turn", text="Thought: done\nFinal Answer: {}"):
        self.kwargs = None
        self.stop_reason, self.text = stop_reason, text

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=self.text)])


def make(stub):
    llm = ClaudeCrewLLM(model="claude-sonnet-5-5", stop=["\nObservation:"])
    llm._client = SimpleNamespace(messages=stub)
    return llm


def test_messages_mapped_to_messages_api():
    stub = StubMessages()
    out = make(stub).call([
        {"role": "system", "content": "You are the Intent Analyst."},
        {"role": "user", "content": "Classify A101"},
        {"role": "assistant", "content": "Thought: I should call a tool"},
    ])
    k = stub.kwargs
    assert out.startswith("Thought")
    assert k["system"] == "You are the Intent Analyst."
    assert k["model"] == "claude-sonnet-5-5"
    assert k["stop_sequences"] == ["\nObservation:"]          # ReAct loop stop word
    assert k["output_config"] == {"effort": "low"}
    assert k["messages"][0]["role"] == "user"
    assert k["messages"][-1]["role"] == "user"                 # never ends on an assistant prefill
    assert "temperature" not in k                              # sampling params are rejected on 5.5 models


def test_refusal_raises_so_chain_can_fall_back():
    with pytest.raises(RefusalError):
        make(StubMessages(stop_reason="refusal")).call("hi")
