# Skopos 0.1.7 — recuperação de senha por e-mail

Compilado em 17/10/2026. Esta versão acrescenta a recuperação da senha local por e-mail à versão 0.1.6, sem alterar a senha do Google. Ainda não foi publicada no GitHub.

## Arquivos da versão

- Instalador: `dist/installer/Skopos-Setup-0.1.7-windows-x64.exe` (121.525.896 bytes).
- Checksum: `dist/installer/Skopos-Setup-0.1.7-windows-x64.exe.sha256`.
- SHA256: `c00b2075e0d4e4fd104cfb8662cd387a8f0a438a83279bcb36ac2afc59fe5d64`.
- Código público: `dist/installer/Skopos-Codigo-0.1.7.zip`.

Feche o aplicativo e instale a atualização sobre a versão atual. O pacote mantém o cliente Google Desktop anterior e preserva os dados fora da pasta do programa. A configuração de envio Gmail ainda precisa ser importada em cada instalação. O download público continua apontando para a versão 0.1.6 já publicada; somente altere `public_release.json` para 0.1.7 depois de publicar e conferir os anexos da nova Release.

## Configurar Gmail ou Google Workspace

1. Na conta que enviará as mensagens, ative a verificação em duas etapas e gere uma **senha de app** para o Skopos em https://myaccount.google.com/apppasswords. Use a senha de app de 16 caracteres, não a senha normal da conta. Algumas contas Workspace dependem da liberação do administrador. Instruções oficiais: https://support.google.com/mail/answer/185833?hl=pt-BR.
2. Copie `gmail-email.json.example` para um arquivo privado chamado `skopos-email.json`, por exemplo em Downloads. Preencha `username` e `from_email` com o mesmo endereço remetente, e `password` com a senha de app. Mantenha `host` como `smtp.gmail.com` e `port` como `587` (STARTTLS) ou `465` (TLS).
3. Abra o aplicativo e use **Skopos → Configurar e-mail Gmail…**. Selecione esse JSON. A configuração é validada e salva privadamente em `%LOCALAPPDATA%\Skopos\Data\.local_auth\email.json`; uma importação inválida não substitui a anterior. Não é necessário reiniciar o servidor para usar a configuração.
4. Depois da importação, remova a cópia de Downloads que contém a credencial ou guarde-a em local seguro. Nunca envie o JSON preenchido ao GitHub ou pelo chat. O modelo `.example` contém somente marcadores e pode ser publicado.

A configuração é por instalação. Para distribuir o instalador para vários computadores, não inclua uma senha SMTP comum no pacote. Um remetente central para todas as instalações exigiria um serviço de envio separado, com autenticação e limites próprios. O login Google do Skopos não concede permissão para enviar e-mails.

Também é possível usar a seção privada `[email]` dos Secrets locais para remetentes SMTP configurados, com `host`, `port`, `username`, `password` e `from_email`. O campo `app_url` continua sendo usado por convites, mas não é necessário para a recuperação: o link é gerado a partir da origem local validada da instalação.

## Usar a recuperação

**Esqueci minha senha → Informe seu e-mail → Enviar link de recuperação.** O sistema envia o link ao endereço do perfil com senha local. Não é preciso ter gerado um código antes. Abra a mensagem no **mesmo computador em que o Skopos está instalado e aberto**, escolha uma nova senha e volte ao aplicativo para entrar. Se reiniciar o app em outro endereço/porta, solicite outro link.

O link é válido por 15 minutos, pode ser usado uma única vez e é invalidado quando outro link é emitido ou a senha é alterada. A identidade e as empresas existentes são preservadas. A redefinição também invalida o código de emergência antigo; gere outro depois de entrar.

As opções de código de emergência e Google previamente vinculado continuam disponíveis. A senha da conta Google é recuperada no próprio Google; a opção de e-mail do Skopos atende perfis que já têm senha local.

## Proteções e verificação

- Tokens aleatórios de 256 bits; apenas o hash é guardado no banco. O token vai no fragmento do link, que não é enviado em requisições HTTP; a tela o remove do endereço após carregar. Aberturas e prévias do e-mail não consomem o token.
- Confirmação da nova senha, limite de tamanho e CSRF validados no servidor. A troca exige o token, ocorre em transação e não autentica o usuário automaticamente.
- Solicitações apresentam a mesma resposta para contas existentes, inexistentes e limitadas. Intervalo de um minuto, máximo de cinco solicitações por e-mail/hora e trinta por instalação/hora.
- Entrega usa TLS e autenticação SMTP em segundo plano. Falhas invalidam o token correspondente e registram somente o código `E01`, sem credenciais, token, e-mail ou resposta bruta do provedor.
- Se o remetente não estiver configurado, a tela explica como configurar e oferece os outros meios de recuperação.
- A configuração real não faz parte do código público nem do instalador. As novas tabelas estão incluídas no migrador PostgreSQL.
- Os testes automatizados usam contas fictícias e SMTP simulado. O envio real depende de configurar o remetente e validar a entrega em uma caixa postal; nenhum e-mail real foi enviado durante o desenvolvimento.
- Suíte completa: 156 testes, com 143 aprovados e 13 integrações opcionais ignoradas. Após sincronizar o download público já publicado, os 13 testes de página pública e recuperação por e-mail também passaram.
- O executável compilado passou no autoteste em pasta nova: PostgreSQL, estrutura, cálculo da Home, servidor, recursos estáticos, identidade local e tela de login em WebView2. Um teste adicional no PostgreSQL temporário validou a troca de senha por token, uso único e preservação da empresa. Resultados em `build/self-test-0.1.7-ok.json` e `build/email-recovery-postgres-ok.json`.

O instalador e a publicação de 0.1.6 permanecem separados desta atualização. Publique 0.1.7 apenas depois de conferir o respectivo instalador e a configuração do remetente.
