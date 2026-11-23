import os
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


def backup_sqlite(origem, destino):
    origem = Path(origem).resolve()
    destino = Path(destino).resolve()
    if origem == destino:
        raise ValueError("O arquivo de backup não pode ser o banco original.")
    if not origem.is_file():
        raise FileNotFoundError(f"Banco de dados não encontrado: {origem}")

    with destino.open("xb"):
        pass
    concluido = False
    try:
        with closing(sqlite3.connect(f"{origem.as_uri()}?mode=ro", uri=True)) as fonte:
            with closing(sqlite3.connect(destino)) as copia:
                fonte.backup(copia)
                resultado = copia.execute("PRAGMA integrity_check").fetchall()
                if resultado != [("ok",)]:
                    raise ValueError(f"Falha na verificação de integridade: {resultado}")
        concluido = True
    finally:
        if not concluido:
            destino.unlink()


def backup_postgresql(configuracao, destino):
    ambiente = os.environ.copy()
    ambiente.pop("PGPASSWORD", None)
    if configuracao["PASSWORD"]:
        ambiente["PGPASSWORD"] = configuracao["PASSWORD"]
    comando = [
        os.environ.get("LOJINHA_PG_DUMP", "pg_dump"),
        "--no-password",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--host", str(configuracao["HOST"]),
        "--port", str(configuracao["PORT"]),
        "--username", configuracao["USER"],
        "--dbname", configuracao["NAME"],
    ]
    with destino.open("xb") as arquivo:
        concluido = False
        try:
            subprocess.run(
                comando, stdout=arquivo, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, env=ambiente, check=True,
            )
            concluido = True
        finally:
            if not concluido:
                arquivo.close()
                destino.unlink()


class Command(BaseCommand):
    help = "Cria um backup manual do banco configurado, mesmo com a loja aberta."

    def add_arguments(self, parser):
        parser.add_argument(
            "--destino",
            type=Path,
            help="Pasta para salvar o backup (padrão: backups dentro do projeto).",
        )

    def handle(self, *args, **options):
        banco = connections["default"]
        if banco.vendor not in {"sqlite", "postgresql"}:
            raise CommandError(
                f"Backup não disponível para o banco {banco.vendor}."
            )
        pasta = options["destino"] or settings.BASE_DIR / "backups"
        pasta = pasta.expanduser().resolve()
        extensao = "sqlite3" if banco.vendor == "sqlite" else "dump"
        nome = f"lojinha_{datetime.now():%Y%m%d_%H%M%S_%f}.{extensao}"
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            destino = pasta / nome
            if banco.vendor == "sqlite":
                backup_sqlite(banco.settings_dict["NAME"], destino)
            else:
                backup_postgresql(banco.settings_dict, destino)
        except subprocess.CalledProcessError as error:
            detalhe = error.stderr.decode(errors="replace").strip()
            raise CommandError(f"Falha no pg_dump: {detalhe}") from error
        except (OSError, sqlite3.Error, ValueError) as error:
            raise CommandError(f"Não foi possível criar o backup: {error}") from error
        if banco.vendor == "sqlite":
            mensagem = "Backup criado e verificado"
        else:
            mensagem = "Backup criado; teste a restauração em um banco separado"
        self.stdout.write(self.style.SUCCESS(f"{mensagem}: {destino}"))
