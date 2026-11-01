"""Testes com LLM real: só rodam com LLM_API_KEY (e provedor configurado). Use: pytest -m live"""
import os

import pytest

from app.agent.orchestrator import Agent
from app.core.config import load_env_file, load_llm_settings
from app.llm.factory import create_client

load_env_file()
pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not os.environ.get("LLM_API_KEY"), reason="LLM_API_KEY não definida")]


@pytest.fixture
def agent():
    return Agent(create_client(load_llm_settings()))


def test_live_preco_vem_da_ferramenta(agent):
    reply = agent.reply("Qual o preço do violão Takamine GD20?")
    assert "2.199" in reply.text or "2199" in reply.text


def test_live_fora_de_escopo_sem_ferramentas(agent):
    reply = agent.reply("Me explica como funciona a bolsa de valores?")
    assert reply.trace == []
