# Lojinha.com — Sistema de Loja de Conveniência

Aplicação web acadêmica desenvolvida com Python e Django, conforme os requisitos do Trabalho Prático 03.

## Funcionalidades

- Página inicial com resumo de produtos, categorias e itens com estoque baixo.
- CRUD de categorias: cadastrar, listar, editar e excluir quando não houver produtos vinculados.
- Cadastro e edição de produtos com custo opcional, estoque mínimo individual e código de barras único.
- Arquivamento de produtos para preservar o histórico, em vez de exclusão definitiva.
- Busca e paginação na lista de produtos.
- Filtro por categoria e ordenação de produtos.
- Controle de estoque com entradas, perdas, saídas manuais e ajustes autorizados.
- Histórico de movimentações com saldo anterior/posterior, motivo e responsável.
- PDV com busca por nome/código de barras, carrinho editável e revisão do preço atual antes da confirmação.
- Registro de vendas e pagamentos em dinheiro, Pix ou cartão; cálculo de troco para dinheiro.
- Cancelamento integral com justificativa e estorno de estoque, preservando a venda no histórico.
- Detalhes e comprovante simplificado para impressão.
- Relatórios com faturamento diário, semanal ou mensal, comparação entre períodos, produtos mais/menos vendidos, estoque baixo e movimentações.
- Exportação PDF dos dados do período selecionado.
- Grupos `Atendente` e `Gerente`, com autorização verificada no backend.
- Acesso ao painel restrito a usuários autenticados em um desses grupos ou superusuários.
- Relacionamento `ForeignKey`: cada produto pertence a uma categoria.
- Formulários HTML renderizados pelo Django Templates.
- Mensagens de feedback após as operações.
- Inicializador da loja configurado para PostgreSQL; Django usa SQLite quando executado sem configuração explícita.
- Backup manual do banco configurado, com verificação de integridade para SQLite.
- Interface responsiva em português.

## Requisitos

- Python 3.10 ou superior.
- Conexão com a internet na primeira configuração para instalar as dependências.
- Dependências listadas em `requirements.txt` (Django, ReportLab e driver PostgreSQL).

## Executar no Windows (VS Code)

1. Extraia o ZIP em uma pasta, por exemplo `Documentos\Lojinha.com`.
2. Abra essa pasta no VS Code.
3. Abra **Terminal > Novo Terminal**.
4. Execute:

   ```powershell
   .\iniciar_windows.bat
   ```

5. Configure o PostgreSQL, crie o banco e o usuário da aplicação com as permissões necessárias. Para aplicar as migrações em um banco novo ou após uma atualização, execute o comando abaixo e informe a senha do administrador PostgreSQL:

   ```powershell
   .\.venv\Scripts\python.exe gerenciar_postgresql.py migrar
   ```

6. Em uma instalação nova, crie o primeiro usuário Django autorizado:

   ```powershell
   .\.venv\Scripts\python.exe gerenciar_postgresql.py criar-superusuario
   ```

   Para criar usuários de operação, acesse `/admin` com o superusuário e atribua o grupo `Atendente` ou `Gerente` a cada conta. O superusuário já tem acesso total ao painel.

7. Inicie o site:

   ```powershell
   .\iniciar_site.bat
   ```

8. Digite a senha do usuário PostgreSQL da aplicação quando solicitada, abra http://127.0.0.1:8000/ e entre com sua conta Django.

### Alternativa usando o terminal com PostgreSQL

```powershell
.\.venv\Scripts\python.exe gerenciar_postgresql.py iniciar
```

Comandos `manage.py` executados diretamente sem as variáveis de PostgreSQL usam SQLite. Após a migração, não use esse SQLite antigo para operar a loja: ele não é sincronizado com o PostgreSQL.

## Backup manual do SQLite

Execute na pasta do projeto:

```powershell
.\.venv\Scripts\python.exe manage.py backup_loja
```

O comando cria uma cópia consistente do banco, mesmo com a loja aberta, verifica sua integridade e informa o caminho em `backups`. A pasta é ignorada pelo Git, mas contém dados sensíveis: proteja o acesso e mantenha outra cópia em local seguro. Use `--destino "C:\caminho\da\pasta"` para escolher outra pasta. Para restaurar, pare a loja, preserve o banco atual e teste a cópia em um ambiente separado antes de substituir qualquer arquivo.

## Backup manual do PostgreSQL

Após configurar e migrar o PostgreSQL, execute `backup_postgresql.bat` e digite a senha do usuário da aplicação quando solicitada. O backup é salvo em `backups` no formato compactado do `pg_dump`; não substitui arquivos existentes. O PostgreSQL 17 instalado no caminho padrão é detectado pelo arquivo `.bat`. Para outras instalações, coloque `pg_dump` no PATH ou defina `LOJINHA_PG_DUMP` com o caminho completo do executável.

Um backup não garante, por si só, uma restauração bem-sucedida. Teste periodicamente a restauração com `pg_restore --exit-on-error --no-owner --no-acl` em um banco novo e separado. Proteja os arquivos e mantenha outra cópia em local seguro.

## Preparação para PostgreSQL

O Django usa SQLite quando não recebe configuração explícita; os inicializadores PostgreSQL selecionam `LOJINHA_DB_ENGINE=postgresql`. As variáveis `LOJINHA_DB_NAME`, `LOJINHA_DB_USER`, `LOJINHA_DB_PASSWORD`, `LOJINHA_DB_HOST` e `LOJINHA_DB_PORT` permitem configurar a conexão. Não salve senhas no código nem em arquivos versionados.

**A configuração não migra dados automaticamente.** Antes de mudar o banco da loja, instale e configure o PostgreSQL, crie e valide um banco de destino separado, faça um backup, transfira e confira os dados e teste venda, cancelamento e concorrência. Não habilite múltiplos caixas enquanto essas etapas não forem concluídas.

`iniciar_site.bat` chama `iniciar_postgresql.bat`. A senha fica no ambiente do processo enquanto ele estiver em execução. O inicializador usa, por padrão, o banco `lojinha_postgres` e o usuário `lojinha_app`; eles podem ser alterados com as variáveis acima. Para `migrar`, o usuário padrão é `postgres`. Se houver migrações pendentes, aplique-as com um usuário administrador antes de iniciar. O SQLite preservado é uma cópia anterior e não é atualizado pelo PostgreSQL.

## Configuração para produção

O modo local usa `DEBUG=True` e uma chave de desenvolvimento. Antes de publicar, configure variáveis de ambiente no servidor:

- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY`: chave aleatória e privada; gere uma com `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`.
- `DJANGO_ALLOWED_HOSTS`: nomes de host separados por vírgula, sem esquema, por exemplo `loja.exemplo.com`.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: origens HTTPS separadas por vírgula, por exemplo `https://loja.exemplo.com`.

Com `DEBUG` desligado, o Django exige a chave e os hosts e ativa redirecionamento HTTPS, cookies seguros e HSTS. A hospedagem deve estar configurada para HTTPS antes de ativar esse modo. O banco SQLite padrão é adequado para uso local e acadêmico; avalie um banco gerenciado para produção.

Para disponibilizar os arquivos estáticos em produção, execute `python manage.py collectstatic` e configure o servidor para servir o conteúdo da pasta `staticfiles` no endereço `/static/`. O Django não serve esses arquivos automaticamente com `DEBUG=False`.

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
│   ├── relatorios.py
│   ├── relatorio_pdf.py
│   ├── services.py
│   ├── vendas.py
│   └── admin.py
├── manage.py
├── requirements.txt
├── iniciar_windows.bat
└── iniciar_site.bat
```

## Modelos e relacionamento

- `Categoria`: nome e descrição.
- `Produto`: nome, descrição, preço, custo opcional, saldo, estoque mínimo, código de barras, situação no catálogo, categoria e data de cadastro.
- `MovimentacaoEstoque`: registra variações de saldo, saldos anterior/posterior, tipo, motivo e responsável.
- `Produto.categoria` usa `ForeignKey` para ligar cada produto a uma categoria.
- A migração cria os grupos `Atendente` e `Gerente` e registra o saldo existente como saldo inicial, sem inventar movimentos anteriores.

## Escopo em andamento

O catálogo, o controle auditável de estoque, o PDV, as vendas, os pagamentos, os cancelamentos, os relatórios e a exportação PDF estão implementados. Os relatórios permitem selecionar até 365 dias, exibem na tela as 30 movimentações mais recentes e incluem todas as movimentações do período no PDF.

## Observações acadêmicas

O Django Admin está disponível apenas como ferramenta auxiliar. O CRUD principal é realizado nas páginas HTML do próprio sistema, conforme solicitado no enunciado. Antes da entrega, a equipe deve executar e testar o projeto no próprio computador, revisar o código e estar preparada para explicar os modelos, o `ForeignKey`, as views, as URLs, os templates e as operações CRUD.
