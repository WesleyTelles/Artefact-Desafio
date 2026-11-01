"""Cenários com LLM real. Rode: pytest -m live (precisa de LLM_API_KEY; sem ela, tudo é pulado).

Cada teste espaça as chamadas (cota gratuita) e vira skip, não falha, se o provedor devolver 429.
"""
import os
import time

import pytest

from app.core.config import load_env_file, load_llm_settings
from app.llm.factory import create_client
from tests.live.harness import evaluate, run_scenario
from tests.live.scenarios import SCENARIOS

load_env_file()
pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not os.environ.get("LLM_API_KEY"), reason="LLM_API_KEY não definida")]
PAUSE_SECONDS = float(os.environ.get("LIVE_PAUSE_SECONDS", "4"))


@pytest.fixture(scope="module")
def llm():
    return create_client(load_llm_settings())


@pytest.fixture(autouse=True)
def _throttle():
    yield
    time.sleep(PAUSE_SECONDS)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_cenario(scenario, llm):
    run = run_scenario(scenario, llm)
    if run.rate_limited:
        pytest.skip("provedor devolveu 429 (rate_limit): resultado inconclusivo")
    assert evaluate(scenario, run) == []
