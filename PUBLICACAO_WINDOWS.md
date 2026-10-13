# Publicação manual — Skopos 0.1.3 para Windows

**Candidato 0.1.4 compilado, com validação pendente:** o novo cliente Google, a inclusão automática do JSON e o checksum atual estão descritos em [ATUALIZACAO_0_1_4.md](ATUALIZACAO_0_1_4.md). Os nomes, checksums e testes abaixo são da entrega anterior 0.1.3 e não devem ser usados para publicar a atualização.

Entrega piloto preparada em 12/10/2026. Repositório: https://github.com/Elias-Skopos/skopos.
Nenhum arquivo foi publicado automaticamente. A configuração pública continua com o download desativado até o instalador estar disponível.

## 1. Atualizar o código no GitHub

Extraia `dist/installer/Skopos-Codigo-0.1.3.zip` em uma pasta separada. Envie **o conteúdo extraído**, preservando os nomes e pastas, para a raiz do repositório na branch usada pelo Streamlit (atualmente `main`). Pelo GitHub, use **Add file → Upload files** e confirme o commit. O ZIP é uma cópia dos arquivos públicos para atualização; subir somente o ZIP não atualiza o aplicativo.

Inclua `.streamlit/config.toml`; no Windows, habilite a exibição de arquivos/pastas ocultos se necessário. O pacote contém um exemplo de Secrets, mas não contém as credenciais reais. Não substitua seus Secrets privados pelo exemplo.

O pacote inclui os módulos de autenticação local, iniciador, página pública e demonstração, estilos, imagens, dependências, testes e documentação. Bancos, dados reais, backups, credenciais, ambiente Python e binários do PostgreSQL não entram nesse ZIP. O `.exe` deve ser enviado às Releases, conforme o passo seguinte.

## 2. Publicar o instalador nas Releases

1. Abra https://github.com/Elias-Skopos/skopos/releases e selecione **Draft a new release**.
2. Crie a tag **v0.1.3**, apontando para o código atualizado em `main`.
3. Use o título **Skopos 0.1.3 — piloto Windows**.
4. Anexe os dois arquivos de `dist/installer/`:
   - `Skopos-Setup-0.1.3-windows-x64.exe` (aproximadamente 115 MB).
   - `Skopos-Setup-0.1.3-windows-x64.exe.sha256`.
5. Nas notas, informe: Windows 10/11 de 64 bits, PostgreSQL privado, acesso somente no computador instalado, conta local e opção Google. Informe também que a instalação começa com uma base vazia e não migra automaticamente os dados atuais.
6. Publique a Release. Para esta entrega, marque **pre-release** para identificar o piloto.
7. Abra o link abaixo sem estar conectado ao GitHub e confirme que o arquivo pode ser baixado. Confira o SHA256 do arquivo baixado antes de habilitar o botão no site.

Link esperado:

https://github.com/Elias-Skopos/skopos/releases/download/v0.1.3/Skopos-Setup-0.1.3-windows-x64.exe

Checksum deste instalador:

```text
ebfe3fba346b03cc8e153dd229aa88a0fe3460054d6106b31d4cef12b59257f5
```

No PowerShell, confira o arquivo baixado com:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "$env:USERPROFILE\Downloads\Skopos-Setup-0.1.3-windows-x64.exe"
```

## 3. Ativar o download

**Somente depois de publicar e conferir o arquivo**, edite `public_release.json` no repositório para conter:

```json
{
  "version": "0.1.3",
  "published": true,
  "download_url": "https://github.com/Elias-Skopos/skopos/releases/download/v0.1.3/Skopos-Setup-0.1.3-windows-x64.exe",
  "sha256": "ebfe3fba346b03cc8e153dd229aa88a0fe3460054d6106b31d4cef12b59257f5"
}
```

Confirme esse commit. Não altere a versão ou o nome do arquivo sem ajustar também a URL e o checksum. Uma nova compilação pode ter outro checksum, mesmo com a mesma versão.

## 4. Trocar a página do Streamlit pela apresentação pública

Antes da troca, preserve quaisquer dados existentes somente na hospedagem, usando o procedimento de backup do banco configurado. Esta mudança não copia dados do Cloud para o computador.

Mantenha `app.py` como entrada do site existente, preservando o endereço `https://skopos.streamlit.app/`. No Streamlit Community Cloud, abra **Settings → Secrets** e acrescente ao final, como uma seção separada:

```toml
[distribution]
edition = "public"
```

Preserve as seções e credenciais existentes. Se `[distribution]` já existir, altere seu campo `edition` em vez de duplicar a seção. Salve e reinicie o app se necessário. O código detecta essa edição antes de carregar banco, usuários ou empresas.

O site terá o padrão visual do login atual e as opções **Baixar para Windows** e **Explorar demonstração**. A demonstração usa dados fictícios gerados em memória e não exige cadastro nem consulta o banco real. Ela oferece Visão geral, Vendas, Estoque, Contas e Curva ABC. Ainda é necessário conferir visualmente o site publicado em computador e celular.

Para um site novo separado, também é possível escolher `online_app.py` como entrada. Nesse caso, a página pública não precisa da seção `[distribution]`.

## Google opcional e atalhos em 0.1.3

A senha local continua disponível sem configurar Google. A janela do iniciador tem **Configurar Google: importar JSON**, e o instalador oferece a tarefa **Criar atalho Skopos na área de trabalho**, selecionada por padrão. O atalho local se chama **Skopos**; o antigo **Skopos Online** abre a hospedagem. No teste desta máquina foi confirmado que `C:\Users\Elias\Desktop\Skopos.lnk` aponta para o executável instalado e que o destino existe.

O cliente Google de computador informado rejeitou a troca sem o parâmetro adicional com `client_secret is missing`. Quando desejar configurar:

1. No Google Cloud → Google Auth Platform → Clientes, baixe o JSON do cliente **Aplicativo para computador**, com ID `209016002028-qahub3vvc1v9gcn31hldv1iu1gb1435m.apps.googleusercontent.com`. Use o cliente desktop, não o cliente web. Referência: https://developers.google.com/identity/protocols/oauth2/native-app.
2. Na janela Skopos, clique em **Configurar Google: importar JSON** e escolha esse arquivo localmente. Não cole suas credenciais no chat nem no GitHub.
3. A importação verifica o tipo e o identificador, salva somente os campos necessários em `%LOCALAPPDATA%\Skopos\Data\.local_auth\google-desktop-client.json` e recusa substituir uma configuração válida por um arquivo inválido.
4. Se o app já estiver aberto, clique em **Encerrar Skopos** e reabra pelo atalho.
5. Se já criou um perfil local e quer manter as mesmas empresas, entre por ele e use **Meu perfil → Gerenciar senha local e Google → Vincular ou confirmar Google**. Use a mesma conta/e-mail; coincidência de e-mail não vincula perfis automaticamente.

Essa configuração é opcional e fica fora do pacote de instalação e do ZIP público. Preserve o arquivo privado ao transferir uma instalação: ele não faz parte dos dados do dump PostgreSQL. O cliente web e as senhas Google não são utilizados por essa importação.

Erros Google agora têm códigos G00–G05, com orientações específicas. O diagnóstico não imprime tokens, credenciais ou a resposta bruta do provedor; os logs de acesso removem parâmetros da URL. Os testes controlados conferiram o envio de `client_secret` no corpo HTTPS, PKCE, assinatura/claims e conclusão do fluxo. Um login Google real ainda depende de configurar o JSON e testar com o usuário.

## Correção de inicialização

O Streamlit inferia modo de desenvolvimento a partir do caminho empacotado, impedindo configurar a porta do servidor. O iniciador agora define modo de produção antes de importar o Streamlit; a linha de comando e a configuração pública também o fixam explicitamente. Erros do processo de servidor vão para o log em vez de abrir uma caixa de diálogo separada no processo filho.

Para atualizar uma instalação 0.1.1 que mostrou esse erro, feche as janelas de erro e use **Encerrar Skopos** no iniciador. Instale 0.1.3 sobre a mesma instalação e abra pelo atalho existente. Não apague `%LOCALAPPDATA%\Skopos\Data`: o nome local, banco e credenciais existentes são reaproveitados.

O autoteste passou a iniciar também o servidor real do pacote em uma base nova, conferir a resposta de prontidão, página HTML, JavaScript e discovery/JWKS do login local, e encerrar os processos de teste sem abrir navegador. Ele não verifica um login Google real nem toda a interação visual.

## Novidades da Home

A Home apresenta ponto de equilíbrio estimado por mês, checklist de até três pagamentos pendentes e entradas/saídas realizadas. O proprietário configura os custos fixos e a margem estimada na própria Home, após mostrar os valores na barra superior. Não há premissas reais pré-preenchidas. A meta usa custos fixos / (margem / 100), não inclui principal de dívidas nem reservas, e fica independente do filtro de período.

A agenda mostra vencidos primeiro e não é limitada ao filtro. Marcar pagamentos e confirmar a data efetiva dá baixa em Contas; colaboradores apenas consultam. Entradas/saídas usam o período selecionado e os registros recebidos/pagos, sem somar vendas ainda não recebidas. O instalador 0.1.0 anterior não contém essas mudanças; use o pacote 0.1.3.

## 5. Instalar e usar

1. Execute o instalador no Windows 10/11 de 64 bits. Python e PostgreSQL vão no pacote; não precisam ser instalados separadamente.
2. Abra **Skopos** pelo atalho da área de trabalho ou do menu Iniciar.
3. Na primeira abertura, informe o nome usado para gerar o endereço local, por exemplo `skopos.minha-livraria.localhost`. Esse nome pertence à instalação; alterar o nome da empresa dentro do app não altera o endereço. Prefira Chrome ou Edge no Windows.
4. O iniciador prepara um PostgreSQL privado, escolhe portas disponíveis e abre o aplicativo no navegador. Depois, crie um perfil local ou entre com Google e cadastre a empresa.
5. Para vincular o Google a um perfil local, entre primeiro nesse perfil e use **Meu perfil → Gerenciar senha local e Google**. A vinculação exige autenticação Google e o mesmo e-mail verificado; não combina automaticamente dois perfis já existentes. Quem entrou primeiro pelo Google pode criar uma senha local nessa mesma área.
6. Use **Encerrar** na janela do iniciador ao terminar. Fechar apenas a guia do navegador mantém o app em execução.

A senha local permite entrar sem internet. Google, Horus, IA e envio de e-mail precisam das conexões e configurações correspondentes. Um e-mail apenas informado no cadastro local não é verificado; para aceitar convites por e-mail, vincule uma identidade Google verificada. Os dois métodos vinculados usam o mesmo perfil, empresas e permissões; não sincronizam senhas ou dados entre computadores.

Dados e configurações ficam em `%LOCALAPPDATA%\Skopos\Data`, separados do programa em `%LOCALAPPDATA%\Programs\Skopos`. Backups automáticos ficam na pasta `backup_local_postgres` dentro dos dados. A desinstalação foi configurada para preservar a pasta de dados. Não apague essa pasta para atualizar. Transferência dos dados antigos, restauração assistida e recuperação de senha esquecida ainda precisam de um procedimento específico; não há recuperação por e-mail nesta entrega.

## Validação e limites do piloto

- 123 testes passaram, incluindo PostgreSQL, autenticação, página pública e Home. Na Home foram conferidos ponto de equilíbrio, baixa transacional de pagamentos, datas de caixa, ocultação de valores e permissões.
- O executável 0.1.3 passou no teste de inicialização em uma pasta nova: PostgreSQL, estrutura, cálculo de equilíbrio, servidor real, página HTML, JavaScript e discovery/JWKS locais foram conferidos. Confirmou base vazia e encerrou seus processos de teste, sem abrir navegador nem usar o banco real desta máquina.
- Ainda falta validar o instalador em um Windows limpo, o fluxo visual completo, login Google real, reinício do computador, atualização, reinstalação e desinstalação. Os testes de Google validam o protocolo com respostas controladas, não uma entrada real na conta Google.
- O cliente Google para computador informado foi incluído como identificador público. Se o projeto Google estiver em teste, autorize os usuários de teste no Google Auth Platform. O segredo do cliente web não é distribuído.
- O instalador ainda não tem assinatura digital. Distribuição comercial e atualização automática estão no backlog.

## Recompilar

No Windows x64, instale as dependências fixadas em `requirements-desktop.lock` e o compilador Inno Setup. Obtenha o arquivo oficial PostgreSQL usado no projeto; `build_installer.py` verifica o SHA256 do arquivo e compara os binários com ele. O ZIP de código não inclui essas ferramentas nem o arquivo PostgreSQL.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.lock
.\.venv\Scripts\python.exe build_installer.py --inno "C:\caminho\Inno Setup 6\ISCC.exe"
```

Os caminhos alternativos do PostgreSQL podem ser informados com `--postgres-runtime` e `--postgres-archive`. O resultado fica em `dist/installer`, e a URL/checksum candidatos ficam em `build/release-candidate.json`. O processo não habilita nem publica o download automaticamente.
