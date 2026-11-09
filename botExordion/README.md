# Exordion

Qualidade de vida para Tibia 7.4 em OTservs, no Windows 10/11: hotkeys de runa, treino AFK, pesca e rotinas de manutenção. Confira as regras do seu server antes de usar, porque muitos proíbem macros.

## Instalação

1. Instale o Python 3.12 ou superior.
2. Execute `install.bat`. Ele instala as dependências e cria o atalho `app.bat.lnk` com os caminhos da sua máquina.

## Como abrir

Use o atalho `app.bat.lnk`. Ele abre direto pelo `pythonw`, sem terminal, e como administrador, que é exigido pelo `BlockInput`.

O atalho não vai para o git. Em outro computador, ou se mover a pasta do projeto, execute `install.bat` de novo para recriá-lo.

Para ver a saída no terminal, use `run.bat`. Os erros ficam em `logs/exordion.log`, e a tela Ajustes abre a pasta.

## Módulos

| Módulo | O que faz |
|---|---|
| Treino | Ataca pela battle list, nos modos Summon e Normal. |
| Pesca | Pesca em segundo plano. Não bloqueia seu mouse. |
| Macros | Runa normal, self use e puxar item por hotkey. |
| Loot | Com o loot aberto, cada aperto do atalho pega os itens aprendidos, rola a janela atrás do resto, abre as bags aprendidas, fecha a janela e termina. |
| Repetidor | Repete uma macro ou tecla em intervalo fixo, mesmo com o jogo atrás. |
| Alarme | Toca som e para os módulos AFK se a battle list mudar. |
| Sobrevivência | Comer, anti-idle e regras por HP e mana. |
| Rune Maker | Blank rune para a mão, conjura e guarda a runa. Para e avisa quando as blanks acabam. |

## Teclas

- `ESC` para tudo, em qualquer janela.
- Cada módulo pode ter um atalho para ligar e desligar, com Ctrl, Alt e Shift, definido em Ajustes > Atalhos. Eles funcionam em qualquer janela, menos o do Loot, que exige o jogo na frente, e ficam salvos no perfil.
- Por padrão, `Shift+F1` liga e desliga as macros. Útil para digitar no chat se você usa letras como hotkey.
- As hotkeys das macros só disparam com o jogo em primeiro plano.

## Segundo plano

- Em Ajustes > Perfil dá para renomear, exportar e importar perfis. O arquivo leva toda a configuração, inclusive o título da janela do jogo, que costuma ter o nome do personagem; importar sempre cria um perfil novo.
- A lista de itens e bags do Loot pode ser exportada e importada na tela do Loot. O arquivo leva os desenhos, que valem para o mesmo cliente, e o número da BP de cada item.
- O Loot pode separar os itens em várias BPs: adicione destinos na tela do Loot e clique no desenho de um item para escolher a BP dele.
- Macros de runa, puxar item e Loot bloqueiam o input físico enquanto rodam (`BlockInput`), para um movimento acidental do mouse não causar uma ação errada. Por isso, cada repetição em segundo plano trava seu mouse por um instante.
- Com o jogo na frente, a runa usa o cursor real. Com o jogo atrás, só alcançável pelo Repetidor ou pelas regras, usa mensagens.
- Se o puxar item não funcionar no seu cliente, desligue "Arrastar em segundo plano" em Macros.
- A leitura da tela tenta `PrintWindow`, que funciona com o jogo coberto. Se o cliente não responder, o bot lê a tela, e o jogo precisa ficar visível.

## Perfis

Tudo que você configura é salvo automaticamente em `config/profiles/`, um arquivo por perfil. As posições são relativas à janela do jogo, então movê-la não quebra nada. Na primeira execução, o `assets/runa_mappings.json` antigo é importado.

## Desenvolvimento

- `src/bot.py`: toda a lógica, sem dependência de interface.
- `src/ui.py`: interface em CustomTkinter.
- `src/action_manager.py`: envio de input para a janela.
- `src/battle_vision.py`: leitura de pixels.

Rode os testes com `python -m pytest -q`.
