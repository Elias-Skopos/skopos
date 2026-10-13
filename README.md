# Skopos Financeiro — KPIs para livrarias

Aplicativo em Python, Streamlit, SQLite local e PostgreSQL externo para acompanhar o financeiro da livraria e analisar vendas por pedido, título, cliente e canal, com execução local e publicação no Streamlit Community Cloud.

Endereço publicado: [skopos.streamlit.app](https://skopos.streamlit.app/).

Documentação atualizada em 13/10/2026. As mudanças locais precisam ser enviadas ao GitHub para chegar à versão publicada.

## Instalador Windows e site público

O candidato **0.1.5** abre o painel em uma janela própria com pywebview/WebView2, oculta os comandos auxiliares da inicialização e corrige as cores da demo no modo escuro. Fechar a janela encerra a execução local; abrir novamente o atalho reativa a janela existente. Consulte [ATUALIZACAO_0_1_5.md](ATUALIZACAO_0_1_5.md) para atualização e validação. Os resultados das versões anteriores abaixo são históricos.

O piloto **0.1.3** foi compilado com Python e PostgreSQL no pacote, instalação por usuário e atalhos locais. O site público oferece download e demonstração com números fictícios, sem conta, usando o visual do login atual. A publicação será manual; o download está desativado até a Release existir. Consulte [PUBLICACAO_WINDOWS.md](PUBLICACAO_WINDOWS.md) para os arquivos, checksum, publicação, primeiro uso e limites dos testes.

Na edição instalada, cada perfil pode usar senha local e vincular Google à mesma identidade. Dados ficam em `%LOCALAPPDATA%\Skopos\Data`; o nome local é definido na primeira abertura. A instalação começa vazia e não transfere automaticamente os dados desta pasta ou do Cloud. O executável 0.1.3 passou no teste de preparação de PostgreSQL em pasta nova; ainda falta a validação completa em um Windows limpo e o login Google real.

## O que o painel mostra

- **Financeiro:** receitas e despesas pagas, saldo dos lançamentos, contas a pagar e receber, fluxo de caixa e orçamento.
- **Vendas:** faturamento líquido, CMV estimado, margem bruta, margem de contribuição, pedidos, ticket médio, clientes ativos, frequência, descontos e frete.
- **Estoque:** valor da última posição importada, itens abaixo do mínimo e giro quando há pelo menos duas posições históricas.
- **Análise comercial:** evolução mensal, canais, ranking de clientes, receita por UF e curva ABC de títulos.
- **Curva ABC:** página dedicada para títulos ou clientes, com critério por faturamento, exemplares ou pedidos, limites ajustáveis e exportação CSV.
- **Integração:** importação manual de CSV e configuração de leitura de API REST.

## Navegação e personalização

- **Home:** saudação, capa da empresa, filtro de período e três blocos principais: ponto de equilíbrio mensal estimado, checklist dos próximos três pagamentos e entradas/saídas realizadas. Favoritos ficam abaixo desse resumo.
- **Acompanhamento:** Visão geral, Relatórios, Fluxo de caixa, Contas, Curva ABC e Insights com IA.
- **Alimentar e planejar:** Vendas e estoque, Lançamentos e Orçamento, disponíveis para administrador e gestor.
- **Gestão da Plataforma:** API do Horus, Configuração de IA e Conta, disponíveis para administrador.
- **Conta → Equipe:** inclusão de pessoas, convites pendentes, alteração de perfil e remoção de acesso. A gestão da equipe fica dentro de Conta em Gestão da Plataforma.
- **Conta:** configurações de capa, atalhos e perfil da empresa, conforme as permissões.

O filtro de período compartilhado aparece em um botão compacto à direita; as datas são editadas ao abrir o calendário. Há modo claro/escuro e ocultação dos valores na Home e na Visão geral. O logo da barra lateral retorna à Home na mesma guia. As imagens da marca ficam em `assets/logo_login.svg` (login) e `assets/logo_barra_lateral.svg` (barra lateral).

Em Lançamentos, Tipo e Status atualizam categoria e vencimento antes do envio do formulário. Ao alternar um lançamento pago para pendente, selecione o vencimento no campo exibido nas ações. A busca trata o texto digitado literalmente. Na remoção de colaboradores por Conta, marque a confirmação e envie o formulário; o servidor verifica a confirmação antes de remover o acesso.

O CSS tenta ocultar os controles e o selo do Streamlit Cloud para evitar sobreposição com a barra do Skopos. O resultado deve ser conferido na hospedagem após atualizações do Streamlit.

## Executar localmente

Execute os comandos dentro da pasta `skopos`:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    streamlit run app.py

O banco `livraria.db` é criado automaticamente. As pastas `backup_*` são cópias locais e não fazem parte da publicação.

### Iniciador local do Windows

O botão **Atalho desktop** foi retirado. O instalador cria os atalhos que iniciam o aplicativo local. Atalhos antigos chamados `Skopos Online` e o arquivo `Skopos.url` continuam apontando para o site hospedado; eles não iniciam o aplicativo neste computador.

Para executar a versão local com PostgreSQL, use **Iniciar Skopos local.cmd**: ele inicia o banco, faz um backup e abre o aplicativo. As instruções de manutenção estão em [POSTGRESQL_LOCAL.md](POSTGRESQL_LOCAL.md). Sem PostgreSQL configurado, também é possível executar `.\.venv\Scripts\python.exe -m streamlit run app.py` com SQLite. Fechar a guia do navegador não encerra o servidor local; encerre-o no terminal que o iniciou.

O planejamento da versão instalável está em [BACKLOG_INSTALAVEL.md](BACKLOG_INSTALAVEL.md), com etapas, decisões pendentes e critérios de conclusão.

Os caminhos persistentes são centralizados em `local_paths.py`. Sem configuração adicional, este projeto continua usando suas pastas atuais. A edição instalada fornece `SKOPOS_DATA_DIR` (pasta absoluta dos dados, Secrets e backups) e `SKOPOS_POSTGRES_RUNTIME` (binários `pgsql`, contendo `bin/`, `lib/` e `share/`), prepara permissões e carrega os Secrets da pasta de dados. Essas opções não copiam nem migram um banco existente.

`local_launcher.py` prepara o banco, valida a configuração e aguarda a prontidão do servidor. Na edição instalada, `desktop_window.py` carrega o painel em sua própria janela e controla o encerramento. O nome configurável segue `skopos.nome-da-empresa.localhost:8501`, com acesso somente neste computador e autenticação local OIDC. O iniciador de desenvolvimento pelo `.cmd` continua abrindo o navegador, usando o Google web e exigindo a origem configurada nos Secrets. Consulte [POSTGRESQL_LOCAL.md](POSTGRESQL_LOCAL.md) para manutenção dessa instalação de desenvolvimento.

### Os três blocos financeiros da Home

Em **Ponto de equilíbrio → Configurar ponto de equilíbrio**, o proprietário informa custos fixos mensais e margem de contribuição estimada. Use os valores completos da empresa e considere CMV, descontos, impostos, taxas de cartão e outros custos variáveis na margem, evitando duplicação. As premissas são compartilhadas dentro da empresa e a fórmula usa cálculo decimal: custos fixos / (margem / 100). Margem zero ou negativa aparece como sem equilíbrio. Não são cadastradas despesas nem recebimentos ao salvar essas premissas. O valor é uma estimativa mensal, independente do filtro, e não inclui parcelas do principal de dívidas nem reservas.

**Próximos compromissos** mostra até três despesas pendentes com vencimento, ordenadas pela data, incluindo atrasadas primeiro. Essa agenda não depende do filtro de período. O proprietário pode marcar o que já pagou, informar a data efetiva e usar **Confirmar pagamentos**. A baixa é transacional, verifica a permissão atual e atualiza Contas e entradas/saídas. Colaboradores apenas consultam. Pendências sem vencimento aparecem em um aviso para revisão em Contas.

**Entradas e saídas** soma somente receitas recebidas e despesas pagas no período selecionado, pela data efetiva; registros antigos sem essa data usam a original. Vendas ainda não recebidas e contas pendentes não são somadas. A opção de ocultar valores também protege os três blocos; mostre os valores para editar as premissas.

## Login com Google

O primeiro login com uma conta Google cadastra o perfil no banco configurado; acessos seguintes atualizam o último acesso. O Google autentica a conta e confirma sua identidade; o app não recebe nem armazena a senha. Para ativar o login:

1. Instale as dependências com `pip install -r requirements.txt`.
2. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml`.
3. No arquivo copiado, preencha `client_id` e `client_secret` do Google e troque `cookie_secret` por um valor aleatório longo.
4. No arquivo local, defina `redirect_uri = "http://localhost:8501/oauth2callback"` e autorize esse endereço no cliente OAuth Google. O exemplo usa a URL local; ajuste-o para a URL publicada ao configurar o Cloud.
5. Reinicie o app e use o botão do provedor configurado.

O arquivo `.streamlit/secrets.toml` está ignorado pelo Git e não deve ser compartilhado. Os dados são filtrados pela empresa à qual a conta Google está vinculada.

| Perfil | Permissões principais |
| --- | --- |
| Proprietário | Opera os dados, gerencia equipe e perfil da empresa e configura Horus e IA. |
| Colaborador | Consulta dados, gerencia suas preferências e pode sair da empresa, sem editar dados da empresa. |

Após o login, a tela de entrada apresenta empresas vinculadas, convites pendentes e criação de empresa. Quem cria uma empresa recebe o perfil Proprietário, mesmo se já for colaborador de outra. O segmento, nome, cidade e e-mail de contato são configurados no cadastro e em **Empresa → Perfil da empresa**. Empresas existentes recebem o segmento Livraria durante a atualização. Ao criar uma empresa, a página **Empresa** abre com **Equipe e convites** expandido para convidar pessoas; essa etapa é opcional.

O menu **Conta** oferece **Empresa** (somente proprietários), **Meu perfil** e **Empresas e convites**. A gestão da equipe, capa e integrações pertence à empresa. Nome de exibição, tema e favoritos são pessoais; favoritos antigos da empresa servem como padrão até a pessoa salvar sua escolha.

Em **Empresa → Equipe e convites**, o proprietário registra convites pelo e-mail da conta Google. O botão **+** adiciona outro campo de e-mail, preservando os já preenchidos. Cada pessoa pode ter seu próprio perfil de acesso. **Adicionar à empresa** registra todos os convites de uma vez; e-mails inválidos ou repetidos impedem o lote inteiro de ser gravado. Linhas extras vazias são ignoradas. Nenhum acesso é concedido automaticamente, mesmo a usuários já cadastrados: a pessoa deve aceitar ou recusar após login com e-mail verificado. Convites valem por sete dias, podem ser cancelados e podem ser registrados novamente. A empresa precisa manter pelo menos um proprietário; sair da empresa preserva seus dados e a identidade do usuário.

O envio de e-mail é opcional: configure `[email]` conforme `.streamlit/secrets.toml.example` com SMTP autenticado e TLS (587/STARTTLS ou 465/TLS) e o endereço da aplicação. Sem configuração, o convite fica disponível na entrada; compartilhe o endereço com o convidado. Falha no envio não apaga o convite nem concede acesso.

A opção de empresa Demo foi retirada da edição protegida. A nova demonstração anônima fica na página pública e usa somente dados fictícios em memória. Empresas de demonstração antigas continuam isoladas e não aparecem na seleção de empresas. Na atualização de um SQLite existente, é criado um backup em `backup_account_upgrade/` antes de alterar a estrutura. Administradores existentes permanecem proprietários (código interno `administrator`); gestores antigos passam a colaboradores. Revise esses vínculos na gestão da equipe se precisar conceder propriedade.

Usuários vinculados a mais de uma empresa podem alternar pelo menu Conta da barra superior. Os perfis valem dentro de cada empresa e não concedem acesso global.

### Excluir e recuperar uma empresa

Em **Empresa → Excluir empresa**, somente um proprietário pode excluir a empresa. É necessário digitar o nome exato e marcar a confirmação; o servidor verifica novamente a propriedade no momento da operação. A exclusão remove a empresa da seleção, revoga os acessos e convites e retira seus lançamentos, vendas, estoque, importações, orçamento, recorrências, saldo inicial e configurações da área ativa. Perfis pessoais e outras empresas permanecem.

Antes da remoção, é guardada uma cópia dos dados e vínculos em `company_deletion_backups`, no mesmo banco e na mesma transação. Se a cópia ou a exclusão falhar, nenhuma remoção é confirmada. Na tela **Empresas e convites → Empresas excluídas**, somente o proprietário que realizou a exclusão pode recuperar a empresa, confirmando a restauração dos dados e acessos da equipe. A recuperação preserva os identificadores e recusa substituir registros existentes. Uma exclusão de empresa não elimina essa cópia de recuperação; não há expurgo definitivo nesta etapa.

Essa cópia também entra na migração e nos backups PostgreSQL do Skopos. Como fica no mesmo banco, continue mantendo backups externos para recuperação de falhas do disco. A tabela é criada automaticamente na próxima inicialização do app; nenhuma empresa real é removida pela atualização do código.

## Publicar no Streamlit Community Cloud

Para publicar a atualização 0.1.4 e a página pública de download e demonstração, siga [ATUALIZACAO_0_1_4.md](ATUALIZACAO_0_1_4.md). [PUBLICACAO_WINDOWS.md](PUBLICACAO_WINDOWS.md) conserva as instruções e resultados da entrega anterior. As instruções abaixo se referem à edição protegida com login e banco. A demonstração pública é separada da seleção de empresas e não acessa a base real.

Envie ao GitHub os módulos Python do app, `app_chrome.css`, `requirements.txt`, `README.md`, `.gitignore`, `assets/` e `.streamlit/config.toml`. O arquivo `.streamlit/secrets.toml.example` contém somente exemplos e pode ser enviado.

Não envie `.streamlit/secrets.toml`, `.env`, bancos `.db`, CSVs com dados reais, ambientes virtuais, caches, logs ou backups. Os iniciadores do Windows não são necessários na hospedagem. Se uma credencial foi publicada, substitua-a no provedor; apagar o arquivo não elimina o histórico do Git.

1. Acesse [Streamlit Community Cloud](https://share.streamlit.io/), crie um app e selecione o repositório e a branch.
2. Se o conteúdo de `skopos` estiver na raiz do repositório, escolha `app.py` como arquivo principal. Se preservar a pasta, escolha `skopos/app.py` e mantenha `.streamlit/config.toml` na raiz do repositório para a configuração da hospedagem.
3. Use o `requirements.txt`, que inclui `streamlit[auth]` para o login com Authlib.
4. Em **Settings → Secrets**, configure:

```toml
[auth]
redirect_uri = "https://skopos.streamlit.app/oauth2callback"
cookie_secret = "SUBSTITUA_POR_UM_SEGREDO_ALEATORIO_LONGO"

[auth.google]
client_id = "SEU_CLIENT_ID_DO_GOOGLE"
client_secret = "SEU_CLIENT_SECRET_DO_GOOGLE"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

5. No Google Cloud, em **Google Auth Platform → Clientes**, abra o cliente correspondente ao `client_id` e autorize `https://skopos.streamlit.app/oauth2callback`. Mantenha também a URI local se usar o app no PC.
6. Salve e teste o login. Os valores TOML precisam estar entre aspas; não cole links formatados em Markdown nos Secrets.

Para atualizar a publicação, envie as alterações ao GitHub na branch configurada. A navegação fica em `app.py`; os ajustes de aparência ficam em `ui.py`.

### Persistência dos dados

O app aceita PostgreSQL externo, configurado por `[database].url` nos Secrets ou pela variável `SKOPOS_DATABASE_URL`. Sem conexão externa configurada, usa SQLite local. O armazenamento local do Community Cloud **não tem persistência garantida**. Quando a conexão externa está configurada e falha, o app interrompe a operação: não cria um banco local alternativo.

Para ativar a persistência, crie o PostgreSQL, migre os dados que deseja conservar e configure a mesma conexão no Cloud. Consulte [POSTGRESQL.md](POSTGRESQL.md). O suporte e o migrador estão implementados, mas a conexão real depende do provisionamento do serviço. Bancos do PC e do Cloud só compartilham dados se apontarem para o mesmo PostgreSQL.

Referências: [publicação](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings) e [persistência](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data).

### Problemas comuns

- **Login Google não configurado:** confira `client_id`, `client_secret` e `server_metadata_url` dentro de `[auth.google]` nos Secrets da hospedagem.
- **`StreamlitMissingAuthlibError`:** reinstale `streamlit[auth]` no Python que executa o app e reinicie o servidor.
- **`redirect_uri_mismatch`:** a URI dos Secrets precisa coincidir exatamente com uma URI autorizada no mesmo cliente OAuth Google.
- **Barra da hospedagem cobrindo o app:** publique o `ui.py` atualizado. Para apps públicos, o modo oficial de incorporação pode ser acessado em [skopos.streamlit.app/?embed=true](https://skopos.streamlit.app/?embed=true).

## Rotina simples: vendas diárias e financeiro

Quem tem apenas o total vendido em cada dia pode usar **Vendas e estoque → Importar vendas diárias**. Baixe o modelo ou o exemplo preenchido, substitua os dados de exemplo e envie um CSV com `data;total_vendas`. Datas usam `DD-MM-AAAA`; valores usam vírgula decimal, sem separador de milhar, com até duas casas (`1250,00`). Todas as importações CSV usam ponto e vírgula (`;`) para separar as colunas. Uma data aparece uma única vez por arquivo. Reimportar a mesma data atualiza seu total. Um dia sem registro é desconhecido; para informar um dia sem vendas, use zero.

Esses totais representam vendas realizadas. Não criam pedidos fictícios, recebimentos, margens ou clientes e não são somados às vendas por item. A Visão geral mostra o total e a média apenas dos dias informados, além da disponibilidade dos demais dados e suas datas de atualização.

Em **Lançamentos → Importar lançamentos financeiros**, há modelo, exemplo, prévia e confirmação. Colunas obrigatórias: `referencia;data;tipo;categoria;descricao;valor;status`. O modelo também inclui `data_pagamento;vencimento;forma_pagamento;observacoes`.

- `referencia`: identificação estável e única da movimentação, por exemplo `ALUGUEL-2026-10`. A reimportação atualiza essa referência dentro da mesma empresa. Referências diferentes criam lançamentos diferentes; não duplique um registro manual no CSV.
- `data`: data do registro/documento, separada da data em que o dinheiro entra ou sai.
- `tipo`: `Receita` ou `Despesa`; `status`: `Pago` ou `Pendente`.
- `valor`: maior que zero, vírgula decimal e até duas casas.
- `data_pagamento`: obrigatória para `Pago`; vazia para `Pendente`.
- `vencimento`: obrigatório para `Pendente`.
- `forma_pagamento`: opcional, com padrão `Não informado`; `observacoes`: opcional.

Datas do registro, pagamento e vencimento usam `DD-MM-AAAA`. Arquivos com erros não gravam nenhuma linha. O histórico permite exportar os registros atuais do lote para conferência e excluir a importação após confirmar. Exclusões não recuperam valores anteriores substituídos por reimportação. Colaboradores consultam os dados, mas não importam, excluem nem gerenciam recorrências e saldo inicial.

Em **Lançamentos → Despesas recorrentes**, cadastre aluguel ou outras contas e gere os meses desejados, até 24 meses desde o início cadastrado. As contas são criadas como pendentes. Repetir a geração não duplica nem altera as contas existentes, inclusive as já pagas. Dias inexistentes no mês usam o último dia daquele mês. Desativar uma recorrência impede novas gerações, preservando contas existentes. Para reajustes, cadastre a nova regra no mês correto e revise as contas futuras já geradas.

Em **Fluxo de caixa**, informe o saldo consolidado de caixa e contas no início de uma data, antes das movimentações desse dia. O saldo inicial não é receita. A visão mostra saldo realizado pelos registros e projeção com contas pendentes; pagamentos anteriores ao início do filtro, mas posteriores ao saldo inicial, são considerados. Pendências vencidas entram no primeiro dia válido da projeção. Sem saldo inicial, o gráfico representa somente a variação dos lançamentos, não o dinheiro disponível. Transferências entre contas da própria empresa não devem ser registradas como entradas/saídas desse caixa consolidado.

Lançamentos novos registram a data efetiva do recebimento/pagamento; contas pendentes pedem essa data ao serem marcadas como pagas. As datas podem ser corrigidas em **Lançamentos → Ações sobre lançamento**. Registros antigos sem essa informação continuam usando a data original e precisam ser conferidos. Saldo calculado a partir de registros incompletos não comprova saldo bancário nem lucro.

## Carregar dados comerciais

Abra **Vendas e estoque** e baixe os modelos CSV. A importação usa ponto e vírgula (`;`) como separador e grava os dados no banco configurado. Há modelos vazios e exemplos preenchidos para vendas e estoque; os exemplos contêm dados fictícios e devem ser substituídos antes de importar. Baixe novamente os modelos anteriores à mudança de padrão de 12/10/2026.

### CSV de vendas

Uma linha por combinação de pedido e SKU. Colunas obrigatórias:

    pedido_id;data;sku;titulo;quantidade;preco_unitario;custo_unitario

Campos opcionais:

    cliente;cliente_id;canal;cidade;uf;categoria;quantidade_devolvida;desconto;impostos;frete_cobrado;frete_custo;status

Datas devem usar DD-MM-AAAA, como 12-10-2026. Números devem usar vírgula decimal, sem separador de milhar, moeda, porcentagem ou notação científica: use 1234,56. Valores como 1.234,56, 1,234.56 e 49.90 são rejeitados; inteiros como 10 são aceitos. Cada erro de formato indica a linha do CSV (cabeçalho = linha 1), a coluna e o valor; nenhum registro é gravado enquanto houver erro. Cabeçalhos repetidos, colunas desconhecidas, campos obrigatórios vazios e linhas com número errado de campos também são rejeitados. Status permitido: Concluído, Cancelado ou Devolvido. Desconto e impostos são valores por linha. Frete cobrado e custo do frete são valores do pedido: preencha-os somente na primeira linha daquele pedido. A chave de atualização é pedido + SKU; um novo envio atualiza uma venda importada anteriormente. cliente_id é preferível ao nome para contar clientes e frequência sem confundir pessoas com nomes iguais.

Cancelamentos são excluídos dos valores de venda. Devoluções reduzem unidades e faturamento. CMV é calculado pelas unidades líquidas multiplicadas pelo custo unitário recebido.

Arquivos UTF-8 com BOM e Latin-1 são aceitos. Campos numéricos opcionais vazios assumem zero; textos inválidos e valores não finitos são rejeitados, tanto nas vendas quanto no estoque. Os modelos, exemplos, prévias de importação e o CSV da consulta Horus para completar custos usam o padrão brasileiro. A padronização de 12/10/2026 foi validada em 70 testes, incluindo a integração PostgreSQL.

### CSV de estoque

Uma linha por SKU para cada data de inventário. Colunas obrigatórias:

    data_ref;sku;titulo;quantidade;custo_unitario

estoque_minimo é opcional. A chave de atualização é data de inventário + SKU. O giro exige pelo menos duas datas com inventário dentro do período selecionado.

## Configuração da API Horus

Em **Gestão da Plataforma → API do Horus**, disponível para administrador, informe a URL base terminada em `/Horus/api/TServerB2B/`, as credenciais Basic Auth e os códigos de empresa e filial. A ação **Testar conexão** consulta uma amostra do catálogo; **Consultar vendas** busca pedidos faturados e seus itens por período, usando a paginação documentada pelo Horus. Os parâmetros de conexão não sensíveis são salvos no banco; as credenciais ficam na sessão ou podem ser carregadas de `.streamlit/secrets.toml`:

    [horus_api]
    username = "seu_usuario"
    password = "sua_senha"

O app mostra uma prévia antes de importar os registros. Os exemplos públicos dos itens do Horus não incluem custo unitário. Para evitar calcular uma margem fictícia, a importação fica desabilitada quando esse custo não vier na resposta. Confirme com a FMZ qual consulta/campo fornece o custo dos produtos.

A consulta e suas credenciais de sessão são limpas ao trocar de empresa. A prévia só pode ser importada na empresa em que foi consultada; depois da troca, faça uma nova consulta usando os parâmetros da empresa selecionada.

A URL do Horus é validada antes da chamada. Em implantação pública, configure `HORUS_ALLOWED_HOSTS` no servidor com os hosts autorizados, separados por vírgula. Hosts que resolvem para endereços locais ou privados são bloqueados por padrão. Para uma instalação local que precise alcançar um Horus na rede da livraria ou em uma VPN confiável, o administrador pode definir `HORUS_ALLOW_PRIVATE_NETWORK=true` no ambiente do servidor. Isso também libera HTTP para esse ambiente privado; Basic Auth não criptografa credenciais em HTTP, portanto prefira HTTPS sempre que disponível. Não habilite essa opção em uma hospedagem pública sem uma rede privada controlada.

## Insights com IA

O administrador configura a chave e o modelo Gemini em **Gestão da Plataforma → Configuração de IA**. Em **Acompanhamento → Insights com IA**, os usuários podem conferir o resumo, autorizar o envio e gerar uma análise para o período global selecionado. O identificador do modelo é salvo nas configurações da empresa; a chave digitada fica somente na sessão e não é armazenada no SQLite. Para carregá-la no servidor, adicione ao `.streamlit/secrets.toml` local:

    [gemini]
    api_key = "sua_chave_da_api"

Também é possível definir a variável de ambiente `GEMINI_API_KEY`. Crie e gerencie chaves no [Google AI Studio](https://aistudio.google.com/app/apikey); as chaves ficam associadas a um projeto Google Cloud e podem exigir ativação de faturamento e restrições apropriadas. A página mostra o resumo antes do envio e pede autorização explícita. O resumo é limitado à empresa ativa e não inclui nome de cliente, e-mail, descrição de lançamento ou identificador da empresa; pode incluir os cinco títulos de livro com maior faturamento no período. As análises e a chave não são salvas no banco do Skopos.

No nível gratuito, o Google pode usar as solicitações e respostas para melhorar seus produtos e permitir revisão humana; no nível pago, informa que não as usa para esse fim. Evite enviar informações sigilosas no nível gratuito. O custo ou a quota dependem do modelo e do projeto. Consulte os [termos da Gemini API](https://ai.google.dev/gemini-api/terms), a [documentação de chaves](https://ai.google.dev/gemini-api/docs/generate-content/api-key) e os [modelos disponíveis](https://ai.google.dev/gemini-api/docs/models).

## Como interpretar os indicadores

- **Faturamento líquido:** vendas brutas menos devoluções, descontos e impostos informados.
- **CMV estimado:** unidades vendidas líquidas × custo unitário importado.
- **Margem bruta:** faturamento líquido − CMV.
- **Margem de contribuição:** faturamento líquido + frete cobrado − CMV − custo do frete.
- **Run-rate anual:** média diária do período × 365; é uma extrapolação simples, não uma previsão sazonal.
- **Giro de estoque:** CMV do período ÷ valor médio das posições de estoque importadas.

Os lançamentos financeiros e as vendas ficam em grupos separados para evitar dupla contagem. O resultado dos lançamentos financeiros não substitui conciliação bancária ou apuração contábil.

## Testes de regressão

Com as dependências instaladas, execute:

    .\.venv\Scripts\python.exe -m unittest discover -s tests -v

Os testes usam bancos SQLite temporários, simulam a identidade e bloqueiam chamadas externas. A integração PostgreSQL é opcional no comando acima e usa um banco separado, com schemas temporários; nesta instalação, execute `local_postgres.py test` para essa verificação. A validação de 12/10/2026 passou em 67 testes, incluindo PostgreSQL local, migração, importações simplificadas, saldo inicial, recorrências e permissões. A atualização da base local também preservou os registros anteriores e teve os backups validados por restauração em banco temporário. Nenhuma conexão real com o Horus da livraria foi feita nos testes.

## Histórico e remoção de importações

Em **Vendas e estoque → Histórico de importações e limpeza de dados**, cada envio de CSV ou consulta importada do Horus aparece como lote. Administradores podem exportar as linhas do lote e excluí-lo após confirmar. A exclusão só alcança a empresa ativa. Gestores podem importar e consultar o histórico, mas não excluir lotes.

Uma reimportação de pedido + SKU ou data de estoque + SKU transfere a linha para o lote mais recente. Excluir o lote antigo preserva essa linha; excluir o lote atual remove a linha, sem restaurar valores anteriores. A exportação do lote é uma cópia dos registros internos para consulta e backup, não o modelo CSV de importação.

Dados anteriores à criação do histórico são preservados e agrupados por empresa/tipo com o nome **Dados anteriores ao histórico**. Não é possível recuperar o nome do arquivo original retroativamente. A migração não exclui dados automaticamente.

Dados antigos gerados pelo antigo botão de demonstração permanecem identificados e podem ser apagados em **Apagar demonstração**. Registros financeiros antigos sem essa marca devem ser revisados e removidos por ID em **Lançamentos**; o app não presume que sejam fictícios.

## Celular e cores

O menu lateral usa abertura automática: inicia recolhido em telas pequenas. A barra superior usa fundo opaco em ambos os temas, controles compactos no celular e mantém o botão para abrir o menu. O atalho de Windows aparece em telas de desktop. Os logos do login e da barra lateral usam os SVGs de assets.

A tela de login usa classes próprias para a composição, reduzindo a dependência do seletor CSS :has. A navegação auxiliar de desktop ainda usa esse seletor. As cores foram conferidas em Chrome e Edge, em larguras de 1440, 390 e 360 px, nos modos claro e escuro. Também houve conferência em emulação Chrome Android com toque e preferência do sistema por tema claro ou escuro; os gráficos seguem o tema do Skopos. Safari, Firefox e aparelhos físicos ainda precisam de conferência. Configurações de alto contraste ou extensões que alteram cores também podem mudar a aparência.
