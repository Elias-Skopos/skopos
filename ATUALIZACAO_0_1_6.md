# Skopos 0.1.6 — acesso e alimentação de dados

Implementação e instalador Windows compilados em 17/10/2026. O executável passou no autoteste em uma pasta nova, sem dados reais. A versão não foi instalada sobre a instalação do usuário nem publicada no GitHub.

## Instalador compilado

- Arquivo: `dist/installer/Skopos-Setup-0.1.6-windows-x64.exe` (121.513.507 bytes).
- Integridade: `dist/installer/Skopos-Setup-0.1.6-windows-x64.exe.sha256`.
- SHA256: `c4c3d0c1ddd62cae52490088a638cb951c609a1c5028b303503a836f15d25512`.
- O pacote mantém o cliente Google Desktop usado no instalador anterior e o mesmo identificador de instalação do produto. Dados pessoais, banco, Secrets e backups ficam fora do pacote.
- Para atualizar, feche o Skopos e execute o instalador. A pasta de dados existente é preservada.
- Para distribuir pelo GitHub, anexe o `.exe` e o `.sha256` à Release `v0.1.6`. O ZIP de código serve para atualizar os arquivos do repositório. A ativação do download no site continua dependendo de publicação e conferência do arquivo; `public_release.json` não foi ativado por esta compilação.

## Correções solicitadas

1. **Cadastro local:** erros aparecem em uma janela de aviso, sem navegar nem apagar nome, e-mail, senha e confirmação. As regras reais ficam visíveis: 12 a 256 caracteres, confirmação idêntica, sem combinação obrigatória de letras/números/símbolos. A validação do servidor continua ativa. Sem JavaScript, o retorno preserva nome e e-mail; senhas nunca são devolvidas no HTML nem gravadas em cookies.
2. **E-mail existente:** cadastro e recuperação oferecem “Voltar ao login”, levando o e-mail preenchido e conservando a autorização de entrada em andamento. Google não cria mais um segundo perfil quando encontra um e-mail local ainda não vinculado.
3. **Recuperação:** “Esqueci minha senha” permite usar um código de recuperação de uso único ou confirmar o Google previamente vinculado. Em “Meu perfil → Gerenciar senha local e Google”, gere o código após confirmar a senha atual ou o Google. Ele aparece uma vez; guarde fora do app. Gerar outro invalida o anterior; usar o código exige gerar outro para o futuro. O banco guarda somente seu hash e bloqueia tentativas repetidas por dez minutos. Não há envio de redefinição por e-mail configurado. Sem código previamente gerado nem Google vinculado, não há redefinição automática. A senha da conta Google é recuperada pelo próprio Google.
4. **Aba Google:** o retorno externo tenta fechar a guia após a confirmação, preservando o retorno à janela original do Skopos. Navegadores podem bloquear `window.close()` em guias abertas pelo sistema; nesse caso, aparece a orientação para fechar manualmente. O fechamento efetivo com uma conta Google real continua dependendo da validação no navegador do usuário.
5. **Home:** favoritos aparecem acima dos indicadores financeiros.
6. **CSV no Windows:** a causa identificada está no diálogo do pywebview 6.2, que oferecia apenas “Todos os arquivos”. O adaptador do Skopos apresenta “Arquivo CSV (*.csv)”, sugere a extensão e mantém a confirmação de substituição. Os downloads do Streamlit já informavam nome `.csv` e tipo `text/csv`. A janela nativa precisa ser conferida no próximo executável Windows.
7. **Sessão:** o provedor local usava 15 minutos, e o app encerrava a sessão quando o token OIDC vencia em uma hora. Agora a sessão de uso assinada e o cookie persistente têm prazo de 30 dias, independente da validade curta do token de protocolo. O usuário ainda pode sair explicitamente. A confirmação Google para alterações sensíveis continua válida por apenas cinco minutos. Cookies antigos do provedor podem exigir uma nova entrada para receber o prazo novo; não é necessário alterar segredos ou recriar contas.
8. **Insights:** a tela explica se falta chave, modelo ou autorização de envio, oferece acesso direto à configuração e preserva a chave durante a navegação da sessão. A geração continua exigindo uma chave Gemini válida, modelo disponível, dados e consentimento. Nenhuma análise real foi enviada a um serviço externo durante os testes.
9. **Gerenciar acesso:** o cookie do provedor permanece disponível; se estiver vencido, a tela pede nova autenticação e retorna à gestão de senha/Google, em vez de enviar à Home.
10. **Lançamentos:** abas distintas para inserção manual, CSV e recorrências. Status, vencimento e pagamento/recebimento podem ser editados na tabela e confirmados juntos. O servidor valida datas, permissão, empresa e alterações concorrentes; um erro cancela o lote inteiro. As ações individuais continuam disponíveis, e o histórico de importações fica abaixo. Em Vendas e estoque, o histórico simplificado também foi movido para baixo.

## Verificação e limites

- Testes usam bancos temporários e dados fictícios; os dados reais da instalação não foram usados.
- Suíte completa: 146 casos, sendo 133 aprovados e 13 de integração PostgreSQL ignorados por falta de banco de homologação configurado; nenhuma falha. Sintaxe e listas de arquivos do empacotamento também foram verificadas.
- Fluxos de senha, CSRF, recuperação, limite de tentativas, vínculo Google, OIDC sem cookies de navegador, persistência da sessão, navegação da configuração de IA e edição de status têm cobertura automatizada.
- Cadastro verificado também em navegador: senhas divergentes e e-mail duplicado abrem o aviso, mantêm os campos e permitem retornar ao login com o e-mail preenchido.
- Executável compilado: autoteste aprovado para PostgreSQL, criação da estrutura, cálculo da Home, servidor, recursos estáticos, descoberta/JWKS da identidade local e renderização do login em WebView2 (`renderer=edgechromium`). Resultado registrado em `build/self-test-0.1.6-ok.json`; somente a pasta de teste foi usada.
- O Google foi simulado nos testes de protocolo. Login Google real, fechamento da guia em cada navegador e o diálogo CSV nativo permanecem como validações manuais do próximo instalador.
- Testes PostgreSQL opcionais exigem `SKOPOS_TEST_DATABASE_URL`; a suíte padrão usa SQLite temporário.
- A nova tabela `identity_recovery` é criada na inicialização e está incluída no migrador PostgreSQL. Novos módulos estão incluídos na lista de arquivos do instalador e da exportação de código.

Para verificar localmente, execute a suíte com o Python do projeto: `python -m unittest discover -s tests`. Se o ambiente restringir o diretório temporário, configure-o para uma pasta gravável; o AppTest também precisa do socket interno de loopback do Python.
