from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple

from .battle_list_selector import BattleListRow, BattleListSnapshot, SafeBattleListTargetSelector, SelectorState


class TrainingState(str, Enum):
    INATIVO = "INATIVO"
    CALIBRANDO = "CALIBRANDO"
    IDENTIFICANDO_ALVO = "IDENTIFICANDO_ALVO"
    TREINANDO = "TREINANDO"
    AVALIANDO_CRIATURAS = "AVALIANDO_CRIATURAS"
    TROCANDO_EQUIPAMENTO = "TROCANDO_EQUIPAMENTO"
    RECUPERANDO_ESTADO = "RECUPERANDO_ESTADO"
    PAUSADO = "PAUSADO"
    ERRO = "ERRO"


@dataclass
class TrainingDecision:
    can_attack: bool
    protected_index: Optional[int]
    eligible_targets: Tuple[int, ...]
    reason: str


class TrainingStateMachine:
    def __init__(self) -> None:
        self.state = TrainingState.INATIVO
        self.selector = SafeBattleListTargetSelector(min_confidence=0.8, required_stable_captures=2)
        self.last_snapshot: Optional[BattleListSnapshot] = None

    def start(self) -> TrainingState:
        self.state = TrainingState.CALIBRANDO
        return self.state

    def identify_target(self) -> TrainingState:
        self.state = TrainingState.IDENTIFICANDO_ALVO
        return self.state

    def train(self) -> TrainingState:
        self.state = TrainingState.TREINANDO
        return self.state

    def pause(self) -> TrainingState:
        self.state = TrainingState.PAUSADO
        return self.state

    def recover(self) -> TrainingState:
        self.state = TrainingState.RECUPERANDO_ESTADO
        return self.state

    def error(self) -> TrainingState:
        self.state = TrainingState.ERRO
        return self.state

    def resume(self) -> TrainingState:
        self.state = TrainingState.TREINANDO
        return self.state

    def get_next_target(self, snapshot: BattleListSnapshot) -> Optional[int]:
        if not snapshot or not snapshot.rows:
            return None
        if len(snapshot.rows) < 2:
            return None
        if not self.selector.validate_snapshot(snapshot):
            return None

        protected_index = self.selector.get_protected_index(snapshot)
        if protected_index is not None and protected_index == 0:
            return None
        if not self.selector.is_candidate_eligible(snapshot, 0):
            return None
        return 0

    def evaluate_battle_list(self, snapshot: BattleListSnapshot) -> TrainingDecision:
        self.last_snapshot = snapshot
        protected_index = self.selector.get_protected_index(snapshot)
        eligible = self.selector.get_eligible_targets(snapshot)

        if snapshot.state is not SelectorState.VALID:
            return TrainingDecision(False, protected_index, (), "lista em estado incerto")
        if not snapshot.complete:
            return TrainingDecision(False, protected_index, (), "lista incompleta")
        if not snapshot.rows:
            return TrainingDecision(False, None, (), "lista vazia")
        if len(snapshot.rows) < 2:
            return TrainingDecision(False, protected_index, (), "necessário pelo menos dois alvos para atacar")
        if not self.selector.validate_snapshot(snapshot):
            return TrainingDecision(False, protected_index, (), "still waiting for stable captures")

        if not eligible:
            return TrainingDecision(False, protected_index, (), "nenhum alvo elegível sem violar a regra da mãe")

        next_target = self.get_next_target(snapshot)
        if next_target is None:
            return TrainingDecision(False, protected_index, (), "próximo alvo indisponível")

        return TrainingDecision(
            True,
            protected_index,
            eligible,
            f"alvo seguro disponível: {next_target}"
        )

    def reset_training(self) -> None:
        self.state = TrainingState.INATIVO
        self.selector.reset()
        self.last_snapshot = None
