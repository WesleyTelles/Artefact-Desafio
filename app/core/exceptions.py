"""Exceções do projeto, com hierarquia simples."""


class AppError(Exception):
    """Erro base da aplicação."""


class DataError(AppError):
    """Falha ao carregar ou validar os dados (CSV ausente, corrompido, inconsistente)."""


class ToolInputError(AppError):
    """Argumento inválido recebido por uma ferramenta."""
