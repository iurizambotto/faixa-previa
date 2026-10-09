# Faixa Prévia (nome provisório)

Site estático de uma página com a proposta de um simulador e diagnóstico do IEG-M (Índice de Efetividade da Gestão Municipal, do Tribunal de Contas do Estado de São Paulo) para prefeituras paulistas.

Iniciativa independente, sem vínculo com o TCESP. Usa só dados públicos. As telas da página são simulações.

## Estrutura

```
index.html                 página única, navegação por âncoras
assets/css/style.css       estilos, tema claro e escuro por tokens
assets/js/main.js          dicas dos gráficos, simulações "e se", troca de tema
assets/fonts/              fontes servidas pelo próprio site, com as licenças OFL
assets/img/                diagrama de arquitetura em SVG (horizontal e vertical)
data/faixas_all.json       cópia das faixas oficiais por município, 2014 a 2024
data/media_estadual_por_indice_2014_2024.json   cópia da média estadual por índice
data/retrato_estado.json   agregados usados nos gráficos do estado
data/media_estadual.json   médias por índice e média ponderada
data/exemplo_suzano.json   histórico de Suzano e vizinhos do Alto Tietê
tools/build.py             gera os agregados, os gráficos e o diagrama
.nojekyll                  desliga o Jekyll no GitHub Pages
qa/                        capturas de tela da revisão visual (não precisa ser publicada)
```

Não há etapa de build para publicar. Os gráficos já estão escritos dentro do `index.html` e a página funciona sem internet, sem bibliotecas externas e sem fontes de terceiros.

## Testar localmente

```bash
cd landing
python3 -m http.server 8000
```

Abrir `http://localhost:8000` no navegador. Abrir o `index.html` direto do disco também funciona, mas o servidor local reproduz melhor o GitHub Pages.

## Regerar números e gráficos

Quando os arquivos de `data/faixas_all.json` ou `data/media_estadual_por_indice_2014_2024.json` mudarem:

```bash
cd landing
python3 tools/build.py --check   # só confere os números de referência
python3 tools/build.py           # confere, grava data/*.json derivados, reescreve os blocos gerados do index.html e os SVG
```

O script usa só a biblioteca padrão do Python 3.11 ou mais novo. Ele reescreve apenas o que fica entre os marcadores `<!-- gerado:NOME -->` e `<!-- /gerado:NOME -->` do `index.html`; o resto da página é editado à mão. Se um número de referência divergir, o script para com erro e não grava nada.

## Publicar no GitHub Pages

1. Criar um repositório novo no GitHub, com a branch `main`.
2. Escolher onde a página fica:
   - **Raiz do repositório**: copiar o conteúdo desta pasta para a raiz do repositório.
   - **Pasta `docs/`**: copiar o conteúdo desta pasta para `docs/` no repositório.
3. Fazer o commit e o push para `main`.
4. No GitHub, abrir **Settings > Pages**. Em **Build and deployment**, escolher **Deploy from a branch**, a branch `main` e a pasta `/ (root)` ou `/docs`, conforme o passo 2. Salvar.
5. Em alguns minutos a página fica disponível em `https://<usuario>.github.io/<repositorio>/`.

Todos os caminhos da página são relativos, então ela funciona tanto na raiz quanto em `docs/` e também em um subcaminho do GitHub Pages.

Antes de publicar:

- A pasta `qa/` tem cerca de 9 MB de capturas de tela e não é usada pela página. O `.gitignore` desta pasta já a deixa fora do repositório.
- A página tem `<meta name="robots" content="noindex">` porque o nome ainda é provisório. Remover essa linha do `index.html` quando a página puder aparecer em buscadores.
- Não há imagem de compartilhamento (`og:image`). Ela pede uma URL absoluta, que só existe depois de publicar.

## Fontes

As fontes Bricolage Grotesque, Atkinson Hyperlegible Next e IBM Plex Mono estão em `assets/fonts/`, no subconjunto latino, sob a SIL Open Font License; os textos das licenças estão na mesma pasta.

As fontes dos dados e das regras do índice estão listadas na própria página, na seção "Fontes verificadas (2026-10-09)".
