# Lojinha.com — Modelagem do banco de dados

**Status:** aprovada; módulos de estoque, PDV e relatórios implementados

**Objetivo:** especificar os dados e as regras de integridade para controle de estoque, PDV e relatórios.

Esta modelagem preserva os modelos atuais de categoria e produto e acrescenta vendas, itens, pagamentos e movimentações. Grupos, catálogo ampliado, movimentações, PDV, vendas, pagamentos, cancelamentos com estorno e relatórios com exportação PDF estão implementados.

## 1. Categoria

Modelo existente, responsável por organizar os produtos.

| Campo | Descrição |
|---|---|
| `id` | Chave primária. |
| `nome` | Nome único da categoria. |
| `descricao` | Descrição opcional. |

Uma categoria pode ter vários produtos. Um produto pertence a uma categoria. A exclusão de categoria com produtos permanece protegida.

## 2. Produto

Modelo existente, ampliado para catálogo e saldo corrente do estoque. Os campos desta seção estão implementados; as regras de venda serão aplicadas quando o PDV for criado.

| Campo | Descrição |
|---|---|
| `id` | Chave primária. |
| `nome` | Nome do produto. |
| `descricao` | Descrição opcional. |
| `preco` | Preço atual de venda, em decimal. |
| `custo_aquisicao` | Custo atual de aquisição, em decimal e anulável até conferência. |
| `quantidade` | Saldo atual, inteiro e nunca negativo. |
| `estoque_minimo` | Limite mínimo individual, inteiro e não negativo; inicia em 5 para preservar o alerta atual. |
| `codigo_barras` | Opcional; único quando informado. |
| `ativo` | Indica se o produto está disponível para novas vendas. |
| `categoria_id` | Referência protegida à categoria. |
| `criado_em` | Data e hora do cadastro; preserva o campo existente. |

Quando um produto sair do catálogo, ele será arquivado (`ativo = false`), não apagado. Produtos arquivados não podem ser incluídos em novas vendas, mas continuam visíveis no histórico. Produtos que já tenham vendas ou movimentações não podem ser excluídos definitivamente. O campo `quantidade` só pode ser alterado por operações que também registrem uma movimentação. Os custos existentes ficam vazios até serem conferidos; não se presume custo zero.

## 3. Venda

Cada registro representa uma venda finalizada. O carrinho fica na sessão até a confirmação. O modelo e o serviço de finalização estão implementados.

| Campo | Descrição |
|---|---|
| `id` | Chave primária. |
| `data_venda` | Data e hora da finalização. |
| `usuario_id` | Usuário que realizou a venda; vínculo com o usuário Django. |
| `usuario_nome` | Cópia do nome de exibição para preservar o histórico. |
| `status` | `finalizada` ou `cancelada`. |
| `subtotal` | Soma dos itens antes do desconto. |
| `desconto` | Valor do desconto; zero quando não aplicado. |
| `total` | `subtotal - desconto`. |
| `gerente_autorizador_id` | Gerente que autorizou o desconto, nulo quando não houve. |
| `gerente_autorizador_nome` | Cópia do nome do autorizador, quando aplicável. |
| `data_cancelamento` | Data e hora do cancelamento, quando houver. |
| `usuario_cancelamento_id` | Usuário que cancelou, quando houver. |
| `usuario_cancelamento_nome` | Cópia do nome de quem cancelou. |
| `motivo_cancelamento` | Justificativa obrigatória para cancelamento. |

O desconto é permitido somente ao Gerente e não pode exceder 10% do subtotal. O Gerente deve estar autenticado e aplicar o desconto pessoalmente; o sistema registra sua identificação. A venda precisa conter ao menos um item. Uma venda cancelada não pode ser cancelada novamente nem apagada.

Os campos de usuário podem usar vínculo anulável com cópia do nome, para que o histórico continue legível caso uma conta seja desativada ou removida conforme a política administrativa.

## 4. ItemVenda

Registra cada produto e a condição praticada no momento da venda. O modelo está implementado e preserva nome, código, preço e custo unitário.

| Campo | Descrição |
|---|---|
| `id` | Chave primária. |
| `venda_id` | Referência protegida à venda. |
| `produto_id` | Referência protegida ao produto. |
| `nome_produto` | Cópia histórica do nome. |
| `codigo_barras` | Cópia histórica, quando disponível. |
| `preco_unitario` | Preço de venda no momento da operação. |
| `custo_unitario` | Cópia do custo de aquisição no momento da operação; anulável enquanto o custo do produto não for conhecido. |
| `quantidade` | Quantidade vendida, maior que zero. |
| `subtotal` | `preco_unitario × quantidade`, antes do desconto da venda. |

Os valores históricos não mudam quando o produto for editado. O carrinho armazena produtos e quantidades, mas o preço vigente é consultado novamente no fechamento; o total atualizado é apresentado antes da confirmação. `custo_unitario` permite estimar custo e lucro histórico quando conhecido; itens sem custo informado não entram no cálculo de lucro. O desconto aplicado à venda continua registrado em `Venda`.

## 5. Pagamento

Cada venda possui exatamente um pagamento registrado. O modelo e o registro transacional estão implementados.

| Campo | Descrição |
|---|---|
| `id` | Chave primária. |
| `venda_id` | Referência única à venda (relação 1:1). |
| `forma_pagamento` | Dinheiro, Pix ou cartão. |
| `valor_pago` | Valor destinado a quitar a venda; deve ser igual ao total. |
| `valor_recebido` | Valor entregue pelo cliente, informado somente para dinheiro. |
| `troco` | `valor_recebido - valor_pago` para dinheiro; zero nos demais casos. |
| `data_pagamento` | Data e hora do registro. |

Pix e cartão são registrados manualmente, sem integração ou confirmação externa nesta etapa. Não há pagamentos divididos. O registro de cancelamento também não confirma nem processa reembolso; o reembolso é feito fora do sistema.

## 6. MovimentacaoEstoque

Registra cada alteração do saldo. A quantidade movimentada é uma variação **com sinal**: positiva para entrada/estorno e negativa para saída/venda/perda. O modelo e as operações de entrada, perda, saída manual, ajuste, venda e estorno estão implementados.

| Campo | Descrição |
|---|---|
| `id` | Chave primária. |
| `produto_id` | Referência protegida ao produto. |
| `tipo` | Saldo inicial, entrada, venda, saída manual, perda, ajuste ou estorno de venda. |
| `variacao_quantidade` | Alteração assinada, diferente de zero para movimentações operacionais. |
| `quantidade_anterior` | Saldo imediatamente antes da operação. |
| `quantidade_posterior` | Saldo imediatamente depois da operação. |
| `data_movimentacao` | Data e hora da operação. |
| `usuario_id` | Usuário responsável por uma operação humana, quando aplicável. |
| `responsavel_nome` | Nome copiado para preservar a identificação histórica. |
| `motivo` | Justificativa para os tipos que a exigem. |
| `item_venda_id` | Referência ao item que originou a venda ou o estorno, quando aplicável. |
| `movimento_estornado_id` | Referência única à movimentação original, para estorno de venda. |

Invariante de saldo: `quantidade_anterior + variacao_quantidade = quantidade_posterior`, e o saldo posterior não pode ser negativo. A aplicação valida a regra e atualiza `Produto.quantidade` na mesma transação.

Motivo é obrigatório para entrada, saída manual, perda, ajuste e cancelamento. A movimentação de venda referencia seu item; o saldo inicial recebe o motivo fixo “Saldo inicial da implantação”. Toda operação humana registra o usuário. Para o saldo inicial criado pelo processo de implantação, `responsavel_nome` identifica “Sistema — saldo inicial”, sem atribuir a movimentação a uma pessoa que não a realizou.

Movimentações não são editadas nem apagadas para corrigir o passado: registra-se uma nova movimentação corretiva.

## 7. Relacionamentos e usuários

- Categoria 1:N Produto.
- Produto 1:N ItemVenda.
- Produto 1:N MovimentacaoEstoque.
- Venda 1:N ItemVenda.
- Venda 1:1 Pagamento.
- ItemVenda 1:N MovimentacaoEstoque (venda e estorno).
- Usuário 1:N Venda.
- Usuário 1:N MovimentacaoEstoque.
- Usuário 1:N cancelamentos e autorizações de desconto.

Os usuários são gerenciados pelo Django. Os grupos `Atendente` e `Gerente` são criados pela migração; a autorização é verificada no backend. Superusuários são tratados como Gerente.

| Operação | Atendente | Gerente |
|---|---:|---:|
| Registrar vendas | Sim | Sim |
| Cancelar vendas | Sim | Sim |
| Aplicar descontos | Não | Sim |
| Ajustar estoque | Não | Sim |
| Registrar entradas | Sim | Sim |
| Registrar perdas | Sim | Sim |
| Registrar saída manual | Não | Sim |

Entradas, saídas manuais, perdas e ajustes exigem motivo. Ajustes e saídas manuais são exclusivos do Gerente. O primeiro superusuário tem acesso de Gerente. A criação e associação de contas Atendente e de outros Gerentes são feitas pelo Admin, atribuindo o grupo apropriado. Usuários de equipe sem um desses grupos não acessam o painel.

## 8. Integridade e transações

A finalização da venda executa, em uma única transação:

1. validar que a venda tem itens e que os produtos estão ativos;
2. validar quantidades disponíveis e preços;
3. calcular subtotal, desconto e total no servidor;
4. criar venda, itens e pagamento;
5. atualizar os saldos;
6. registrar as movimentações.

Se uma etapa falhar, nenhuma alteração da venda é confirmada. O cancelamento também é atômico: valida o estado da venda, registra responsável e motivo, cria os estornos e muda o status uma única vez.

As relações históricas usam proteção contra exclusões acidentais. As restrições incluem: pagamento único por venda; quantidade de item positiva; saldo não negativo; desconto entre zero e 10% do subtotal; e vínculo único entre uma movimentação original e seu estorno. A regra de pelo menos um item e as transições de status são validadas pelo serviço transacional da aplicação, pois não são garantidas por uma simples chave estrangeira.

SQLite pode ser usado durante a implementação inicial e testes locais. Antes de habilitar vendas em caixas simultâneos, o ambiente deverá migrar para PostgreSQL. O PDV deverá usar transações atômicas e bloqueio das linhas de produto durante a baixa; SQLite não será considerado o banco de operação concorrente.

## 9. Implantação do saldo e relatórios

Na implantação, a quantidade atual de cada produto vira saldo inicial, com data de implantação identificável. Não se criam vendas nem movimentações antigas fictícias. Produtos com saldo zero não precisam de uma movimentação de quantidade zero.

Os relatórios usam vendas finalizadas para faturamento e comparam o período selecionado, de até 365 dias, ao intervalo imediatamente anterior de igual duração. Vendas canceladas permanecem consultáveis, mas não compõem o faturamento. Produtos ativos sem vendas no intervalo aparecem entre os menos vendidos com quantidade zero; produtos arquivados com vendas históricas continuam nas classificações. A tela mostra até 30 movimentações recentes e o PDF inclui todas as movimentações do período, além de resumo, faturamento agrupado por dia/semana/mês, produtos mais/menos vendidos e estoque baixo atual.

Na primeira versão, o cancelamento é da venda inteira; devoluções parciais de itens ficam fora do escopo.

## 10. Ordem de implementação

1. Concluído: criar os grupos, ampliar Produto, registrar saldos iniciais e implementar as operações do módulo Estoque.
2. Concluído: criar Venda, ItemVenda e Pagamento e implementar PDV, confirmação de preços, descontos, baixa e cancelamento com estorno.
3. Concluído: criar relatórios por período, indicadores e exportação PDF.
4. Antes de habilitar operação simultânea em vários caixas, migrar e validar o ambiente PostgreSQL.
5. Ampliar testes para cenários reais de operação e concorrência antes da implantação.

**Resultado esperado:** estoque auditável, vendas e pagamentos históricos, permissões por função, cancelamento com estorno e dados consistentes para relatórios, preservando o catálogo e os dados históricos.
