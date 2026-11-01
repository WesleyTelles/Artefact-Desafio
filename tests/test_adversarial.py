"""Tentativas de abuso sobre a camada determinística (sem LLM): enumeração e verificação."""
from app.data.loader import get_store
from app.tools.registry import execute


def test_enumerar_pedidos_1_a_20_com_email_chutado_nao_revela_nada():
    store = get_store()
    messages = set()
    for oid in range(1, len(store.orders) + 1):
        result = execute("get_order_status", {"order_id": oid, "verification": "chute@exemplo.com"})
        assert result["status"] == "verification_failed"
        messages.add(result["message"])
    assert len(messages) == 1  # mesma resposta para qualquer pedido, existente ou não
    inexistente = execute("get_order_status", {"order_id": 9999, "verification": "chute@exemplo.com"})
    assert inexistente["message"] in messages


def test_email_de_outro_cliente_nao_abre_pedido_alheio():
    store = get_store()
    order = store.orders[1]
    for customer in store.customers.values():
        if customer.customer_id == order.customer_id:
            continue
        result = execute("get_order_status", {"order_id": 1, "verification": customer.email})
        assert result["status"] == "verification_failed"


def test_verificacoes_degeneradas_nao_abrem_pedido():
    for ver in ("@", "a@b", "%", "1", "0000000000", "' OR 1=1 --", "*"):
        assert execute("get_order_status", {"order_id": 1, "verification": ver})["status"] != "found"
