"""
BaseTenantModel

Classe base para todos os models que pertencem a um tenant.
Garante que tenant_id esteja presente e indexado em toda entidade de negócio.

Uso:
    class Ticket(BaseTenantModel):
        __tablename__ = "tickets"
        # tenant_id já está aqui, não precisa redeclarar
        title = Column(String, nullable=False)

Benefícios:
  - Impossível criar um model sem tenant_id
  - Index automático em tenant_id para performance
  - Facilita aplicação de RLS no PostgreSQL
  - Auditoria de created_at / updated_at em todas as tabelas
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, func
from sqlalchemy.orm import declared_attr

from src.models.database import Base


class TimestampMixin:
    """Adiciona created_at e updated_at em qualquer model."""

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )


class BaseTenantModel(Base, TimestampMixin):
    """
    Base para todos os models com escopo de tenant.

    Inclui:
      - id (PK automático)
      - tenant_id (FK obrigatória, indexada)
      - created_at / updated_at
    """

    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)

    @declared_attr
    def __table_args__(cls):
        from sqlalchemy import Index
        # Index composto tenant_id + id para queries filtradas por tenant
        return (
            Index(f"ix_{cls.__tablename__}_tenant_id", "tenant_id"),
        )


class RLSMigrationHelper:
    """
    Helper para gerar os comandos SQL de RLS.
    Executar uma vez na migration após criar as tabelas.

    Uso:
        from src.models.base_tenant import RLSMigrationHelper
        sql = RLSMigrationHelper.generate_rls_sql(["tickets", "conversations", "customers"])
        # Executar no banco
    """

    @staticmethod
    def generate_rls_sql(tables: list[str]) -> str:
        """Gera SQL para habilitar RLS nas tabelas listadas."""
        lines = []
        for table in tables:
            lines.append(f"-- RLS para tabela: {table}")
            lines.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            lines.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            lines.append(
                f"CREATE POLICY tenant_isolation_{table} ON {table}"
                f"  USING (tenant_id = current_setting('app.current_tenant')::integer)"
                f"  WITH CHECK (tenant_id = current_setting('app.current_tenant')::integer);"
            )
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def print_rls_sql(tables: list[str]):
        print(RLSMigrationHelper.generate_rls_sql(tables))
