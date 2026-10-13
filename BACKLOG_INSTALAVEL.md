# Backlog — Skopos instalável

Atualizado em 13/10/2026. Não há execução automática nem publicação externa realizada.

## Objetivo e decisões

Distribuir o Skopos para Windows 10/11 x64, com Python e PostgreSQL privados no pacote. Acesso somente no computador instalado, em janela própria com pywebview/WebView2; instalação por usuário, sem exigir um terminal aberto. Endereço configurado no primeiro uso, como `skopos.empresa.localhost`, sem domínio registrado ou DDNS. Senha local e Google podem ser vinculados ao mesmo perfil; senhas e dados não são sincronizados entre computadores.

Atualização 0.1.5: janela única implementada, comandos auxiliares ocultos e contraste da demo corrigido. O navegador é usado somente para autenticação Google e links externos. Consulte [ATUALIZACAO_0_1_5.md](ATUALIZACAO_0_1_5.md) para os testes e limites atuais; itens referentes à abertura no navegador abaixo descrevem versões anteriores.

A página online apresenta o produto, permite baixar o instalador e oferece demonstração anônima com dados fictícios. O visual reutiliza a página de login atual. A publicação será manual no repositório Elias-Skopos/skopos e nas suas Releases.

## Implementado

- [x] PostgreSQL local de desenvolvimento, migração da origem SQLite, backups e verificação de recuperação em destino temporário.
- [x] Autonomia de importação: vendas diárias e financeiro, saldo inicial, despesas recorrentes, disponibilidade dos dados, exemplos e modelos CSV brasileiros (DD-MM-AAAA, vírgula decimal e separador ponto e vírgula).
- [x] Primeiro acesso com empresas, criação e convites; Empresa separada de Meu perfil; proprietário e colaborador; múltiplos convites por e-mail.
- [x] Excluir empresa somente como proprietário, com confirmação pelo nome e aceite, verificação atual da permissão e cópia transacional de recuperação. Recuperar somente como proprietário que excluiu; preservação de usuários e outras empresas.
- [x] Curva ABC imediatamente depois de Contas na navegação e nos atalhos.
- [x] Separação entre programa e dados em `%LOCALAPPDATA%\Programs\Skopos` e `%LOCALAPPDATA%\Skopos\Data`; permissões privadas de pasta.
- [x] Runtime PostgreSQL oficial verificado contra arquivo e checksum, credenciais exclusivas por instalação, inicialização vazia somente no primeiro uso e escolha de portas disponíveis.
- [x] Autenticação individual OIDC, senhas Argon2, bloqueio temporário por tentativas inválidas, CSRF, PKCE, nonce e códigos de uso único.
- [x] Google desktop com retorno loopback e vinculação autenticada ao perfil existente. Não vincular por simples coincidência de e-mail; preservar identidade Google, empresas e permissões. Senha local independente; segredos web atuais não distribuídos.
- [x] Identidades, hashes e vínculos incluídos na estrutura e nos processos de migração/backup PostgreSQL.
- [x] Iniciador gráfico, abertura após prontidão da própria instância, reutilização da instância em outro clique e encerramento dos processos próprios.
- [x] Primeira configuração do nome local e segredos OIDC gerados por instalação. Dados atuais não são migrados automaticamente.
- [x] Empacotamento PyInstaller e instalador Inno Setup, dependências fixadas, ícone e atalhos da área de trabalho/menu Iniciar.
- [x] Atalho para download dentro do app retirado; instalador cria atalhos locais.
- [x] Código mantém dados/configurações existentes em novas aberturas, faz backup antes da atualização da estrutura e não configura exclusão da pasta de dados na desinstalação. Validação completa de atualização/desinstalação permanece pendente.
- [x] Instalador piloto 0.1.0 gerado. Executável empacotado passou na preparação de PostgreSQL e estrutura do banco em pasta nova, sem usar a base real.
- [x] Página pública com download condicionado a uma Release publicada e checksum; demonstração sem login e sem acesso ao banco real. A opção de empresa Demo continua retirada da edição protegida.
- [x] Pacote de código público e guia para publicação manual. Consulte [PUBLICACAO_WINDOWS.md](PUBLICACAO_WINDOWS.md).
- [x] 104 testes de regressão passaram; posteriormente sete verificações focadas passaram, incluindo uma verificação adicional de identidade Google. Testes de protocolo Google usam respostas controladas.

## Home financeira — atualização 0.1.1

- [x] Três blocos principais antes dos Favoritos: equilíbrio mensal estimado, checklist de até três pagamentos e entradas/saídas realizadas.
- [x] Custos fixos/margem configurados por empresa e editáveis somente pelo proprietário; cálculo decimal e tratamento de margem zero/negativa.
- [x] Pagamentos pendentes ordenados por vencimento, incluindo atrasados primeiro; baixa pelo proprietário com data efetiva, transação e verificação de permissão no servidor.
- [x] Filtro de período aplicado somente às entradas/saídas; meta mensal e agenda permanecem independentes.
- [x] Ocultação de valores respeitada; nenhum dado real ou premissa ilustrativa inserido automaticamente.
- [x] 116 testes passaram, incluindo PostgreSQL, interação da Home, isolamento de empresas e falhas na baixa sem gravação parcial.
- [x] Executável 0.1.1 validado em pasta nova: PostgreSQL, estrutura do banco e importação/cálculo do módulo financeiro empacotado passaram.
- [ ] Validar visualmente a Home no navegador em computador e celular durante o piloto.

## Correção de inicialização — 0.1.2

- [x] Desativar a inferência de modo de desenvolvimento do Streamlit em caminhos empacotados, antes dos imports e também na configuração/linha de comando.
- [x] Preservar o modo de diagnóstico do processo filho ao chamar o CLI, para registrar erros no log sem caixa de diálogo do filho.
- [x] Ampliar o autoteste com servidor real, página e JavaScript, readiness e discovery/JWKS do provedor local, em dados próprios temporários e sem navegador.
- [x] 118 testes de regressão passaram, incluindo PostgreSQL e as verificações do modo de produção.
- [x] Executável final 0.1.2 passou no teste ampliado: PostgreSQL, estrutura, Home, servidor HTTP, página/JavaScript e discovery/JWKS locais. Os processos de teste foram encerrados, sem abrir navegador ou usar dados reais.

## Google opcional e atalhos — 0.1.3

- [x] Diagnóstico com o cliente público confirmou rejeição por ausência de `client_secret` na troca; código corrigido para cliente desktop com parâmetro no corpo HTTPS e PKCE preservado.
- [x] Importação do JSON desktop pela janela do iniciador, com conferência do tipo/ID, armazenamento privado e preservação da configuração anterior em falhas. Cliente web recusado.
- [x] Sem JSON, Google mostra orientação de configuração e a senha local continua disponível. Usuário decidiu configurar Google depois.
- [x] Códigos de diagnóstico seguros, sem imprimir resposta bruta, tokens ou credenciais; filtro de logs de acesso omite parâmetros da URL.
- [x] Atalho local existente conferido na área de trabalho e destino confirmado. Instalador torna sua criação uma tarefa visível e selecionada por padrão.
- [x] 123 testes passaram, incluindo callback Google com transportes controlados, importação de credenciais, proteção de logs e regressão PostgreSQL.
- [x] Executável 0.1.3 passou na inicialização real em dados novos: PostgreSQL, Home, servidor, página/JavaScript e endpoints locais.
- [x] Receber e validar o JSON desktop fornecido pelo usuário para inclusão na atualização 0.1.4.
- [ ] Validar login/vinculação Google reais; não realizados nesta entrega.

## Pendências antes de sair do piloto

- [x] Preparar atualização 0.1.4 para o novo cliente Google, inclusive instalações existentes, sem mudar credenciais OIDC locais.
- [x] Preparar inclusão explícita do JSON desktop autorizado no instalador e instalação automática na pasta privada; manter JSON fora do código GitHub/ZIP público.
- [x] Compilar o candidato 0.1.4 com o JSON autorizado, a mensagem de configuração incluída no iniciador e checksum próprio; validação de funcionamento permanece pendente.
- [x] Documentar atalho que inicia banco/servidor e abre a aplicação web no navegador padrão, e separar repositório de código de Releases.
- [ ] Validar a versão 0.1.4: testes e autoteste do executável continuam pendentes após falha da revisão automática por limite de uso. Nenhum resultado anterior deve ser apresentado como validação dessa versão.

- [ ] Publicar manualmente o instalador e checksum nas Releases; conferir download anônimo e integridade antes de ativar `public_release.json`.
- [ ] Atualizar o código no GitHub e converter o site para a edição pública, preservando previamente os dados exclusivos do Cloud.
- [ ] Conferir visualmente site publicado, demonstração e fluxo completo em computador/celular.
- [ ] Testar o instalador em um Windows limpo sem Python/PostgreSQL: primeiro uso, abertura do navegador, fechamento, segundo clique, atalhos e permissões sem administrador.
- [ ] Fazer login Google real com o cliente desktop informado e confirmar vinculação, senha local, logout e isolamento de empresas. Conferir configuração de usuários de teste no Google quando aplicável.
- [ ] Testar importações, relatórios, persistência após reiniciar o Windows, portas ocupadas e caminhos com espaços/acentos na edição empacotada.
- [ ] Testar atualização, reinstalação e desinstalação com preservação dos dados em máquina de teste.
- [ ] Preparar transferência da instalação atual para a edição instalada com backup e validação do destino; nunca copiar credenciais da máquina no instalador.
- [ ] Oferecer backup, recuperação e transferência para outro computador por interface/utilitário acessível; definir retenção, destino externo e frequência durante uso prolongado.
- [ ] Definir recuperação de senha local esquecida. Não há recuperação por e-mail implementada; vínculo Google permite acesso enquanto disponível.
- [ ] Definir atualização distribuída e procedimento de recuperação de falhas; avaliar assinatura digital e licenças das ferramentas para comercialização.
- [ ] Definir retenção e expurgo definitivo separados para as cópias de empresas excluídas. Hoje a cópia permanece no mesmo banco; backup externo continua necessário.

## Fora desta entrega

Sincronização entre computadores, acesso remoto da equipe, macOS/Linux, cobrança/licenciamento comercial e operação integral sem internet (Google, Horus, IA e e-mail continuam dependendo das conexões correspondentes).

## Critério de conclusão

Uma pessoa em um Windows compatível consegue baixar, instalar, abrir pelo atalho, cadastrar seu perfil/empresa e usar sem configurar ambiente técnico. Persistência, atualização, backup e recuperação precisam estar validados em instalação independente. O instalador gerado ainda é um piloto até concluir as verificações pendentes acima.
