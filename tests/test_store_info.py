from app.tools.store_info import get_store_info


def test_endereco_e_horario():
    info = get_store_info()["info"]
    assert "Rua 14 de Maio, 3200" in info["address"]["value"]
    assert info["hours"]["value"]["sabado"] == "09:00 às 13:00"
    assert info["hours"]["value"]["domingo_e_feriados"] == "Fechado"


def test_contatos_com_divergencia_sinalizada():
    c = get_store_info("contacts")["info"]["contacts"]
    assert c["phone"]["value"] == "(67) 3341-4444" and c["phone"]["to_confirm"]
    assert c["whatsapp"]["value"] == "(67) 3321-4500" and c["whatsapp"]["to_confirm"]
    assert "diverge" in c["divergence_note"]


def test_toda_informacao_tem_fonte():
    info = get_store_info()["info"]
    for key in ("address", "hours", "scope"):
        assert "§" in info[key]["source"] and "p." in info[key]["source"]
    for key in ("phone", "whatsapp", "email"):
        assert "p." in info["contacts"][key]["source"]


def test_escopo_so_instrumentos():
    assert "Somente instrumentos" in get_store_info("scope")["info"]["scope"]["value"]
