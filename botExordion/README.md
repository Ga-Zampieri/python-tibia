# Exordion 7.4 Pro

Aplicação desktop para automatização de Tibia 7.4 em Windows 10/11, com foco em segurança, coordenação de entrada, macros e treinamento. Esta versão preserva a base do projeto original (`botExordion`) e acrescenta uma arquitetura mais robusta para entrada, coordenadas, persistência, testes e empacotamento.

## Visão geral

- Entrada Win32 via `SendInput` e `ctypes`.
- Modelo lógico de coordenadas independente do cursor físico.
- Motor de macros personalizáveis.
- Backend simulado para testes e validação automática.
- Persistência em SQLite para perfis e regras.
- Estado explícito para treinamento com slimes.
- Infraestrutura de benchmark e diagnóstico.

## Requisitos

- Windows 10 ou Windows 11 64 bits.
- Python 3.12 ou superior.
- Biblioteca `pywin32` para APIs nativas do Windows.

## Instalação

1. Crie um ambiente virtual: `python -m venv .venv`
2. Ative o ambiente: `.venv\Scripts\activate`
3. Instale dependências: `pip install -r requirements.txt`
4. Instalar tesseract: `https://tesseractocr.org/pt/`
5. Adicioná-lo ao path windows: `C:\Program Files\Tesseract-OCR\`
6. Execute a aplicação: `executar.bat.lnk`, que basicamente roda run.bat como adm.

## Execução

- `python app.py --demo`: executa a validação rápida de integração.
- `python app.py --gui`: inicia a interface básica local.
- `pytest -q`: roda a suíte automatizada.

## Limitações

- `SendInput` move o cursor global do sistema e não cria um mouse virtual independente.
- Reconhecimento visual em ambientes reais depende da janela ativa, DPI e renderização do cliente.
- Treinamento automático exige validação com o cliente real e perfil específico do servidor.

## Desenvolvimento

Estrutura principal:

- `src/coordinates.py`: coordenadas, DPI e conversão.
- `src/input_controller.py`: backend nativo de entrada.
- `src/backend.py`: backend simulado.
- `src/macro_engine.py`: motor de macros.
- `src/persistence.py`: SQLite.
- `src/training.py`: máquina de estados.
- `src/hotkeys.py`: gestão de atalhos.
- `tests/`: testes automatizados.

## Benchmark

Os benchmarks estão disponíveis via teste e logging estruturado. O cabeçalho básico compara latência e evento por segundo, sempre com medidas reais e registradas.
