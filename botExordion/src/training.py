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


# Modo Normal: abaixo desta vida (%) o alvo é trocado pelo mob com mais vida,
# desde que ele tenha pelo menos SWITCH_MARGIN pontos a mais.
SWITCH_BELOW = 50.0
SWITCH_MARGIN = 3.0
# Vida aproximada pela cor da barra, quando a % não foi lida.
HP_BY_COLOR = {"green": 100.0, "yellow": 45.0, "red": 15.0}


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


class NormalOrder(str, Enum):
    BALANCE = "balance"  # troca para o mob com mais vida quando o alvo enfraquece
    TOP = "top"          # primeiro da lista, até morrer


def attackable(snapshot: BattleListSnapshot) -> Tuple[int, ...]:
    """Índices que podem ser atacados, de cima para baixo (sem ignorados/desconhecidos)."""
    return tuple(i for i, row in enumerate(snapshot.rows) if row.allowed)


@dataclass
class TrainingDecision:
    can_attack: bool
    protected_index: Optional[int]
    eligible_targets: Tuple[int, ...]
    reason: str


class TrainingStateMachine:
    def __init__(self, mode: TrainingMode = TrainingMode.SUMMON_CREATURES,
                 normal_order: NormalOrder = NormalOrder.BALANCE) -> None:
        self.state = TrainingState.INATIVO
        self.mode: TrainingMode = mode
        self.normal_order: NormalOrder = normal_order
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

    def set_mode(self, mode: TrainingMode, normal_order: Optional[NormalOrder] = None) -> None:
        self.mode = mode
        if normal_order is not None:
            self.normal_order = normal_order
        self._last_normal_target = None

    # ---------- seleção de alvo ----------

    def get_next_target(self, snapshot: BattleListSnapshot) -> Optional[int]:
        if not snapshot or not snapshot.rows:
            return None
        if self.mode == TrainingMode.NORMAL_CREATURES:
            return self._get_next_normal_target(snapshot)
        return self._get_next_summon_target(snapshot)

    def _get_next_summon_target(self, snapshot: BattleListSnapshot) -> Optional[int]:
        """Summon: o primeiro atacável de cima para baixo, pulando ignorados.
        Com um só atacável não ataca: sem summons, esse é o bicho principal."""
        targets = attackable(snapshot)
        if len(targets) < 2:
            return None
        if not self.selector.validate_snapshot(snapshot):
            return None

        first = targets[0]
        protected_index = self.selector.get_protected_index(snapshot)
        if protected_index is not None and protected_index == first:
            return None
        if not self.selector.is_candidate_eligible(snapshot, first):
            return None
        return first

    def _get_next_normal_target(self, snapshot: BattleListSnapshot) -> Optional[int]:
        """Normal Creatures: espalha o dano para os mobs durarem mais.
        - Alvo atual com HP >= SWITCH_BELOW: continua nele.
        - Abaixo disso: troca para o mob permitido com mais vida, se ele tiver
          pelo menos SWITCH_MARGIN pontos a mais (evita trocar a cada golpe).
          Senão mantém o atual, até o último morrer.
        - Sem alvo (morreu ou ainda não atacou): o permitido com mais vida.
        Quando a % de vida não foi lida, cai na regra por cor (verde = cheio).
        """
        n = len(snapshot.rows)
        if n == 0:
            return None

        selected = snapshot.selected_index
        # Considera seleção detectada no snapshot; senão usa a memória como fallback.
        # O alvo que já está sendo atacado vale mesmo se o nome não bater: o nome
        # muda de cor quando é alvo, e largá-lo aqui faz o bot alternar entre dois.
        current_idx: Optional[int] = None
        if selected is not None and 0 <= selected < n:
            current_idx = selected
        elif self._last_normal_target is not None and self._last_normal_target < n:
            current_idx = self._last_normal_target
            if not snapshot.rows[current_idx].allowed:
                current_idx = None

        target = self._choose_normal_target(snapshot, current_idx)
        self._last_normal_target = target
        return target

    @staticmethod
    def _health(row) -> Optional[float]:
        if row.hp_percent is not None:
            return row.hp_percent
        return HP_BY_COLOR.get(row.hp_state)

    def _choose_normal_target(self, snapshot: BattleListSnapshot, current_idx: Optional[int]) -> Optional[int]:
        if self.normal_order == NormalOrder.TOP:
            if current_idx is not None:
                return current_idx  # fica no alvo até ele morrer
            targets = attackable(snapshot)
            return targets[0] if targets else None

        others = [(self._health(row), -i, i) for i, row in enumerate(snapshot.rows)
                  if i != current_idx and row.allowed and self._health(row) is not None]
        best = max(others)[2] if others else None  # mais vida; empate fica com o de cima

        if current_idx is None:
            if best is not None:
                return best
            allowed = [i for i, row in enumerate(snapshot.rows) if row.allowed]
            return allowed[0] if allowed else None

        current = self._health(snapshot.rows[current_idx])
        if current is None or current >= SWITCH_BELOW or best is None:
            return current_idx
        if self._health(snapshot.rows[best]) >= current + SWITCH_MARGIN:
            return best
        return current_idx

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


class AttackPlanner:
    """Decide onde clicar a cada leitura da battle list."""

    def __init__(self, machine: TrainingStateMachine) -> None:
        self.machine = machine
        self._last_key = None
        self._last_at = 0.0

    def plan(self, snapshot: BattleListSnapshot, now: float):
        """Devolve (posição do clique ou None, motivo)."""
        if snapshot is None or not snapshot.complete or not snapshot.rows:
            return None, "Battle list vazia."
        if self.machine.mode == TrainingMode.NORMAL_CREATURES:
            return self._plan_normal(snapshot, now)
        return self._plan_summon(snapshot, now)

    def _cooling_down(self, key, now: float, seconds: float) -> bool:
        if key == self._last_key and now - self._last_at < seconds:
            return True
        self._last_key = key
        self._last_at = now
        return False

    @staticmethod
    def _center(row: BattleListRow):
        left, top, right, bottom = row.bounds
        return ((left + right) // 2, (top + bottom) // 2)

    def _plan_summon(self, snapshot: BattleListSnapshot, now: float):
        targets = attackable(snapshot)
        if not targets:
            return None, "Nenhum alvo permitido."
        if len(targets) == 1:
            return None, "Só um bicho atacável: é o principal, não ataca."
        if snapshot.selected_index is not None:
            return None, "Já existe um alvo selecionado."
        first = targets[0]
        key = tuple((row.index, row.bounds) for row in snapshot.rows[:3])
        if self._cooling_down(key, now, 1.2):
            return None, "Aguardando cooldown."
        return self._center(snapshot.rows[first]), f"Atacando alvo #{first}."

    def _plan_normal(self, snapshot: BattleListSnapshot, now: float):
        target = self.machine.get_next_target(snapshot)
        if target is None:
            return None, "Nenhum alvo permitido."
        if snapshot.selected_index == target:
            return None, "Alvo já selecionado."
        if self._cooling_down(target, now, 1.0):
            return None, "Aguardando cooldown."
        row = snapshot.rows[target]
        hp = f"{row.hp_percent:.0f}%" if row.hp_percent is not None else row.hp_state
        return self._center(row), f"Atacando alvo #{target} (HP {hp})."


class HealPlanner:
    """Modo Normal: usa a runa de cura no alvo quando a vida dele cai abaixo do limite."""

    def __init__(self) -> None:
        self._next_at = 0.0

    def reset(self) -> None:
        self._next_at = 0.0

    def plan(self, snapshot: BattleListSnapshot, now: float, config: dict):
        """Devolve (posição da linha do alvo ou None, motivo)."""
        if not config.get("enabled") or not config.get("rune"):
            return None, "Cura desligada."
        index = snapshot.selected_index if snapshot is not None else None
        if index is None or not 0 <= index < len(snapshot.rows):
            return None, "Sem alvo para curar."
        row = snapshot.rows[index]
        if row.hp_percent is None or row.hp_percent >= float(config["below"]):
            return None, "Alvo com vida suficiente."
        if now < self._next_at:
            return None, "Aguardando intervalo da cura."
        self._next_at = now + float(config["cooldown"])
        return AttackPlanner._center(row), f"Curando alvo #{index} (HP {row.hp_percent:.0f}%)."
