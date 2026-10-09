# Persistência no PostgreSQL

O suporte foi preparado. Criar o banco, configurar a conexão e validar o serviço são etapas necessárias para ativá-lo. Nenhum serviço externo foi criado ou recebeu dados nesta alteração.

1. Crie um banco PostgreSQL em um serviço de sua escolha. Use a conexão fornecida pelo serviço, preferencialmente com TLS (`sslmode=require`), e um usuário com permissão para criar e alterar as tabelas do app. Mantenha a URL privada.
2. Instale as dependências locais: `pip install -r requirements.txt`.
3. Antes de conectar o app ao banco vazio, decida quais dados deseja conservar. A migração copia empresas, acessos, convites, lançamentos, orçamento, vendas, estoque, configurações e histórico de importações. Ela não une bancos do PC e do Cloud. Caso a versão do Cloud tenha dados próprios, exporte seu SQLite na hospedagem antes de reiniciar ou migrar; os CSVs de relatórios não substituem esse backup completo.
4. Confira a origem sem enviar ou alterar dados:

```powershell
.\.venv\Scripts\python.exe migrate_postgres.py --source .\livraria.db
```

5. Para copiar para um PostgreSQL **vazio**, defina `SKOPOS_DATABASE_URL` no ambiente do terminal, com a conexão privada, e execute:

```powershell
.\.venv\Scripts\python.exe migrate_postgres.py --source .\livraria.db --apply
```

O migrador lê o SQLite em modo somente leitura, cria uma cópia temporária, atualiza essa cópia para o esquema atual e preserva IDs. A inserção ocorre em uma transação, com bloqueio das tabelas e conferência das contagens; falhas revertem as inserções. Tabelas vazias podem ser criadas no destino durante a preparação. Um destino com dados é recusado. Faça a migração antes de abrir o app nesse destino; mantenha o arquivo SQLite original como backup.

6. No Streamlit Cloud, em Settings → Secrets, acrescente ao bloco de autenticação já configurado:

```toml
[database]
url = "postgresql://USUARIO:SENHA@HOST:5432/BANCO?sslmode=require"
```

Substitua pelos dados do serviço diretamente no painel de Secrets. Caracteres especiais no usuário/senha precisam estar codificados como exigido pela URL do provedor. Não salve a URL real no arquivo de exemplo ou no Git.

7. Reinicie o app. A página Vendas e estoque informa **Banco em uso: PostgreSQL** no histórico. Confira o login, as empresas, as contagens e uma importação/exclusão de teste na empresa de homologação. Reinicie o app novamente e confirme que os registros permanecem. O banco original local não é modificado pela migração.

Para compartilhar os mesmos dados no PC, configure a mesma `[database].url` em `.streamlit/secrets.toml` local. Uma URL configurada com erro interrompe o app; ele não grava automaticamente em SQLite como alternativa. Sem URL externa configurada, permanece em SQLite local.

Ative backups e retenção no serviço PostgreSQL; persistência externa não substitui uma política de backup. O código e a simulação do migrador foram verificados localmente; a conexão, permissões e execução da migração real devem ser validadas depois do provisionamento.

Referências: [persistência no Community Cloud](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data), [Secrets no Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings), [driver Psycopg](https://www.psycopg.org/psycopg3/docs/).

## Teste de integração depois de criar o serviço

Opcionalmente, configure `SKOPOS_TEST_DATABASE_URL` com uma conexão de homologação e execute `python -m unittest discover -s tests -v -k postgres`. O teste cria um schema temporário próprio, verifica criação de empresas, convites, importação, orçamento e isolamento nas exclusões, e remove somente esse schema ao terminar. Exige permissão para criar schemas. Sem essa variável, o teste de integração é ignorado; os testes locais não fazem conexão externa.
