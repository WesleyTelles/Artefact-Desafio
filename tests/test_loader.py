import shutil
from pathlib import Path

import pytest

from app.core.config import PROJECT_ROOT
from app.core.exceptions import DataError
from app.data.loader import load_data

SRC = PROJECT_ROOT / "data"


@pytest.fixture
def data_copy(tmp_path):
    for f in SRC.glob("*.csv"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


def _csv(data_dir: Path, table: str) -> Path:
    return data_dir / f"desafio_tecnico_ai_eng - {table}.csv"


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_carga_real(store):
    assert len(store.products) == 65 and len(store.orders) == 20
    assert len(store.customers) == 50 and len(store.promotions) == 25
    assert sum(1 for p in store.promotions.values() if p.is_active) == 4


def test_csv_ausente(tmp_path):
    with pytest.raises(DataError, match="não encontrado"):
        load_data(tmp_path)


def test_csv_corrompido_numero_de_colunas(data_copy):
    path = _csv(data_copy, "products")
    path.write_text(path.read_text(encoding="utf-8") + "\n999,10,so,tres,colunas\n", encoding="utf-8")
    with pytest.raises(DataError, match="products"):
        load_data(data_copy)


def test_csv_com_preco_invalido(data_copy):
    _edit(_csv(data_copy, "products"), "599.9,Yamaha C40", "abc,Yamaha C40")
    with pytest.raises(DataError, match="price_brl"):
        load_data(data_copy)


def test_csv_sem_colunas_esperadas(data_copy):
    _csv(data_copy, "orders").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(DataError, match="colunas ausentes"):
        load_data(data_copy)


def test_bytes_invalidos(data_copy):
    _csv(data_copy, "customers").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(DataError):
        load_data(data_copy)


def test_pedido_com_cliente_inexistente(data_copy):
    _edit(_csv(data_copy, "orders"), "\n1,3,", "\n1,9999,")
    with pytest.raises(DataError, match="customer_id 9999"):
        load_data(data_copy)


def test_item_com_produto_inexistente(data_copy):
    path = _csv(data_copy, "order_items")
    path.write_text(path.read_text(encoding="utf-8") + "\n1,1,77777\n", encoding="utf-8")
    with pytest.raises(DataError, match="product_id 77777"):
        load_data(data_copy)


def test_status_desconhecido(data_copy):
    _edit(_csv(data_copy, "products"), ",coming_soon,", ",quebrado,")
    with pytest.raises(DataError, match="status"):
        load_data(data_copy)
