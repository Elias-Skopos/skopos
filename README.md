# Skopos Financeiro — KPIs para livrarias

Aplicativo em Python, Streamlit e SQLite para acompanhar o financeiro da livraria e analisar vendas por pedido, título, cliente e canal, com execução local e publicação no Streamlit Community Cloud.

Endereço publicado: [skopos.streamlit.app](https://skopos.streamlit.app/).

Documentação atualizada em 07/10/2026. As mudanças locais precisam ser enviadas ao GitHub para chegar à versão publicada.

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
- **Conta → Equipe:** inclusão de pessoas, convites pendentes, alteração de perfil e remoção de acesso. Também há um acesso a Equipe no menu Conta da barra superior.
- **Conta:** configurações de capa, atalhos e perfil da empresa, conforme as permissões.

Há modo claro/escuro e ocultação dos valores na Home e na Visão geral. O logo da barra lateral retorna à Home na mesma guia. As imagens da marca ficam em `assets/logo_login.png` (login) e `assets/Logo_barra_lateral.png` (barra lateral).

O CSS tenta ocultar os controles e o selo do Streamlit Cloud para evitar sobreposição com a barra do Skopos. O resultado deve ser conferido na hospedagem após atualizações do Streamlit.

## Executar localmente

Execute os comandos dentro da pasta `skopos`:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    streamlit run app.py

O banco `livraria.db` é criado automaticamente. As pastas `backup_*` são cópias locais e não fazem parte da publicação.

### Atalho do Windows

Na **Home → Skopos na área de trabalho**, qualquer usuário pode baixar `Skopos.url`. Salve na área de trabalho ou mova o arquivo de Downloads para lá. Dois cliques abrem `https://skopos.streamlit.app/` no navegador padrão, com acesso pela internet e login Google. Esse atalho não instala o app nem inicia o servidor local.

Nesta instalação, o atalho **Skopos** da área de trabalho executa `../iniciar_skopos.pyw` com `pythonw.exe`, sem abrir terminal. O iniciador abre o navegador quando o servidor responde e reutiliza um servidor já ativo na porta 8501. Fechar a guia não encerra o servidor.

O atalho usa `C:\Program Files\Python313\pythonw.exe` e precisa ser ajustado em outro computador. Instale as dependências no mesmo Python usado pelo atalho. Falhas são registradas em `skopos/inicializacao.log`.

## Login com Google

O primeiro login com uma conta Google cadastra o perfil no SQLite; acessos seguintes atualizam o último acesso. O Google autentica a conta e confirma sua identidade; o app não recebe nem armazena a senha. Para ativar o login:

1. Instale as dependências com `pip install -r requirements.txt`.
2. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml`.
3. No arquivo copiado, preencha `client_id` e `client_secret` do Google e troque `cookie_secret` por um valor aleatório longo.
4. No arquivo local, defina `redirect_uri = "http://localhost:8501/oauth2callback"` e autorize esse endereço no cliente OAuth Google. O arquivo de exemplo usa a URL publicada; ajuste-o para execução local.
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

Envie ao GitHub os módulos Python do app, `requirements.txt`, `README.md`, `.gitignore`, `assets/` e `.streamlit/config.toml`. O arquivo `.streamlit/secrets.toml.example` contém somente exemplos e pode ser enviado.

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

O app ainda usa SQLite local, inclusive no Cloud. O armazenamento local do Community Cloud **não tem persistência garantida**: empresas, acessos, lançamentos, vendas, estoque e configurações podem ser perdidos. O banco da hospedagem não sincroniza automaticamente com o banco do PC.

Antes de operar continuamente com dados reais na nuvem, é necessário adaptar o app para um banco externo persistente. Essa migração ainda não foi implementada.

Referências: [publicação](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings) e [persistência](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data).

### Problemas comuns

- **Login Google não configurado:** confira `client_id`, `client_secret` e `server_metadata_url` dentro de `[auth.google]` nos Secrets da hospedagem.
- **`StreamlitMissingAuthlibError`:** reinstale `streamlit[auth]` no Python que executa o app e reinicie o servidor.
- **`redirect_uri_mismatch`:** a URI dos Secrets precisa coincidir exatamente com uma URI autorizada no mesmo cliente OAuth Google.
- **Barra da hospedagem cobrindo o app:** publique o `ui.py` atualizado. Para apps públicos, o modo oficial de incorporação pode ser acessado em [skopos.streamlit.app/?embed=true](https://skopos.streamlit.app/?embed=true).

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

Em **Gestão da Plataforma → API do Horus**, disponível para administrador, informe a URL base terminada em `/Horus/api/TServerB2B/`, as credenciais Basic Auth e os códigos de empresa e filial. A ação **Testar conexão** consulta uma amostra do catálogo; **Consultar vendas** busca pedidos faturados e seus itens por período, usando a paginação documentada pelo Horus. Os parâmetros de conexão não sensíveis são salvos no banco; as credenciais ficam na sessão ou podem ser carregadas de `.streamlit/secrets.toml`:

    [horus_api]
    username = "seu_usuario"
    password = "sua_senha"

O app mostra uma prévia antes de importar os registros. Os exemplos públicos dos itens do Horus não incluem custo unitário. Para evitar calcular uma margem fictícia, a importação fica desabilitada quando esse custo não vier na resposta. Confirme com a FMZ qual consulta/campo fornece o custo dos produtos.

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
