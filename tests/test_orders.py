import json

from app.tools.orders import get_order_status, mask_email, mask_phone


def _email_do_pedido(store, oid):
    return store.customers[store.orders[oid].customer_id].email


def test_pedido_com_verificacao_por_email(store):
    r = get_order_status(1, "Pedro.Oliveira@JMAIL.com ", store=store)
    assert r["status"] == "found"
    assert r["order_status_label"] == "Entregue" and r["payment_method_label"] == "PIX"
    assert r["total_brl"] == "11499.00"
    assert r["tracking_code"] == "BRAB1234567BR" and r["estimated_delivery"] == "2025-10-25"
    assert r["items"][0]["name"] and r["items"][0]["quantity"] == 1


def test_pedido_com_verificacao_por_telefone_normalizado(store):
    r = get_order_status("#2", "+55 67 98321 6543", store=store)
    assert r["status"] == "found" and r["payment_method_label"] == "Cartão de crédito 6x"


def test_total_registrado_nao_e_recalculado(store):
    r = get_order_status(3, "isabela.moreira@jmail.com", store=store)
    assert r["total_brl"] == "3450.00"  # soma dos itens daria 3498
    assert r["items"][0]["quantity"] == 2


def test_pedido_cancelado_traz_notes(store):
    r = get_order_status(17, _email_do_pedido(store, 17), store=store)
    assert r["order_status_label"] == "Cancelado" and r["notes"]
    assert "tracking_code" not in r and "estimated_delivery" not in r


def test_verificacao_errada(store):
    r = get_order_status(1, "outra.pessoa@jmail.com", store=store)
    assert r["status"] == "verification_failed"
    assert "tracking_code" not in r and "items" not in r


def test_verificacao_com_dados_de_outro_cliente(store):
    outro = store.customers[1].email
    assert get_order_status(1, outro, store=store)["status"] == "verification_failed"


def test_pedido_inexistente_indistinguivel_de_verificacao_errada(store):
    inexistente = get_order_status(99999, "pedro.oliveira@jmail.com", store=store)
    errada = get_order_status(1, "nao.e.ele@jmail.com", store=store)
    assert inexistente == errada
    assert inexistente["status"] == "verification_failed"


def test_sem_verificacao_nao_revela_nada(store):
    r = get_order_status(1, None, store=store)
    assert r["status"] == "verification_required" and "items" not in r
    assert get_order_status(1, "   ", store=store)["status"] == "verification_required"


def test_telefone_parcial_nao_serve(store):
    assert get_order_status(1, "1098", store=store)["status"] == "verification_failed"


def test_pii_mascarada(store):
    r = get_order_status(1, "pedro.oliveira@jmail.com", store=store)
    texto = json.dumps(r, ensure_ascii=False)
    c = store.customers[store.orders[1].customer_id]
    assert c.email not in texto and c.phone not in texto and c.name not in texto
    assert "98432-1098" not in texto
    assert r["contact_on_file"]["email"] == "p***@jmail.com"
    assert r["contact_on_file"]["phone"] == "(67) *****-1098"


def test_mascaras():
    assert mask_email("a@b.com") == "a***@b.com"
    assert mask_phone("(67) 3341-4444") == "(67) *****-4444"


def test_pedido_entregue_nao_afirma_data_de_entrega_efetiva():
    from app.data.loader import get_store
    order_customer = get_store().customers[get_store().orders[4].customer_id]
    r = get_order_status(4, order_customer.email)
    assert r["status"] == "found"
    assert "previsão" in r["delivery_date_note"]
