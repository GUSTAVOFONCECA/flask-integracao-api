# app/cli/sync_commands.py
import click
from flask.cli import AppGroup

from app.cli.logging_setup import setup_sync_logger
from app.services.sync.conta_azul_sync_manager import (
    PersonsSyncManager,
    AccountsSyncManager,
    ServicesSyncManager,
)
from app.services.sync.digisac_sync_manager import (
    ContactsSyncManager,
    DepartmentsSyncManager,
    UsersSyncManager,
)

sync_cli = AppGroup("sync")
sync_logger = setup_sync_logger()


@sync_cli.command("ca-pessoas")
@click.option("--page-size", default=10)
def ca_pessoas(page_size):
    sync_logger.info("🔄 [CA] Pessoas")
    PersonsSyncManager(page_size).run_sync()


@sync_cli.command("ca-contas")
@click.option("--page-size", default=10)
def ca_contas(page_size):
    sync_logger.info("🔄 [CA] Contas Financeiras")
    AccountsSyncManager(page_size).run_sync()


@sync_cli.command("ca-servicos")
@click.option("--page-size", default=10)
def ca_servicos(page_size):
    sync_logger.info("🔄 [CA] Serviços")
    ServicesSyncManager(page_size).run_sync()


@sync_cli.command("digisac-contatos")
@click.option("--page-size", default=40)
def dc_contatos(page_size):
    sync_logger.info("🔄 [DS] Contatos")
    ContactsSyncManager(page_size).run_sync()


@sync_cli.command("digisac-departamentos")
@click.option("--page-size", default=40)
def dc_departamentos(page_size):
    sync_logger.info("🔄 [DS] Departamentos")
    DepartmentsSyncManager(page_size).run_sync()


@sync_cli.command("digisac-usuarios")
@click.option("--page-size", default=40)
def dc_usuarios(page_size):
    sync_logger.info("🔄 [DS] Usuários")
    UsersSyncManager(page_size).run_sync()


@sync_cli.command("all")
@click.option("--ca-page-size", default=10)
@click.option("--ds-page-size", default=40)
def sync_all(ca_page_size, ds_page_size):
    sync_logger.info("🚀 Iniciando sync ALL")

    sync_logger.info("[CA] Pessoas")
    PersonsSyncManager(ca_page_size).run_sync()

    sync_logger.info("[CA] Contas")
    AccountsSyncManager(ca_page_size).run_sync()

    sync_logger.info("[CA] Serviços")
    ServicesSyncManager(ca_page_size).run_sync()

    sync_logger.info("[DS] Contatos")
    ContactsSyncManager(ds_page_size).run_sync()

    sync_logger.info("[DS] Departamentos")
    DepartmentsSyncManager(ds_page_size).run_sync()

    sync_logger.info("[DS] Usuários")
    UsersSyncManager(ds_page_size).run_sync()

    sync_logger.info("✅ Sync ALL concluído")
