import argparse
import getpass
import os


def main():
    parser = argparse.ArgumentParser(description="Gerencia a loja no PostgreSQL.")
    parser.add_argument("acao", choices=("iniciar", "backup", "migrar", "criar-superusuario"))
    parser.add_argument("--endereco", default="127.0.0.1:8000")
    args = parser.parse_args()

    os.environ["LOJINHA_DB_ENGINE"] = "postgresql"
    os.environ.setdefault("LOJINHA_DB_NAME", "lojinha_postgres")
    usuario_padrao = "postgres" if args.acao == "migrar" else "lojinha_app"
    os.environ.setdefault("LOJINHA_DB_USER", usuario_padrao)
    senha = getpass.getpass("Senha do usuário PostgreSQL da loja: ")
    if not senha:
        raise SystemExit("A senha não pode estar vazia.")
    os.environ["LOJINHA_DB_PASSWORD"] = senha
    del senha
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django
    from django.core.management import execute_from_command_line
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    django.setup()
    connection.ensure_connection()
    if args.acao == "iniciar":
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise SystemExit("Há migrações pendentes. Aplique-as com o usuário administrador antes de iniciar.")
        comando = ["manage.py", "runserver", args.endereco, "--noreload"]
    elif args.acao == "backup":
        comando = ["manage.py", "backup_loja"]
    elif args.acao == "migrar":
        comando = ["manage.py", "migrate"]
    else:
        comando = ["manage.py", "createsuperuser"]
    execute_from_command_line(comando)


if __name__ == "__main__":
    main()
