# Ferramentas de tradução Pokémon Pokopia PT-BR

Requer Windows, Python 3.12 com Tkinter e um dump próprio da mesma versão do jogo (atualização 2.0.1a). O dump não acompanha este pacote.

Execute python tradutor_pokopia.py para abrir o editor ou python visualizador_texturas.py para abrir o visualizador. Escolha a pasta romfs da atualização quando solicitado. O editor lê LD_C0_R.BIN e LI_C0_R.IDX nessa pasta e salva alterações em traducoes.json. As revisões começam vazias e são criadas ao editar.

O visualizador usa os índices de metadados incluídos e cria sua própria pasta de cache e seu arquivo de classificações. Os índices correspondem à versão do dump indicada. Para gerar miniaturas, obtenha ou compile texc.exe do projeto https://github.com/hearhellacopters/tex_codec (versão 1.8.0, commit ae0d500b7ac52378f18c309e61f3d782637f3b1d) e coloque-o em tools/texc/texc.exe. O executável não acompanha este pacote porque sua licença de redistribuição não foi identificada.
