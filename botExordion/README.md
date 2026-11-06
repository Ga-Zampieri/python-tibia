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
| Repetidor | Repete uma macro ou tecla em intervalo fixo, mesmo com o jogo atrás. |
| Alarme | Toca som e para os módulos AFK se a battle list mudar. |
| Sobrevivência | Comer, anti-idle e regras por HP e mana. |
| Rune Maker | Blank rune para a mão, conjura e guarda a runa. |

## Teclas

- `ESC` para tudo, em qualquer janela.
- `Shift+F1` liga e desliga as macros. Útil para digitar no chat se você usa letras como hotkey.
- As hotkeys das macros só disparam com o jogo em primeiro plano.

## Segundo plano

- Macros de runa e puxar item bloqueiam o input físico enquanto rodam (`BlockInput`), para um movimento acidental do mouse não causar uma ação errada. Por isso, cada repetição em segundo plano trava seu mouse por um instante.
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
