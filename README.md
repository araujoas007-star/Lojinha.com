# Lojinha.com — Sistema de Loja de Conveniência

Aplicação web acadêmica desenvolvida com Python e Django, conforme os requisitos do Trabalho Prático 03.

## Funcionalidades

- Página inicial com resumo de produtos, categorias e itens com estoque baixo.
- CRUD de categorias: cadastrar, listar, editar e excluir.
- CRUD de produtos: cadastrar, listar, editar e excluir.
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

5. Quando terminar, execute:

   ```powershell
   .\iniciar_site.bat
   ```

6. Abra no navegador: http://127.0.0.1:8000/

### Alternativa usando o terminal

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py makemigrations loja
python manage.py migrate
python manage.py runserver
```

Se o PowerShell bloquear a ativação do ambiente virtual, use os arquivos `.bat` incluídos ou execute os comandos no Prompt de Comando.

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
