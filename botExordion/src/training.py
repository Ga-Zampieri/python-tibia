from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from .battle_list_selector import (
    BattleListRow,
    BattleListSnapshot,
    SafeBattleListTargetSelector,
    SelectorState,
)


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


class TrainingMode(str, Enum):
    SUMMON_CREATURES = "summon"
    NORMAL_CREATURES = "normal"


@dataclass
class TrainingDecision:
    can_attack: bool
    protected_index: Optional[int]
    eligible_targets: Tuple[int, ...]
    reason: str


class TrainingStateMachine:
    def __init__(self, mode: TrainingMode = TrainingMode.SUMMON_CREATURES) -> None:
        self.state = TrainingState.INATIVO
        self.mode: TrainingMode = mode
        self.selector = SafeBattleListTargetSelector(min_confidence=0.8, required_stable_captures=2)
        self.last_snapshot: Optional[BattleListSnapshot] = None
        # Memória do último alvo normal atacado (fallback quando o outline falha)
        self._last_normal_target: Optional[int] = None

    # ---------- ciclo de vida ----------

    def start(self) -> TrainingState:
        self.state = TrainingState.CALIBRANDO
        self._last_normal_target = None
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

    def set_mode(self, mode: TrainingMode) -> None:
        self.mode = mode
        self._last_normal_target = None

    # ---------- seleção de alvo ----------

    def get_next_target(self, snapshot: BattleListSnapshot) -> Optional[int]:
        if not snapshot or not snapshot.rows:
            return None
        if self.mode == TrainingMode.NORMAL_CREATURES:
            return self._get_next_normal_target(snapshot)
        return self._get_next_summon_target(snapshot)

    def _get_next_summon_target(self, snapshot: BattleListSnapshot) -> Optional[int]:
        """Regra original: protege a última linha e ataca a primeira elegível."""
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

    def _get_next_normal_target(self, snapshot: BattleListSnapshot) -> Optional[int]:
        """Normal Creatures:
        - Se o alvo atual está com HP verde: continua nele.
        - Se o alvo atual está com HP baixo (yellow/red): troca para o próximo verde.
        - Se não há verdes: mantém atacando o atual.
        - Se o alvo atual morreu (não há mais outline vermelho / índice inválido):
          ataca o próximo verde. Se não houver, ataca o primeiro da lista.
        """
        n = len(snapshot.rows)
        if n == 0:
            return None

        selected = snapshot.selected_index
        # Considera seleção detectada no snapshot; senão usa a memória como fallback
        current_idx: Optional[int] = None
        if selected is not None and 0 <= selected < n:
            current_idx = selected
        elif self._last_normal_target is not None and self._last_normal_target < n:
            current_idx = self._last_normal_target

        self._last_normal_target = current_idx

        if current_idx is not None:
            current = snapshot.rows[current_idx]
            if current.hp_state == "green" or current.hp_state == "unknown":
                return current_idx
            # HP baixo -> procura próximo verde (diferente do atual)
            for i, row in enumerate(snapshot.rows):
                if i != current_idx and row.hp_state == "green":
                    self._last_normal_target = i
                    return i
            # Sem verdes -> mantém o atual
            return current_idx

        # Sem alvo atual -> primeiro verde disponível
        for i, row in enumerate(snapshot.rows):
            if row.hp_state == "green":
                self._last_normal_target = i
                return i

        # Sem verdes -> ataca o primeiro da lista
        self._last_normal_target = 0
        return 0

    # ---------- avaliação (usada para display/log) ----------

    def evaluate_battle_list(self, snapshot: BattleListSnapshot) -> TrainingDecision:
        self.last_snapshot = snapshot
        protected_index = self.selector.get_protected_index(snapshot)
        eligible = self.selector.get_eligible_targets(snapshot)

        mode_name = (
            "Normal Creatures"
            if self.mode == TrainingMode.NORMAL_CREATURES
            else "Summon Creatures"
        )

        if snapshot.state is not SelectorState.VALID:
            return TrainingDecision(False, protected_index, (), f"[{mode_name}] lista em estado incerto")
        if not snapshot.complete:
            return TrainingDecision(False, protected_index, (), f"[{mode_name}] lista incompleta")
        if not snapshot.rows:
            return TrainingDecision(False, None, (), f"[{mode_name}] lista vazia")

        if self.mode == TrainingMode.NORMAL_CREATURES:
            target = self.get_next_target(snapshot)
            if target is None:
                return TrainingDecision(False, None, (), f"[{mode_name}] nenhum alvo elegível")
            hp = snapshot.rows[target].hp_state if target < len(snapshot.rows) else "?"
            return TrainingDecision(
                True,
                None,
                (target,),
                f"[{mode_name}] alvo #{target} (HP: {hp})",
            )

        # Summon (comportamento original)
        if len(snapshot.rows) < 2:
            return TrainingDecision(False, protected_index, (), f"[{mode_name}] necessário pelo menos dois alvos")
        if not self.selector.validate_snapshot(snapshot):
            return TrainingDecision(False, protected_index, (), f"[{mode_name}] aguardando capturas estáveis")
        if not eligible:
            return TrainingDecision(False, protected_index, (), f"[{mode_name}] nenhum alvo elegível sem violar a proteção")

        next_target = self.get_next_target(snapshot)
        if next_target is None:
            return TrainingDecision(False, protected_index, (), f"[{mode_name}] próximo alvo indisponível")

        return TrainingDecision(
            True,
            protected_index,
            eligible,
            f"[{mode_name}] alvo seguro disponível: {next_target}",
        )

    def reset_training(self) -> None:
        self.state = TrainingState.INATIVO
        self.selector.reset()
        self.last_snapshot = None
        self._last_normal_target = None