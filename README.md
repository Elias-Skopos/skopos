# Skopos Financeiro — KPIs para livrarias

Aplicativo local em Python, Streamlit e SQLite para acompanhar o financeiro da livraria e analisar vendas por pedido, título, cliente e canal.

## O que o painel mostra

- **Financeiro:** receitas e despesas pagas, saldo dos lançamentos, contas a pagar e receber, fluxo de caixa e orçamento.
- **Vendas:** faturamento líquido, CMV estimado, margem bruta, margem de contribuição, pedidos, ticket médio, clientes ativos, frequência, descontos e frete.
- **Estoque:** valor da última posição importada, itens abaixo do mínimo e giro quando há pelo menos duas posições históricas.
- **Análise comercial:** evolução mensal, canais, ranking de clientes, receita por UF e curva ABC de títulos.
- **Curva ABC:** página dedicada para títulos ou clientes, com critério por faturamento, exemplares ou pedidos, limites ajustáveis e exportação CSV.
- **Integração:** importação manual de CSV e configuração de leitura de API REST.

## Executar

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    streamlit run app.py

O banco livraria.db é criado automaticamente. A pasta backup_2026-09-30 guarda a cópia do app e do banco anteriores à versão de KPIs.

## Login com Google

O primeiro login com uma conta Google cadastra o perfil no SQLite; acessos seguintes atualizam o último acesso. O Google autentica a conta e confirma sua identidade; o app não recebe nem armazena a senha. Para ativar o login:

1. Instale as dependências com `pip install -r requirements.txt`.
2. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml`.
3. No arquivo copiado, preencha `client_id` e `client_secret` do Google e troque `cookie_secret` por um valor aleatório longo.
4. Cadastre `http://localhost:8501/oauth2callback` como URL de redirecionamento no provedor enquanto estiver executando localmente.
5. Reinicie o app e use o botão do provedor configurado.

O arquivo `.streamlit/secrets.toml` está ignorado pelo Git e não deve ser compartilhado. Em produção, use HTTPS e cadastre no provedor a URL pública terminada em `/oauth2callback`. Os dados financeiros e comerciais são filtrados pela empresa à qual a conta Google está vinculada. Cada empresa tem três perfis: **Administrador/suporte** (gerencia a equipe e o perfil da empresa), **Gestor** (opera lançamentos, orçamento, importações e integrações) e **Colaborador** (consulta os dados, sem editar). O administrador pode adicionar pessoas pelo e-mail da conta Google; o app não envia e-mails, e a pessoa recebe acesso ao entrar com esse e-mail. Se a conta já tiver entrado no Skopos, a inclusão é imediata. Usuários vinculados a mais de uma livraria podem alternar a empresa pela barra lateral. Os perfis valem dentro da empresa e não concedem acesso global às outras livrarias.

## Carregar dados comerciais

Abra **Vendas e estoque** e baixe os modelos CSV. A importação aceita vírgula ou ponto e vírgula como separador e grava os dados no SQLite.

### CSV de vendas

Uma linha por combinação de pedido e SKU. Colunas obrigatórias:

    pedido_id,data,sku,titulo,quantidade,preco_unitario,custo_unitario

Campos opcionais:

    cliente,cliente_id,canal,cidade,uf,categoria,quantidade_devolvida,desconto,impostos,frete_cobrado,frete_custo,status

Datas podem usar AAAA-MM-DD ou DD/MM/AAAA; valores com vírgula decimal também são aceitos. Desconto e impostos são valores por linha. Frete cobrado e custo do frete são valores do pedido: preencha-os somente na primeira linha daquele pedido. A chave de atualização é pedido + SKU; um novo envio atualiza uma venda importada anteriormente. cliente_id é preferível ao nome para contar clientes e frequência sem confundir pessoas com nomes iguais.

Cancelamentos são excluídos dos valores de venda. Devoluções reduzem unidades e faturamento. CMV é calculado pelas unidades líquidas multiplicadas pelo custo unitário recebido.

### CSV de estoque

Uma linha por SKU para cada data de inventário. Colunas obrigatórias:

    data_ref,sku,titulo,quantidade,custo_unitario

estoque_minimo é opcional. A chave de atualização é data de inventário + SKU. O giro exige pelo menos duas datas com inventário dentro do período selecionado.

## Configuração da API Horus

Em **Configuração de API**, informe a URL base terminada em `/Horus/api/TServerB2B/`, as credenciais Basic Auth e os códigos de empresa e filial. A ação **Testar conexão** consulta uma amostra do catálogo; **Consultar vendas** busca pedidos faturados e seus itens por período, usando a paginação documentada pelo Horus. Os parâmetros de conexão não sensíveis são salvos no banco; as credenciais ficam na sessão ou podem ser carregadas de `.streamlit/secrets.toml`:

    [horus_api]
    username = "seu_usuario"
    password = "sua_senha"

O app mostra uma prévia antes de importar os registros. Os exemplos públicos dos itens do Horus não incluem custo unitário. Para evitar calcular uma margem fictícia, a importação fica desabilitada quando esse custo não vier na resposta. Confirme com a FMZ qual consulta/campo fornece o custo dos produtos.

A URL do Horus é validada antes da chamada. Em implantação pública, configure `HORUS_ALLOWED_HOSTS` no servidor com os hosts autorizados, separados por vírgula. Hosts que resolvem para endereços locais ou privados são bloqueados por padrão. Para uma instalação local que precise alcançar um Horus na rede da livraria ou em uma VPN confiável, o administrador pode definir `HORUS_ALLOW_PRIVATE_NETWORK=true` no ambiente do servidor. Isso também libera HTTP para esse ambiente privado; Basic Auth não criptografa credenciais em HTTP, portanto prefira HTTPS sempre que disponível. Não habilite essa opção em uma hospedagem pública sem uma rede privada controlada.

## Insights com IA

Abra **Insights com IA** para informar uma chave da API Gemini, escolher o modelo e gerar uma análise para o período global selecionado. O identificador do modelo é salvo nas configurações da empresa; a chave digitada fica somente na sessão e não é armazenada no SQLite. Para carregá-la no servidor, adicione ao `.streamlit/secrets.toml` local:

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
