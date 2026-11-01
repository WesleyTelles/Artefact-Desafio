import re

import pytest

from app.core.exceptions import DataError
from app.data.normalize import compact
from app.knowledge.loader import PDF_PATH, TXT_PATH, build_chunks, load_manual, load_manual_from


def _txt_body() -> str:
    raw = TXT_PATH.read_text(encoding="utf-8")
    raw = re.sub(r"=== PAGE \d+ ===|Página \d+|Empório da Música Manual de Políticas e Procedimentos", " ", raw)
    return compact(raw)


def test_carrega_do_pdf_com_oito_paginas():
    manual = load_manual()
    assert manual.source == "pdf"
    assert len(manual.pages) == 8


def test_quantidade_e_ids_unicos():
    chunks = load_manual().chunks
    assert 25 <= len(chunks) <= 32
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_texto_de_cada_trecho_existe_no_texto_extraido():
    body = _txt_body()
    for chunk in load_manual().chunks:
        assert compact(chunk.text) in body, chunk.chunk_id


def test_trechos_cobrem_o_manual_sem_buracos():
    manual = load_manual()
    joined = compact("".join(c.text for c in manual.chunks))
    assert joined == compact("".join(manual.pages))


def test_secao_titulo_e_paginas():
    manual = load_manual()
    s41 = manual.get("s4.1")
    assert (s41.section, s41.page_start, s41.page_end) == ("4.1", 4, 4)
    assert "Arrependimento" in s41.title and "7 (sete) dias corridos" in s41.text
    assert (manual.get("s5.2").page_start, manual.get("s5.2").page_end) == (4, 5)
    assert manual.get("s3.1").page_start == 3 and manual.get("s8.1").page_start == 7


def test_pagina_inicial_contem_o_comeco_do_trecho():
    manual = load_manual()
    for chunk in manual.chunks:
        assert compact(chunk.text[:15]) in compact(manual.pages[chunk.page_start - 1]), chunk.chunk_id
        assert compact(chunk.text[-40:]) in compact(manual.pages[chunk.page_end - 1]), chunk.chunk_id


def test_metadados_de_aliases_e_inconsistencias():
    manual = load_manual()
    assert "devolver" in manual.get("s4.1").aliases and "arrependi" in manual.get("s4.1").aliases
    assert "I-9" in manual.get("s4.2").open_issues and "I-9" in manual.get("s8.1").open_issues
    assert "I-6" in manual.get("s5.1").open_issues
    assert {"I-3", "I-4", "I-7"} <= set(manual.get("s3.1").open_issues)
    assert manual.get("s7.1").audience == "internal_procedure"
    assert all(c.topics or c.chunk_id == "s1.1" for c in manual.chunks)


def test_fallback_para_o_texto_extraido(tmp_path):
    manual = load_manual_from(tmp_path / "inexistente.pdf", TXT_PATH)
    assert manual.source == "txt" and len(manual.chunks) == len(load_manual().chunks)
    assert manual.get("s2").text == load_manual().get("s2").text


def test_build_chunks_falha_se_secao_sumir():
    with pytest.raises(DataError):
        build_chunks(["texto sem estrutura"])


def test_pdf_original_existe():
    assert PDF_PATH.exists() and PDF_PATH.stat().st_size > 1000
