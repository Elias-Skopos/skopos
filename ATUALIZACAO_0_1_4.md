# Skopos 0.1.4 — cliente Google incluído e publicação

Preparado em 12/10/2026. O novo cliente desktop é `209016002028-j03s3mtbikstb4ipf3m9jlv616jmbcsc.apps.googleusercontent.com`.

## O que mudou

O instalador desta entrega inclui o JSON do cliente **Aplicativo para computador** fornecido pelo proprietário do projeto. Na primeira abertura e nas atualizações, o iniciador copia essa configuração automaticamente para a pasta privada de dados. Não é necessário importar o arquivo ao fazer login. O iniciador informa que a configuração já está incluída; a opção **Alterar configuração Google** permanece disponível para manutenção.

Instalações existentes adotam o novo identificador público sem trocar o cliente OIDC local, cookie, identidade da instalação ou senha local. Uma configuração Google do cliente antigo é guardada em uma cópia privada antes de aplicar o cliente incluído. Uma configuração importada com o mesmo identificador atual é preservada.

O JSON desktop é um recurso do aplicativo distribuído e pode ser extraído do instalador/programa. Esse modelo foi explicitamente autorizado. Nenhuma senha Google, token pessoal ou segredo do cliente web é incluído. A senha local continua funcionando independentemente do Google.

Se já existe um perfil com senha local, entre por ele e abra **Meu perfil → Gerenciar senha local e Google → Vincular ou confirmar Google**, usando o mesmo e-mail. Isso permite usar os dois métodos no mesmo perfil, com as mesmas empresas e permissões. O sistema exige a vinculação autenticada; informar um e-mail igual não combina contas automaticamente. Esse vínculo não sincroniza dados entre computadores.

## Atalho e navegador

Durante a instalação, deixe selecionado **Criar atalho Skopos que abre no navegador padrão**. O atalho **Skopos** inicia o PostgreSQL privado e o servidor local, aguarda a prontidão e abre a URL configurada no navegador padrão do Windows. Outro clique reutiliza a instância existente.

Não usar apenas um arquivo de URL: após reiniciar o computador, o banco e o servidor precisam ser iniciados. A aplicação web aberta por esse atalho é local; não depende da hospedagem Streamlit. A janela do iniciador deve permanecer aberta durante o uso e oferece **Encerrar Skopos**.

## Como fica o GitHub

O repositório `https://github.com/Elias-Skopos/skopos` guarda o código e os arquivos públicos: módulos Python, estilos, imagens, dependências, testes e documentação. Extraia `Skopos-Codigo-0.1.4.zip` e envie o conteúdo para a raiz de `main`. Não envie somente o ZIP como substituto dos arquivos do app.

Não enviar `.local_auth/`, `.streamlit/secrets.toml`, bancos, backups, dados reais, `.venv/`, `build/` ou `dist/` ao código do repositório. O JSON de credenciais original fica fora do Git e do ZIP público; o compilador recebe seu caminho explicitamente.

O instalador `.exe` e o arquivo `.sha256` são anexados a uma **Release**, não ao código. Para esta versão, use a tag `v0.1.4`. O link previsto é:

https://github.com/Elias-Skopos/skopos/releases/download/v0.1.4/Skopos-Setup-0.1.4-windows-x64.exe

O JSON desktop incluído poderá ser recuperado por quem baixar esse `.exe`. Não confundir esse parâmetro de cliente instalado com credenciais confidenciais de um cliente web ou de usuário.

O Streamlit mantém a página pública de download e demonstração. A entrada existente continua sendo `app.py`, com `[distribution] edition = "public"` nos Secrets. Após publicar, conferir o arquivo e seu checksum, atualize `public_release.json` com versão, URL, SHA256 e `published: true`. Enquanto isso, mantenha o download desativado. Nenhum banco financeiro local é enviado ao GitHub ou sincronizado pela publicação.

## Compilação com Google incluído

O candidato 0.1.4 foi compilado com o JSON incluído e conferido como cliente para computador. Os testes de funcionamento continuam pendentes, conforme a seção abaixo. Arquivos desta entrega:

- `dist/installer/Skopos-Setup-0.1.4-windows-x64.exe`
- `dist/installer/Skopos-Setup-0.1.4-windows-x64.exe.sha256`
- `dist/installer/Skopos-Codigo-0.1.4.zip`

SHA256 do instalador:

```text
4b6771d4af3b83deda28fb716e05fb2412aa7fee2fcecfecfc4905120b7c0504
```

**Somente após validar o funcionamento e publicar os dois arquivos da Release**, substituir o conteúdo de `public_release.json` pelo seguinte e atualizar esse arquivo no GitHub:

```json
{
  "version": "0.1.4",
  "published": true,
  "download_url": "https://github.com/Elias-Skopos/skopos/releases/download/v0.1.4/Skopos-Setup-0.1.4-windows-x64.exe",
  "sha256": "4b6771d4af3b83deda28fb716e05fb2412aa7fee2fcecfecfc4905120b7c0504"
}
```

O código desta entrega mantém `published: false`. A publicação manual no GitHub não altera a instalação local já existente; é necessário executar o novo instalador no computador.

Para recompilar com o cliente incluído:

```powershell
.\.venv\Scripts\python.exe build_installer.py --google-client-json .local_auth/google-desktop-client.json
```

O arquivo deve ter a seção `installed`, o novo ID e seu `client_secret`. O compilador valida o tipo e o ID e inclui somente esses campos, sem copiar outros arquivos privados. Sem esse argumento, o pacote não inclui configuração Google. Use `export_sources.py` para gerar o ZIP público de código; esse exportador exclui o JSON.

## Validação pendente

A versão 0.1.3 passou em 123 testes e no teste de inicialização real. Esses resultados não validam a versão 0.1.4. A execução dos novos testes foi impedida por falha da revisão automática causada pelo limite de uso; a ação não foi executada e não foi considerada insegura.

Antes de distribuir 0.1.4, validar os testes novos de atualização e configuração automática, o autoteste do executável em uma pasta nova e o login Google real. Confirmar ainda o atalho, o navegador padrão e a preservação dos dados ao atualizar a instalação atual. O novo cliente Google não garante sozinho que audiência, usuários de teste e consentimento estejam configurados no Google Cloud.

Para conferir manualmente no computador de uso:

1. Encerre o Skopos pelo iniciador antes de atualizar. Guarde um backup dos dados.
2. Instale `Skopos-Setup-0.1.4-windows-x64.exe`, mantendo selecionada a criação do atalho.
3. Abra **Skopos** pela área de trabalho. Na instalação existente, a abertura é automática; em uma instalação nova, informe o nome e clique em **Preparar e abrir**.
4. Confira se o navegador padrão abre a aplicação local, se o acesso por senha continua disponível e se o Google permite entrar sem importar JSON. Se já usa um perfil local, vincule o Google a ele conforme explicado acima.
5. Confira as empresas e os dados existentes, encerre o iniciador e abra novamente pelo atalho.

Essas verificações ainda não foram executadas nesta entrega. A compilação e a conferência dos arquivos não substituem a validação de funcionamento.
