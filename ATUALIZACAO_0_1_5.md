# Skopos 0.1.5 — janela própria e contraste da demo

Atualização preparada em 13/10/2026. Os arquivos locais precisam ser publicados para atualizar o site hospedado.

O aplicativo Windows abre em uma única janela redimensionável, com pywebview 6.2.1 e WebView2. A mesma janela apresenta a preparação inicial e depois o painel. Não é necessário manter um iniciador separado aberto. Fechar o Skopos encerra o servidor desta execução e o PostgreSQL da instalação; dados e backups são preservados. Abrir novamente o atalho durante o uso reativa a janela existente.

A consulta `whoami` agora usa `CREATE_NO_WINDOW`, assim como `icacls`, os utilitários PostgreSQL e o servidor. O executável continua sendo compilado com `--windowed`. Os comandos de manutenção executados manualmente continuam disponíveis no terminal.

O acesso por senha local permanece dentro da janela. O Google abre o navegador somente durante a autenticação. A janela aguarda o resultado e continua automaticamente, mantendo PKCE, validação de assinatura/nonce e vinculação à sessão que iniciou o acesso. O menu **Skopos → Configurar Google** permite importar as credenciais do cliente para computador. Downloads CSV e seleção de arquivos continuam disponíveis no painel.

Na demonstração pública, tabelas, calendários, controles e avisos usam o tema nativo do Streamlit. Foram definidos temas claro e escuro, paleta mais legível para gráficos no escuro e uma variante do logo para esse fundo. A demo continua usando somente dados fictícios, sem consultar o banco privado.

## Usar a atualização

Execute `dist/installer/Skopos-Setup-0.1.5-windows-x64.exe` para atualizar a instalação. Feche a versão anterior antes de instalar. O pacote usa a configuração Google incluída no candidato anterior. Os dados permanecem em `%LOCALAPPDATA%\Skopos\Data`. Entre novamente na janela própria, pois ela possui uma sessão separada da sessão do navegador; use o mesmo perfil para acessar suas empresas existentes.

O Windows precisa do [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/). Se estiver ausente, o app informa o requisito, sem usar o antigo motor Internet Explorer. A detecção segue a [documentação Microsoft](https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution). O runtime não está incluído neste instalador.

Para atualizar a demo online, extraia `dist/installer/Skopos-Codigo-0.1.5.zip` e publique seu conteúdo na raiz do repositório usado pelo Streamlit, incluindo `.streamlit/config.toml` e os novos arquivos em `assets`. O ZIP de código não contém os dados ou Secrets privados. Os arquivos `.sha256` acompanham os dois pacotes. O download público permanece desativado até a publicação manual da Release.

## Validação

A suíte executou 134 testes: 121 passaram e 13 integrações opcionais não foram executadas; os 13 testes da demo e identidade foram repetidos após o ajuste final dos gráficos e passaram. Foram verificados acesso público sem banco privado, limites da ponte nativa, encerramento durante a preparação e retorno Google vinculado à janela original. A conferência visual validou tabelas e gráficos e a alternância imediata claro/escuro. A janela WebView2 real também foi exercitada em uma instalação temporária: preparação, login incorporado, abertura Google simulada, reativação e encerramento do servidor. O executável empacotado passou no autoteste em pasta nova, com `webview=ok` e `renderer=edgechromium`, sem dados reais. O autoteste agora renderiza a tela de login em uma WebView2 oculta, além de testar PostgreSQL, servidor, recursos estáticos e identidade local.

O Google real e uma instalação em Windows limpo ainda precisam ser conferidos. Não houve publicação automática nem migração dos dados deste projeto para a edição instalada.
