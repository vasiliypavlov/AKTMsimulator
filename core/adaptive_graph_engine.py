import hashlib
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AdaptiveNode:
    """
    Атомарный узел с контекстным полиморфизмом, хэш-якорем и памятью развязок.
    """
    node_id: str
    val: float
    deps: List[str] = field(default_factory=list)
    
    # Состояние версионности и эволюции
    version: int = 0
    abstraction_level: int = 0          # 0 = сырой узел (тропы), 1 = свернутая автомагистраль
    stability: int = 0                  # счетчик спокойных тактов для подъема абстракции
    highway_hash: Optional[str] = None  # контент-адресный якорь стабилизированного состояния
    
    # Память нижнего уровня ("грунтовые тропы" и буфер карантина при сбоях железа)
    trails: deque = field(default_factory=lambda: deque(maxlen=24))
    quarantine_ticks: int = 0

    def compute_content_hash(self) -> str:
        """Эмуляция аппаратной хэш-адресации (в железе — BLAKE3 / CAM за 1 такт)."""
        payload = f"{self.node_id}:{round(self.val, 4)}:{self.version}".encode()
        return hashlib.blake2b(payload, digest_size=8).hexdigest()

    @property
    def entropy(self) -> float:
        """Показатель турбулентности узла: сигнал для ИИ-агента, куда тратить бюджет."""
        return round(len(self.trails) / (self.stability + 1), 3)

    def try_evolve(self, verbose: bool = False) -> None:
        """Попытка свернуть стабилизировавшийся узел на уровень 'Автомагистрали'."""
        if self.quarantine_ticks > 0:
            self.quarantine_ticks -= 1
            return

        self.stability += 1
        if self.stability >= 3 and self.abstraction_level == 0:
            self.abstraction_level = 1
            self.highway_hash = self.compute_content_hash()
            if verbose:
                print(f"  [ЭВОЛЮЦИЯ] '{self.node_id}' -> АВТОМАГИСТРАЛЬ (Hash: {self.highway_hash})")

    def read(self, context: str) -> Any:
        """
        Контекстно-зависимая проекция одной и той же ячейки памяти (Zero-Copy модель).
        """
        if context == "foxpro":
            # Детерминированный legacy-мир: жесткий табличный тип, ноль метаданных
            return round(float(self.val), 2)

        elif context == "ai_vector":
            # Вероятностный мир: ИИ видит якорь магистрали и карту энтропии, не трогая сырые данные
            return {
                "id": self.node_id,
                "anchor_hash": self.highway_hash or self.compute_content_hash(),
                "mode": "HIGHWAY" if self.abstraction_level == 1 else "TRAIL",
                "entropy": self.entropy,
                "version": self.version,
                "active_trails": len(self.trails),
                "in_quarantine": self.quarantine_ticks > 0,
            }
        raise ValueError(f"Неизвестный контекст обращения: {context}")


class AdaptiveGraphEngine:
    """
    Движок исполнения с драйвером перехвата мутаций, карантином сбоев и адаптивным лагом.
    """
    def __init__(self, hw_error_rate: float = 0.20, base_max_lag: int = 10, max_deferred: int = 5):
        self.nodes: Dict[str, AdaptiveNode] = {}
        self.hw_error_rate = hw_error_rate
        self.base_max_lag = base_max_lag
        self.max_deferred = max_deferred

        # Метрики эффективности
        self.stats = {
            "hw_tears": 0,           # аппаратные сбои кремния / хэш-лукапа
            "trail_detours": 0,      # успешные обходы через сохраненные развязки
            "lattice_merges": 0,     # слияния рассинхронизированных версий без пересборки
            "catastrophic_rebuilds": 0,
        }

    def register_node(self, node: AdaptiveNode) -> None:
        self.nodes[node.node_id] = node

    def _catastrophic_rebuild(self, reason: str, verbose: bool = False) -> None:
        """Крайний случай: граф разорван по времени, принудительная пересборка снизу вверх."""
        self.stats["catastrophic_rebuilds"] += 1
        if verbose:
            print(f"  [!!! АВАРИЙНАЯ ПЕРЕСБОРКА !!!] Причина: {reason}")

        for n in self.nodes.values():
            n.abstraction_level = 0
            n.stability = 0
            n.highway_hash = None
            n.quarantine_ticks = 0
            n.trails.clear()

        # Синхронизация демо-топологии PRICE -> TAX -> TOTAL
        if {"PRICE", "TAX", "TOTAL"}.issubset(self.nodes.keys()):
            base_ver = self.nodes["PRICE"].version
            p = self.nodes["PRICE"].val
            self.nodes["TAX"].val = round(p * 0.2, 2)
            self.nodes["TAX"].version = base_ver
            self.nodes["TOTAL"].val = round(p + self.nodes["TAX"].val, 2)
            self.nodes["TOTAL"].version = base_ver

    def mutate(self, target_id: str, new_val: float, expected_dep_ver: Optional[int] = None, verbose: bool = False) -> bool:
        node = self.nodes[target_id]

        # 1. ЭМУЛЯЦИЯ АППАРАТНОГО СБОЯ (20% ошибок кремния при асимметричном потоке)
        if random.random() < self.hw_error_rate:
            self.stats["hw_tears"] += 1
            node.quarantine_ticks = 2
            node.trails.append(("TEAR_DEFERRED", new_val, node.version, time.time()))
            if verbose:
                print(f"  [СБОЙ КРЕМНИЯ] '{target_id}' -> увод в карантин (отложено: {round(new_val, 2)})")

            deferred_count = sum(1 for t in node.trails if t[0] == "TEAR_DEFERRED")
            if deferred_count >= self.max_deferred:
                self._catastrophic_rebuild(f"Переполнение карантина в '{target_id}'", verbose)
            return False

        # 2. ПРОВЕРКА ТЕМПОРАЛЬНОГО РАЗРЫВА С АДАПТИВНЫМ ОКНОМ (LATTICE MERGE)
        if expected_dep_ver is not None and node.deps:
            dep_node = self.nodes[node.deps[0]]
            lag = dep_node.version - expected_dep_ver
            # Адаптивный амортизатор: чем богаче протоптанная история и выше энтропия, тем шире окно
            effective_max_lag = self.base_max_lag + int(node.entropy * 8) + len(node.trails)

            if lag > effective_max_lag:
                self._catastrophic_rebuild(f"Темпоральный разрыв '{target_id}' (lag={lag} > {effective_max_lag})", verbose)
                return False
            elif lag > 1:
                self.stats["lattice_merges"] += 1
                self.stats["trail_detours"] += 1
                node.trails.append(("LATTICE_MERGE", node.val, new_val, dep_node.version))
                node.val = new_val
                node.version += 1
                if verbose:
                    print(f"  [СЛИЯНИЕ РЕШЕТКИ] '{target_id}' догнал '{dep_node.node_id}' (lag={lag}/{effective_max_lag})")
                return True

        # 3. ДРАЙВЕР-ПЕРЕХВАТЧИК: если узел уже "Автомагистраль", не сносим его, а пишем в развязку
        if node.abstraction_level == 1:
            self.stats["trail_detours"] += 1
            node.trails.append(("FAST_DETOUR", node.val, new_val, node.version))
            node.stability = max(0, node.stability - 1)
            if verbose:
                print(f"  [ДРАЙВЕР] Обход магистрали '{target_id}': {round(node.val, 2)} -> {round(new_val, 2)}")
        else:
            node.trails.append(("RAW_WRITE", node.val, new_val, node.version))
            node.stability = 0

        node.val = new_val
        node.version += 1
        return True

    def tick(self, verbose: bool = False) -> None:
        """Фоновый такт: доигровка карантинных транзакций и эволюция стабильных узлов."""
        for node in self.nodes.values():
            deferred = [t for t in node.trails if t[0] == "TEAR_DEFERRED"]
            if deferred and node.quarantine_ticks == 0:
                _, recovered_val, _, _ = deferred[-1]
                node.val = recovered_val
                node.version += 1
                node.trails = deque([t for t in node.trails if t[0] != "TEAR_DEFERRED"], maxlen=24)
                if verbose:
                    print(f"  [ВОССТАНОВЛЕНИЕ] Карантин '{node.node_id}' успешно влит (val={round(recovered_val, 2)})")
            node.try_evolve(verbose=verbose)


# ==============================================================================
# ИНТЕРАКТИВНЫЙ СТЕНД ДЛЯ ЗАПУСКА И ЭКСПЕРИМЕНТОВ
# ==============================================================================
if __name__ == "__main__":
    random.seed(108)  # Фиксируем зерно для воспроизводимости (уберите для случайного шторма)

    engine = AdaptiveGraphEngine(hw_error_rate=0.20)
    engine.register_node(AdaptiveNode("PRICE", 100.0))
    engine.register_node(AdaptiveNode("TAX", 20.0, deps=["PRICE"]))
    engine.register_node(AdaptiveNode("TOTAL", 120.0, deps=["PRICE", "TAX"]))

    print("=== ФАЗА 1: Прогрев и сворачивание графа в Автомагистрали ===")
    for _ in range(4):
        engine.tick(verbose=True)

    print("\n=== ФАЗА 2: Асимметричный шторм (30 тактов, 20% ошибок железа) ===")
    for step in range(1, 31):
        print(f"\n--- Такт {step:02d} ---")
        new_price = 100.0 + step * 2.5
        engine.mutate("PRICE", new_price, verbose=True)

        # TAX обновляется в 2 раза реже PRICE (асимметрия потока)
        if step % 2 == 0:
            engine.mutate(
                "TAX",
                new_price * 0.2,
                expected_dep_ver=engine.nodes["PRICE"].version - 1,
                verbose=True,
            )

        # TOTAL обновляется в 5 раз реже PRICE
        if step % 5 == 0:
            total_val = engine.nodes["PRICE"].val + engine.nodes["TAX"].val
            engine.mutate(
                "TOTAL",
                total_val,
                expected_dep_ver=engine.nodes["TAX"].version - 1,
                verbose=True,
            )

        engine.tick(verbose=True)

    print("\n" + "=" * 65)
    print("ИТОГОВАЯ СТАТИСТИКА ДВИЖКА:")
    for k, v in engine.stats.items():
        print(f"  * {k}: {v}")

    print("\nСОСТОЯНИЕ ЯЧЕЕК ГЛАЗАМИ ДВУХ МИРОВ (БЕЗ ВМ И СЕРИАЛИЗАЦИИ):")
    for nid, node in engine.nodes.items():
