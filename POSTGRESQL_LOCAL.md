# PostgreSQL local do Skopos

Esta instalação usa PostgreSQL 18.6 para Windows x64, em uma pasta privada do projeto. Não depende de serviço de nuvem nem de uma instalação global. O servidor aceita conexões somente de `127.0.0.1:5432`, com autenticação SCRAM por senha. O aplicativo usa `skopos_app`, sem privilégios de superusuário, criação de usuários ou criação de bancos.

## Abrir e usar

Execute **Iniciar Skopos local.cmd**. O iniciador sobe o PostgreSQL se ele estiver parado, faz um backup e abre o Streamlit local. Se o banco ou o backup falhar, ele interrompe a abertura e mostra uma mensagem. Mantenha o terminal aberto durante o uso; fechar o navegador não encerra o aplicativo. Depois de reiniciar o Windows, use novamente esse iniciador.

O login Google continua necessário e depende de internet para autenticar. Esta etapa não é o instalador distribuível nem altera o login para funcionamento totalmente offline.

O atalho desktop disponibilizado dentro do app ainda abre a versão hospedada na web. Para esta instalação, use o iniciador local acima.

## Arquivos privados

| Caminho | Conteúdo |
| --- | --- |
| `.local_postgres/runtime/pgsql/` | Binários oficiais do PostgreSQL. |
| `.local_postgres/data/` | Dados persistentes e configuração do servidor. |
| `.local_postgres/settings.json` | Credenciais locais geradas automaticamente. Não compartilhar. |
| `.streamlit/secrets.toml` | Login Google e conexão do aplicativo. Não compartilhar. |
| `backup_local_postgres/` | Cópia SQLite anterior à migração, backup dos Secrets e arquivos PostgreSQL `.dump`. |

Esses caminhos privados estão ignorados pelo Git. As pastas do banco e de backup têm permissões restritas ao usuário do Windows que preparou a instalação e ao SYSTEM. Não apague nem substitua `.local_postgres/data/` ao atualizar o código. O SQLite original permanece como cópia histórica e deixa de receber alterações do aplicativo após ativar o PostgreSQL.

Os dados desta instalação não são sincronizados com o Streamlit Cloud ou com outros computadores. Uma URL `127.0.0.1` nos Secrets da hospedagem aponta para o servidor hospedado, e não para este PC. Pessoas convidadas precisam acessar a mesma instalação/banco; o convite não transfere dados para outra instalação.

## Comandos de manutenção

Execute no PowerShell, dentro da pasta do projeto:

```powershell
.\.venv\Scripts\python.exe local_postgres.py status
.\.venv\Scripts\python.exe local_postgres.py start
.\.venv\Scripts\python.exe local_postgres.py backup
.\.venv\Scripts\python.exe local_postgres.py verify-backup
.\.venv\Scripts\python.exe local_postgres.py test
```

Para parar somente o banco, feche o aplicativo primeiro e execute:

```powershell
.\.venv\Scripts\python.exe local_postgres.py stop
```

`stop` faz um encerramento controlado; não apaga dados. `start` reutiliza o diretório existente. Os comandos não imprimem senhas ou URLs privadas.

## Backup e recuperação

Cada abertura pelo iniciador faz um backup em formato customizado do PostgreSQL (`.dump`) e registra seu SHA256 em `.sha256`. Também é possível usar **Fazer backup local.cmd** a qualquer momento. Não há tarefa diária agendada nesta etapa; se deixar o aplicativo aberto por vários dias, execute o backup manualmente após alterações importantes.

O comando `verify-backup` verifica o checksum, restaura o arquivo mais recente em um banco temporário próprio, compara todos os registros com o banco ativo e remove somente esse banco temporário. Feche o aplicativo antes da verificação para evitar que novas alterações tornem a comparação diferente. Ele nunca restaura por cima da base real.

Mantenha uma cópia dos backups em outro disco ou local protegido; a cópia neste mesmo computador não protege contra falha do disco. Para recuperar a base real, crie um novo banco vazio, restaure com `pg_restore --no-owner --no-acl --exit-on-error` usando o usuário proprietário e só altere a conexão depois de validar os registros. Não é necessário reinstalar o aplicativo para recuperar um banco.

## Preparar outra instalação

1. Obtenha os binários Windows x64 oficiais na [página PostgreSQL](https://www.postgresql.org/download/windows/) / [EDB](https://www.enterprisedb.com/download-postgresql-binaries). Confira a assinatura/checksum do fornecedor. A versão usada aqui é `postgresql-18.6-5-windows-x64-binaries.zip`.
2. Extraia `pgsql/bin`, `pgsql/lib` e `pgsql/share` para `.local_postgres/runtime/`. O resultado deve conter `.local_postgres/runtime/pgsql/bin/pg_ctl.exe` e `.local_postgres/runtime/pgsql/lib/dict_snowball.dll`.
3. Instale as dependências Python e prepare as pastas privadas com permissões do usuário atual. Execute `local_postgres.py setup`; ele gera senhas, inicializa o diretório de dados e cria `skopos` e `skopos_test`. Se a porta 5432 estiver ocupada, use `setup --port 5433` na primeira preparação.
4. Execute `local_postgres.py test`. O teste usa somente `skopos_test`, com schemas temporários.
5. Feche o aplicativo, escolha o SQLite correto e execute `local_postgres.py migrate --source CAMINHO`. A origem é preservada e o destino precisa estar vazio; não há combinação automática com uma base de outro PC ou do Cloud.
6. Execute `local_postgres.py backup` e `local_postgres.py verify-backup` antes de `local_postgres.py activate`. A ativação preserva os Secrets de autenticação, grava uma cópia anterior e recusa substituir uma conexão diferente já configurada.

`setup` não reinicializa um diretório com dados e não substitui senhas de uma instalação existente. A pasta `.local_postgres/` não deve ser copiada pelo Git para outro computador; cada instalação precisa de preparação própria.

Referências: [initdb](https://www.postgresql.org/docs/current/app-initdb.html), [pg_ctl](https://www.postgresql.org/docs/current/app-pg-ctl.html), [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html), [arquivo de senhas](https://www.postgresql.org/docs/current/libpq-pgpass.html).
