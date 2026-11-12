# Lojinha.com — Sistema de Loja de Conveniência

Aplicação web acadêmica desenvolvida com Python e Django, conforme os requisitos do Trabalho Prático 03.

## Funcionalidades

- Página inicial com resumo de produtos, categorias e itens com estoque baixo.
- CRUD de categorias: cadastrar, listar, editar e excluir.
- CRUD de produtos: cadastrar, listar, editar e excluir.
- Busca e paginação na lista de produtos.
- Filtro por categoria e ordenação de produtos.
- Acesso ao painel restrito a usuários autenticados com permissão de equipe.
- Relacionamento `ForeignKey`: cada produto pertence a uma categoria.
- Formulários HTML renderizados pelo Django Templates.
- Mensagens de feedback após as operações.
- Banco de dados SQLite, configurado por padrão no Django.
- Interface responsiva em português.

## Requisitos

- Python 3.10 ou superior.
- Conexão com a internet na primeira configuração para instalar Django.

## Executar no Windows (VS Code)

1. Extraia o ZIP em uma pasta, por exemplo `Documentos\Lojinha.com`.
2. Abra essa pasta no VS Code.
3. Abra **Terminal > Novo Terminal**.
4. Execute:

   ```powershell
   .\iniciar_windows.bat
   ```

5. Crie o primeiro usuário autorizado:

   ```powershell
   .\.venv\Scripts\python.exe manage.py createsuperuser
   ```

6. Inicie o site:

   ```powershell
   .\iniciar_site.bat
   ```

7. Abra no navegador: http://127.0.0.1:8000/ e entre com essa conta.

### Alternativa usando o terminal

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Se o PowerShell bloquear a ativação do ambiente virtual, use os arquivos `.bat` incluídos ou execute os comandos no Prompt de Comando.

## Configuração para produção

O modo local usa `DEBUG=True` e uma chave de desenvolvimento. Antes de publicar, configure variáveis de ambiente no servidor:

- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY`: chave aleatória e privada; gere uma com `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`.
- `DJANGO_ALLOWED_HOSTS`: nomes de host separados por vírgula, sem esquema, por exemplo `loja.exemplo.com`.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: origens HTTPS separadas por vírgula, por exemplo `https://loja.exemplo.com`.

Com `DEBUG` desligado, o Django exige a chave e os hosts e ativa redirecionamento HTTPS, cookies seguros e HSTS. A hospedagem deve estar configurada para HTTPS antes de ativar esse modo. O banco SQLite padrão é adequado para uso local e acadêmico; avalie um banco gerenciado para produção.

## Estrutura principal

```text
Lojinha.com/
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── loja/
│   ├── migrations/
│   ├── templates/loja/
│   ├── static/loja/css/
│   ├── models.py
│   ├── forms.py
│   ├── views.py
│   ├── urls.py
│   └── admin.py
├── manage.py
├── requirements.txt
├── iniciar_windows.bat
└── iniciar_site.bat
```

## Modelos e relacionamento

- `Categoria`: nome e descrição.
- `Produto`: nome, descrição, preço, quantidade em estoque, categoria e data de cadastro.
- `Produto.categoria` usa `ForeignKey` para ligar cada produto a uma categoria.

## Observações acadêmicas

O Django Admin está disponível apenas como ferramenta auxiliar. O CRUD principal é realizado nas páginas HTML do próprio sistema, conforme solicitado no enunciado. Antes da entrega, a equipe deve executar e testar o projeto no próprio computador, revisar o código e estar preparada para explicar os modelos, o `ForeignKey`, as views, as URLs, os templates e as operações CRUD.
