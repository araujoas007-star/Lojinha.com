import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from .management.commands.backup_loja import backup_postgresql, backup_sqlite


class BackupSqliteTests(SimpleTestCase):
    def test_backup_copies_live_database_and_can_be_read(self):
        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "origem.sqlite3"
            destino = Path(pasta) / "backup.sqlite3"
            with closing(sqlite3.connect(origem)) as banco:
                banco.execute("CREATE TABLE produtos (nome TEXT, quantidade INTEGER)")
                banco.execute("INSERT INTO produtos VALUES (?, ?)", ("Produto", 7))
                banco.commit()
                backup_sqlite(origem, destino)

            with closing(sqlite3.connect(destino)) as copia:
                self.assertEqual(copia.execute("PRAGMA integrity_check").fetchone(), ("ok",))
                self.assertEqual(
                    copia.execute("SELECT nome, quantidade FROM produtos").fetchall(),
                    [("Produto", 7)],
                )

    def test_backup_refuses_to_overwrite_and_missing_source(self):
        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "origem.sqlite3"
            destino = Path(pasta) / "backup.sqlite3"
            with closing(sqlite3.connect(origem)):
                pass
            destino.write_bytes(b"backup existente")
            with self.assertRaises(FileExistsError):
                backup_sqlite(origem, destino)
            self.assertEqual(destino.read_bytes(), b"backup existente")
            with self.assertRaises(FileNotFoundError):
                backup_sqlite(Path(pasta) / "ausente.sqlite3", Path(pasta) / "novo.sqlite3")
            self.assertFalse((Path(pasta) / "novo.sqlite3").exists())


class BackupPostgresqlTests(SimpleTestCase):
    def setUp(self):
        self.configuracao = {
            "NAME": "loja", "USER": "aplicacao", "PASSWORD": "senha-de-teste",
            "HOST": "localhost", "PORT": "5432",
        }

    @patch("loja.management.commands.backup_loja.subprocess.run")
    def test_backup_uses_password_in_environment_and_preserves_existing_file(self, executar):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "backup.dump"
            backup_postgresql(self.configuracao, destino)
            argumentos, opcoes = executar.call_args
            self.assertNotIn(self.configuracao["PASSWORD"], argumentos[0])
            self.assertEqual(opcoes["env"]["PGPASSWORD"], self.configuracao["PASSWORD"])
            destino.write_bytes(b"backup existente")
            with self.assertRaises(FileExistsError):
                backup_postgresql(self.configuracao, destino)
            self.assertEqual(destino.read_bytes(), b"backup existente")

    @patch("loja.management.commands.backup_loja.subprocess.run")
    def test_failed_dump_removes_incomplete_file(self, executar):
        executar.side_effect = subprocess.CalledProcessError(1, ["pg_dump"], stderr=b"erro")
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "backup.dump"
            with self.assertRaises(subprocess.CalledProcessError):
                backup_postgresql(self.configuracao, destino)
            self.assertFalse(destino.exists())


class ConfiguracaoPostgresTests(SimpleTestCase):
    def executar_settings(self, variaveis):
        ambiente = os.environ.copy()
        for nome in ("LOJINHA_DB_ENGINE", "LOJINHA_DB_NAME", "LOJINHA_DB_USER"):
            ambiente.pop(nome, None)
        ambiente.update(variaveis)
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "from config.settings import DATABASES; print(DATABASES['default']['ENGINE'])",
            ],
            env=ambiente,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_postgres_requires_database_and_user(self):
        resultado = self.executar_settings({"LOJINHA_DB_ENGINE": "postgresql"})
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("Defina LOJINHA_DB_NAME e LOJINHA_DB_USER", resultado.stderr)

    def test_postgres_selection_is_explicit(self):
        resultado = self.executar_settings({
            "LOJINHA_DB_ENGINE": "postgresql",
            "LOJINHA_DB_NAME": "lojinha_teste",
            "LOJINHA_DB_USER": "lojinha",
        })
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("django.db.backends.postgresql", resultado.stdout)
