# Skopos Financeiro — KPIs para livrarias

Aplicativo em Python, Streamlit, SQLite local e PostgreSQL externo para acompanhar o financeiro da livraria e analisar vendas por pedido, título, cliente e canal, com execução local e publicação no Streamlit Community Cloud.

Endereço publicado: [skopos.streamlit.app](https://skopos.streamlit.app/).

Documentação atualizada em 09/10/2026. As mudanças locais precisam ser enviadas ao GitHub para chegar à versão publicada.

## O que o painel mostra

- **Financeiro:** receitas e despesas pagas, saldo dos lançamentos, contas a pagar e receber, fluxo de caixa e orçamento.
- **Vendas:** faturamento líquido, CMV estimado, margem bruta, margem de contribuição, pedidos, ticket médio, clientes ativos, frequência, descontos e frete.
- **Estoque:** valor da última posição importada, itens abaixo do mínimo e giro quando há pelo menos duas posições históricas.
- **Análise comercial:** evolução mensal, canais, ranking de clientes, receita por UF e curva ABC de títulos.
- **Curva ABC:** página dedicada para títulos ou clientes, com critério por faturamento, exemplares ou pedidos, limites ajustáveis e exportação CSV.
- **Integração:** importação manual de CSV e configuração de leitura de API REST.

## Navegação e personalização

- **Home:** saudação, capa da empresa, filtro de período, atalhos configuráveis e resumo financeiro.
- **Acompanhamento:** Visão geral, Curva ABC, Relatórios, Fluxo de caixa, Contas e Insights com IA.
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

### Atalho do Windows

No botão **Atalho desktop**, ao lado de Conta na barra superior, qualquer usuário pode baixar `Skopos-Atalho.zip`. Extraia o ZIP e execute `Criar atalho.vbs`: ele cria `Skopos Online` na área de trabalho e guarda o ícone em `%LOCALAPPDATA%\Skopos`. O atalho abre `https://skopos.streamlit.app/` no navegador, com acesso pela internet e login Google. Ele não inicia o servidor local. O arquivo `Skopos.url` da raiz é uma alternativa simples para abrir o mesmo endereço.

Para executar a versão local, use `.\.venv\Scripts\python.exe -m streamlit run app.py` dentro da pasta do projeto. O iniciador `iniciar_skopos.pyw` não faz parte destes arquivos. Fechar a guia do navegador não encerra o servidor local; encerre-o no terminal que o iniciou.

## Login com Google

O primeiro login com uma conta Google cadastra o perfil no SQLite; acessos seguintes atualizam o último acesso. O Google autentica a conta e confirma sua identidade; o app não recebe nem armazena a senha. Para ativar o login:

1. Instale as dependências com `pip install -r requirements.txt`.
2. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml`.
3. No arquivo copiado, preencha `client_id` e `client_secret` do Google e troque `cookie_secret` por um valor aleatório longo.
4. No arquivo local, defina `redirect_uri = "http://localhost:8501/oauth2callback"` e autorize esse endereço no cliente OAuth Google. O exemplo usa a URL local; ajuste-o para a URL publicada ao configurar o Cloud.
5. Reinicie o app e use o botão do provedor configurado.

O arquivo `.streamlit/secrets.toml` está ignorado pelo Git e não deve ser compartilhado. Os dados são filtrados pela empresa à qual a conta Google está vinculada.

| Perfil | Permissões principais |
| --- | --- |
| Administrador/suporte | Opera os dados, gerencia equipe e perfil da empresa e configura Horus e IA. |
| Gestor | Opera lançamentos, orçamento e importações e consulta os painéis. Não acessa a configuração de Horus e IA nem a gestão completa da equipe. |
| Colaborador | Consulta dados, sem editar. |

Em **Conta → Equipe**, o administrador adiciona pessoas pelo e-mail da conta Google. O app **não envia e-mails automaticamente**: registra o convite, que concede acesso quando a pessoa entra com esse e-mail verificado pelo Google. Se a conta já tiver entrado no Skopos, a inclusão é imediata. A confirmação de **Adicionar ou convidar** permanece após a atualização automática, até clicar em **Fechar mensagem**.

Usuários vinculados a mais de uma livraria podem alternar a empresa pelo menu Conta da barra superior. Os perfis valem dentro da empresa e não concedem acesso global às outras livrarias.

## Publicar no Streamlit Community Cloud

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

## Carregar dados comerciais

Abra **Vendas e estoque** e baixe os modelos CSV. A importação aceita vírgula ou ponto e vírgula como separador e grava os dados no banco configurado. Há modelos vazios e exemplos preenchidos para vendas e estoque; os exemplos contêm dados fictícios e devem ser substituídos antes de importar.

### CSV de vendas

Uma linha por combinação de pedido e SKU. Colunas obrigatórias:

    pedido_id,data,sku,titulo,quantidade,preco_unitario,custo_unitario

Campos opcionais:

    cliente,cliente_id,canal,cidade,uf,categoria,quantidade_devolvida,desconto,impostos,frete_cobrado,frete_custo,status

Datas devem usar AAAA-MM-DD. Números devem usar ponto decimal, sem separador de milhar, moeda, porcentagem ou notação científica: use 1234.56. Valores como 1.234,56, 1,234.56 e 49,90 são rejeitados. Cada erro de formato indica a linha do CSV (cabeçalho = linha 1), a coluna e o valor; nenhum registro é gravado enquanto houver erro. Cabeçalhos repetidos, colunas desconhecidas, campos obrigatórios vazios e linhas com número errado de campos também são rejeitados. Status permitido: Concluído, Cancelado ou Devolvido. Desconto e impostos são valores por linha. Frete cobrado e custo do frete são valores do pedido: preencha-os somente na primeira linha daquele pedido. A chave de atualização é pedido + SKU; um novo envio atualiza uma venda importada anteriormente. cliente_id é preferível ao nome para contar clientes e frequência sem confundir pessoas com nomes iguais.

Cancelamentos são excluídos dos valores de venda. Devoluções reduzem unidades e faturamento. CMV é calculado pelas unidades líquidas multiplicadas pelo custo unitário recebido.

Arquivos UTF-8 com BOM e Latin-1 são aceitos. Campos numéricos opcionais vazios assumem zero; textos inválidos e valores não finitos são rejeitados, tanto nas vendas quanto no estoque.

### CSV de estoque

Uma linha por SKU para cada data de inventário. Colunas obrigatórias:

    data_ref,sku,titulo,quantidade,custo_unitario

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

Os testes usam bancos SQLite temporários, simulam a identidade e bloqueiam chamadas externas. O adaptador PostgreSQL tem testes de tradução; a validação de integração real deve ser feita ao configurar o serviço externo. Eles cobrem as telas, importação CSV, números inválidos, isolamento de empresa no Horus, busca, formulários, confirmação de remoção e vencimentos. O resumo da IA usa vencimentos para contas pendentes, assim como a tela Contas.

## Histórico e remoção de importações

Em **Vendas e estoque → Histórico de importações e limpeza de dados**, cada envio de CSV ou consulta importada do Horus aparece como lote. Administradores podem exportar as linhas do lote e excluí-lo após confirmar. A exclusão só alcança a empresa ativa. Gestores podem importar e consultar o histórico, mas não excluir lotes.

Uma reimportação de pedido + SKU ou data de estoque + SKU transfere a linha para o lote mais recente. Excluir o lote antigo preserva essa linha; excluir o lote atual remove a linha, sem restaurar valores anteriores. A exportação do lote é uma cópia dos registros internos para consulta e backup, não o modelo CSV de importação.

Dados anteriores à criação do histórico são preservados e agrupados por empresa/tipo com o nome **Dados anteriores ao histórico**. Não é possível recuperar o nome do arquivo original retroativamente. A migração não exclui dados automaticamente.

Novos lançamentos gerados pelo botão de demonstração recebem uma marca e podem ser apagados em **Apagar demonstração**. Registros financeiros antigos sem essa marca devem ser revisados e removidos por ID em **Lançamentos**; o app não presume que sejam fictícios.

## Celular e cores

O menu lateral usa abertura automática: inicia recolhido em telas pequenas. A barra superior usa fundo opaco em ambos os temas, controles compactos no celular e mantém o botão para abrir o menu. O atalho de Windows aparece em telas de desktop. Os logos do login e da barra lateral usam os SVGs de assets.

A tela de login usa classes próprias para a composição, reduzindo a dependência do seletor CSS :has. A navegação auxiliar de desktop ainda usa esse seletor. As cores foram conferidas em Chrome e Edge, em larguras de 1440, 390 e 360 px, nos modos claro e escuro. Também houve conferência em emulação Chrome Android com toque e preferência do sistema por tema claro ou escuro; os gráficos seguem o tema do Skopos. Safari, Firefox e aparelhos físicos ainda precisam de conferência. Configurações de alto contraste ou extensões que alteram cores também podem mudar a aparência.
