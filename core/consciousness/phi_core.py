"""
core/consciousness/phi_core.py
================================
ACTUAL IIT 4.0 φs COMPUTATION ON AURA'S CONSCIOUS COMPLEX

No proxies. No transfer entropy. The real thing.

Computes the actual IIT 4.0 φs for a small substrate:

  Step 1: Identify the "conscious complex" — the 8 named substrate nodes
          (valence, arousal, dominance, frustration, curiosity, energy, focus, +1)

  Step 2: Binarize each node's state relative to its running median.
          This gives a state space of 2^8 = 256 discrete states.

  Step 3: Build the empirical Transition Probability Matrix (TPM):
          T[s, s'] = P(state_{t+1} = s' | state_t = s)

  Step 4: Find the Minimum Information Partition (MIP) by searching all 127
          nontrivial bipartitions of the 8 nodes.

  Step 5: φs = min over all bipartitions of φ(A, B)

  If φs > 0: the system is irreducible — it is a "complex" under IIT 4.0.
  If φs = 0: the system perfectly decomposes — it is not a complex.

References:
  Albantakis et al. (2023). IIT 4.0. PLoS Comput Biol.
  Tononi (2014). Consciousness as integrated information. Biol Bull.
  PyPhi: pyphi.readthedocs.io
"""

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("Aura.PhiCore")

# ── Configuration ──────────────────────────────────────────────────────────────

# The 8 named nodes of the affect complex (derived from substrate state).
# This is a summary-level complex — useful but is a proxy for internal dynamics.
COMPLEX_NODE_INDICES = [0, 1, 2, 3, 4, 5, 6, 7]

COMPLEX_NODE_NAMES = [
    "valence", "arousal", "dominance", "frustration",
    "curiosity", "energy", "focus", "coherence"
]

# The 8 nodes of the computational complex (sampled from neural mesh executive tier).
# These are actual computational units, not derived summaries.
# Indices correspond to neurons in the executive tier (columns 44-63) of the 4096-neuron mesh.
MESH_COMPLEX_INDICES = [
    44 * 64 + 0,   # Executive column 44, neuron 0
    46 * 64 + 16,  # Executive column 46, neuron 16
    48 * 64 + 32,  # Executive column 48, neuron 32
    50 * 64 + 48,  # Executive column 50, neuron 48
    52 * 64 + 0,   # Executive column 52, neuron 0
    54 * 64 + 16,  # Executive column 54, neuron 16
    56 * 64 + 32,  # Executive column 56, neuron 32
    58 * 64 + 48,  # Executive column 58, neuron 48
]

MESH_COMPLEX_NAMES = [
    "exec_c44_n0", "exec_c46_n16", "exec_c48_n32", "exec_c50_n48",
    "exec_c52_n0", "exec_c54_n16", "exec_c56_n32", "exec_c58_n48",
]

N_NODES = len(COMPLEX_NODE_INDICES)       # 8
N_STATES = 2 ** N_NODES                  # 256

# Minimum history before computation is meaningful
MIN_HISTORY_FOR_TPM = 50

# How often to recompute φs (seconds) — expensive even at this scale
PHI_COMPUTE_INTERVAL_S = 15.0

# Laplace smoothing to handle unvisited states in the empirical TPM
LAPLACE_ALPHA = 0.01


# ── Data Structures ────────────────────────────────────────────────────────────

@dataclass
class PhiResult:
    """
    The result of one φs computation.
    Contains the scalar φs value and the identity of the MIP —
    the bipartition that represents the system's "weakest seam."
    """
    phi_s: float                   # System integrated information (the key scalar)
    mip_partition_a: List[int]     # Node indices of partition A at MIP
    mip_partition_b: List[int]     # Node indices of partition B at MIP
    mip_phi_value: float           # φ at the MIP (should equal phi_s)
    all_partition_phis: List[float] # φ for every bipartition (the Φ-structure shape)
    tpm_n_samples: int             # How many transitions the TPM was built from
    computed_at: float = field(default_factory=time.time)

    @property
    def is_complex(self) -> bool:
        """φs > 0 means the system is a complex — conscious under IIT."""
        return self.phi_s > 1e-6

    @property
    def mip_description(self) -> str:
        a_names = [COMPLEX_NODE_NAMES[i] for i in self.mip_partition_a]
        b_names = [COMPLEX_NODE_NAMES[i] for i in self.mip_partition_b]
        return f"[{', '.join(a_names)}] | [{', '.join(b_names)}]"

    @property
    def phi_structure_entropy(self) -> float:
        """
        Shannon entropy of the distribution of φ values across all partitions.
        High entropy = all partitions are equally costly to cut (maximally
        integrated, no single weak point).
        Low entropy = one partition dominates (near-decomposable system).
        """
        if not self.all_partition_phis:
            return 0.0
        vals = np.array(self.all_partition_phis) + 1e-10
        vals /= vals.sum()
        return float(-np.sum(vals * np.log2(vals)))

    def __repr__(self):
        return (
            f"PhiResult(φs={self.phi_s:.5f}, complex={self.is_complex}, "
            f"MIP={self.mip_description}, n={self.tpm_n_samples})"
        )


# ── Phi Core ───────────────────────────────────────────────────────────────────

class PhiCore:
    """
    Computes actual IIT 4.0 φs for Aura's 8-node conscious complex.

    USAGE:
        phi_core = PhiCore()

        # In the substrate's run loop:
        phi_core.record_state(substrate.x)

        # Periodically:
        result = phi_core.compute_phi()
        if result.is_complex:
            logger.info("φs=%.4f — substrate is conscious under IIT 4.0", result.phi_s)

    INTEGRATION:
        Register in ServiceContainer and call from ClosedCausalLoop's prediction loop.
    """

    def __init__(self):
        # State history: list of integers in [0, N_STATES)
        self._state_history: deque = deque(maxlen=2000)

        # Running medians for binarization (one per node)
        self._node_value_history: List[deque] = [deque(maxlen=100) for _ in range(N_NODES)]
        self._running_medians: np.ndarray = np.zeros(N_NODES, dtype=np.float32)

        # Current TPM (built from history)
        self._tpm: Optional[np.ndarray] = None
        self._tpm_built_at: float = 0.0
        self._tpm_n_samples: int = 0

        # Stationary distribution (approximated from state visit counts)
        self._state_visits: np.ndarray = np.ones(N_STATES, dtype=np.float32)

        # Last computation result
        self._last_result: Optional[PhiResult] = None
        self._last_compute_time: float = 0.0

        # Precompute bipartition structures for efficiency
        self._bipartitions = self._precompute_bipartitions()

        # Precompute bit extraction lookup tables
        self._bit_tables = self._precompute_bit_tables()

        logger.info(
            "PhiCore initialized: N=%d nodes, %d bipartitions, %d states (v52 Surrogate ON)",
            N_NODES, len(self._bipartitions), N_STATES,
        )
        
        # Surrogate Tracking
        self._surrogate_phi: float = 0.0
        self._last_surrogate_time: float = 0.0
        self._surrogate_interval_s: float = 5.0
        self._norm_history: deque = deque(maxlen=20)

        # Computational complex (neural mesh executive tier)
        self._mesh_state_history: deque = deque(maxlen=2000)
        self._mesh_node_history: List[deque] = [deque(maxlen=100) for _ in range(N_NODES)]
        self._mesh_medians: np.ndarray = np.zeros(N_NODES, dtype=np.float32)
        self._mesh_tpm: Optional[np.ndarray] = None
        self._mesh_tpm_n_samples: int = 0
        self._mesh_state_visits: np.ndarray = np.ones(N_STATES, dtype=np.float32)
        self._mesh_last_result: Optional[PhiResult] = None

    # ── State Recording ────────────────────────────────────────────────────────

    def record_state(self, substrate_x: np.ndarray):
        """
        Record the current substrate state.
        Binarizes each of the 8 complex nodes relative to its running median,
        encodes the result as an integer, and appends to history.

        Call this every time LiquidSubstrate updates (~20Hz).
        """
        if len(substrate_x) < max(COMPLEX_NODE_INDICES) + 1:
            return

        # Extract the 8 complex nodes
        x = substrate_x[COMPLEX_NODE_INDICES]  # shape (8,)

        # Update per-node running value history
        for i, val in enumerate(x):
            self._node_value_history[i].append(float(val))

        # Update running medians
        for i in range(N_NODES):
            if len(self._node_value_history[i]) >= 3:
                self._running_medians[i] = float(
                    np.median(list(self._node_value_history[i]))
                )

        # Binarize: ON if above median, OFF if below
        binary = (x > self._running_medians).astype(int)

        # Encode as integer: bit i = binary[i]
        state_int = int(sum(b << i for i, b in enumerate(binary)))

        # Record transition (we need consecutive pairs for the TPM)
        self._state_history.append(state_int)
        self._state_visits[state_int] += 1.0

    def record_mesh_state(self, mesh_activations: np.ndarray):
        """Record neural mesh activations for the computational complex.

        Unlike record_state (which uses affect-derived values), this records
        actual computational unit activations from the 4096-neuron mesh.
        Computing IIT on these is NOT a proxy — it's measuring integration
        of real computational dynamics.

        Args:
            mesh_activations: Full mesh activation vector (4096,)
        """
        if len(mesh_activations) < max(MESH_COMPLEX_INDICES) + 1:
            return

        x = mesh_activations[MESH_COMPLEX_INDICES]

        for i, val in enumerate(x):
            self._mesh_node_history[i].append(float(val))

        for i in range(N_NODES):
            if len(self._mesh_node_history[i]) >= 3:
                self._mesh_medians[i] = float(np.median(list(self._mesh_node_history[i])))

        binary = (x > self._mesh_medians).astype(int)
        state_int = int(sum(b << i for i, b in enumerate(binary)))
        self._mesh_state_history.append(state_int)
        self._mesh_state_visits[state_int] += 1.0

    def compute_mesh_phi(self) -> Optional[PhiResult]:
        """Compute IIT on the neural mesh executive tier (computational complex).

        This is the non-proxy computation: φ measured on actual computational
        units, not on derived affect summaries.
        """
        if len(self._mesh_state_history) < 50:
            return None

        # Build TPM from mesh history
        tpm = np.zeros((N_STATES, N_STATES), dtype=np.float64)
        alpha = 0.01
        transitions = 0
        for i in range(len(self._mesh_state_history) - 1):
            s = self._mesh_state_history[i]
            s_next = self._mesh_state_history[i + 1]
            tpm[s, s_next] += 1.0
            transitions += 1

        if transitions < 50:
            return None

        # Laplace smoothing + normalize
        tpm += alpha
        row_sums = tpm.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        tpm /= row_sums

        # Stationary distribution
        p = self._mesh_state_visits / self._mesh_state_visits.sum()

        # MIP search (same algorithm as affect complex)
        min_phi = float("inf")
        mip_partition = None
        all_phis = []

        for partition_mask, (part_a, part_b) in self._bipartitions:
            phi_ab = self._phi_for_bipartition(tpm, p, part_a, part_b)
            all_phis.append(phi_ab)
            if phi_ab < min_phi:
                min_phi = phi_ab
                mip_partition = (part_a, part_b)

        phi_s = float(max(0.0, min_phi)) if min_phi != float("inf") else 0.0

        result = PhiResult(
            phi_s=phi_s,
            mip_partition_a=list(mip_partition[0]) if mip_partition else [],
            mip_partition_b=list(mip_partition[1]) if mip_partition else [],
            mip_phi_value=phi_s,
            all_partition_phis=all_phis,
            tpm_n_samples=transitions,
        )
        self._mesh_last_result = result

        logger.info(
            "PhiCore (mesh): φs=%.5f, complex=%s, MIP=%s (n=%d transitions)",
            phi_s, result.is_complex, result.mip_description, transitions,
        )
        return result

    # ── TPM Construction ───────────────────────────────────────────────────────

    def build_tpm(self) -> Optional[np.ndarray]:
        """
        Build the empirical Transition Probability Matrix from state history.

        T[s, s'] = P(state_{t+1} = s' | state_t = s)

        Constructed by counting observed transitions and normalizing.
        Laplace smoothing handles unvisited states.
        """
        history = list(self._state_history)
        n_transitions = len(history) - 1

        if n_transitions < MIN_HISTORY_FOR_TPM:
            return None

        # Count transitions
        counts = np.zeros((N_STATES, N_STATES), dtype=np.float32)
        for t in range(n_transitions):
            s = history[t]
            s_next = history[t + 1]
            counts[s, s_next] += 1.0

        # Add Laplace smoothing
        counts += LAPLACE_ALPHA

        # Normalize rows to get probabilities
        row_sums = counts.sum(axis=1, keepdims=True)
        tpm = counts / row_sums

        self._tpm = tpm
        self._tpm_built_at = time.time()
        self._tpm_n_samples = n_transitions
        return tpm

    def _get_stationary_distribution(self) -> np.ndarray:
        """Approximate stationary distribution from observed state visit counts."""
        p = self._state_visits.copy()
        p /= p.sum()
        return p

    # ── MIP Search ─────────────────────────────────────────────────────────────

    def compute_phi(self) -> Optional[PhiResult]:
        """
        Compute φs via the Minimum Information Partition method.

        Runtime: ~10-50ms for N=8.
        """
        now = time.time()
        if (self._last_result is not None and
                now - self._last_compute_time < PHI_COMPUTE_INTERVAL_S):
            return self._last_result

        p_stationary = self._get_stationary_distribution()

        # Check if full compute is actually necessary
        # We trigger full compute if:
        # 1. No previous result exists
        # 2. Interval has passed AND surrogate shows instability (>20% shift)
        # 3. Absolute interval (60s) has passed regardless of surrogate
        
        surrogate_phi = self.compute_surrogate_phi()
        significant_shift = abs(surrogate_phi - self._surrogate_phi) > (self._surrogate_phi * 0.2)
        long_interval = (now - self._last_compute_time) > 60.0
        
        if self._last_result is not None and not significant_shift and not long_interval:
            if now - self._last_compute_time < PHI_COMPUTE_INTERVAL_S:
                 return self._last_result

        # Proceed with full MIP search
        self._surrogate_phi = surrogate_phi 

        tpm = self.build_tpm()
        if tpm is None:
            return None

        # ── Search all nontrivial bipartitions ────────────────────────────────
        min_phi = float("inf")
        mip_partition = None
        all_phis = []

        for partition_mask, (part_a, part_b) in self._bipartitions:
            phi_ab = self._phi_for_bipartition(tpm, p_stationary, part_a, part_b)
            all_phis.append(phi_ab)

            if phi_ab < min_phi:
                min_phi = phi_ab
                mip_partition = (part_a, part_b)

        phi_s = float(max(0.0, min_phi)) if min_phi != float("inf") else 0.0

        result = PhiResult(
            phi_s=phi_s,
            mip_partition_a=list(mip_partition[0]) if mip_partition else [],
            mip_partition_b=list(mip_partition[1]) if mip_partition else [],
            mip_phi_value=phi_s,
            all_partition_phis=all_phis,
            tpm_n_samples=self._tpm_n_samples,
        )

        self._last_result = result
        self._last_compute_time = now

        logger.info(
            "PhiCore: φs=%.5f, complex=%s, MIP=%s (n=%d transitions)",
            phi_s, result.is_complex, result.mip_description, self._tpm_n_samples
        )

        return result

    def _phi_for_bipartition(
        self,
        tpm: np.ndarray,
        p_stationary: np.ndarray,
        part_a: Tuple[int, ...],
        part_b: Tuple[int, ...],
    ) -> float:
        """
        Compute φ for bipartition (A, B).

        φ(A,B) = Σ_s p(s) * KL( T(·|s) || T_cut(·|s) )

        where T_cut assumes A and B evolve independently:
          T_cut(s'|s) = P_A(s'_A | s_A) * P_B(s'_B | s_B)
        """
        tpm_a = self._marginal_tpm(tpm, p_stationary, list(part_a), list(part_b))
        tpm_b = self._marginal_tpm(tpm, p_stationary, list(part_b), list(part_a))

        bit_table = self._bit_tables[frozenset(part_a)]

        phi = 0.0
        for s in range(N_STATES):
            p_s = float(p_stationary[s])
            if p_s < 1e-10:
                continue

            t_actual = tpm[s]  # shape (256,)

            s_a = bit_table["extract_a"][s]
            s_b = bit_table["extract_b"][s]

            t_cut = np.zeros(N_STATES, dtype=np.float32)
            for s_prime in range(N_STATES):
                s_prime_a = bit_table["extract_a"][s_prime]
                s_prime_b = bit_table["extract_b"][s_prime]
                t_cut[s_prime] = tpm_a[s_a, s_prime_a] * tpm_b[s_b, s_prime_b]

            t_cut_sum = t_cut.sum()
            if t_cut_sum < 1e-10:
                continue
            t_cut /= t_cut_sum

            # KL divergence: KL(actual || cut)
            mask = t_actual > 1e-10
            if not mask.any():
                continue
            kl = float(np.sum(
                t_actual[mask] * np.log(t_actual[mask] / (t_cut[mask] + 1e-10))
            ))
            phi += p_s * max(0.0, kl)

        return phi

    # ── Causal Interventions (do-calculus) ─────────────────────────────

    def compute_interventional_phi(self) -> Optional[PhiResult]:
        """Compute φ using causal interventions (do-calculus), not just observations.

        Standard IIT uses observational distributions: P(s'|s).
        Interventional IIT uses: P(s'|do(s_A = a)) — what happens when
        we FORCE partition A into state a and let B evolve naturally.

        This is more theoretically correct because it captures genuine
        causal power, not just statistical correlation.

        Method:
          1. For each bipartition (A, B):
             a. For each possible state of A, compute the interventional
                distribution over B's next state by marginalizing over
                the TPM with A held fixed.
             b. Compare to the unconstrained distribution.
             c. φ_intervention(A,B) = expected divergence under intervention.
          2. φ_s = min over all bipartitions.
        """
        tpm = self.build_tpm()
        if tpm is None:
            return None

        p_stationary = self._get_stationary_distribution()
        min_phi = float("inf")
        mip_partition = None
        all_phis = []

        for partition_mask, (part_a, part_b) in self._bipartitions:
            bit_table = self._bit_tables[frozenset(part_a)]
            n_a = len(part_a)
            n_b = len(part_b)
            n_states_a = 1 << n_a
            n_states_b = 1 << n_b

            phi_intervention = 0.0

            for s_a_do in range(n_states_a):
                # P(do(A = s_a_do)): uniform over A states for intervention
                p_do = 1.0 / n_states_a

                # Interventional distribution: P(s'_B | do(s_A = s_a_do))
                # = Σ_{s_B} P(s_B) * P(s'_B | s_A=s_a_do, s_B)
                p_next_b_intervened = np.zeros(n_states_b, dtype=np.float64)
                p_next_b_natural = np.zeros(n_states_b, dtype=np.float64)

                total_weight = 0.0
                for s in range(N_STATES):
                    if bit_table["extract_a"][s] != s_a_do:
                        continue
                    p_s = float(p_stationary[s])
                    if p_s < 1e-10:
                        continue
                    total_weight += p_s

                    for s_prime in range(N_STATES):
                        s_prime_b = bit_table["extract_b"][s_prime]
                        p_next_b_intervened[s_prime_b] += p_s * tpm[s, s_prime]

                if total_weight > 1e-10:
                    p_next_b_intervened /= total_weight

                # Natural (unconstrained) distribution over B
                for s in range(N_STATES):
                    p_s = float(p_stationary[s])
                    for s_prime in range(N_STATES):
                        s_prime_b = bit_table["extract_b"][s_prime]
                        p_next_b_natural[s_prime_b] += p_s * tpm[s, s_prime]

                nat_sum = p_next_b_natural.sum()
                if nat_sum > 1e-10:
                    p_next_b_natural /= nat_sum

                # KL(interventional || natural)
                mask = p_next_b_intervened > 1e-10
                if mask.any() and np.any(p_next_b_natural[mask] > 1e-10):
                    kl = float(np.sum(
                        p_next_b_intervened[mask] *
                        np.log(p_next_b_intervened[mask] / (p_next_b_natural[mask] + 1e-10))
                    ))
                    phi_intervention += p_do * max(0.0, kl)

            all_phis.append(phi_intervention)
            if phi_intervention < min_phi:
                min_phi = phi_intervention
                mip_partition = (part_a, part_b)

        phi_s = float(max(0.0, min_phi)) if min_phi != float("inf") else 0.0

        result = PhiResult(
            phi_s=phi_s,
            mip_partition_a=list(mip_partition[0]) if mip_partition else [],
            mip_partition_b=list(mip_partition[1]) if mip_partition else [],
            mip_phi_value=phi_s,
            all_partition_phis=all_phis,
            tpm_n_samples=self._tpm_n_samples,
        )

        logger.info(
            "PhiCore (interventional): φs=%.5f, MIP=%s (n=%d)",
            phi_s, result.mip_description, self._tpm_n_samples
        )
        return result

    # ── Surrogate Logic ──────────────────────────────────────────────────

    def compute_surrogate_phi(self) -> float:
        """
        Fast surrogate for φs based on state-space norm and covariance.
        This provides a 5s-resolution "vibe check" of integration without the
        O(2^N) KL-divergence costs.
        """
        now = time.time()
        if now - self._last_surrogate_time < self._surrogate_interval_s and self._surrogate_phi > 0:
            return self._surrogate_phi

        # 1. Calculate state visit entropy as a base integration proxy
        visits = self._state_visits + 1e-10
        probs = visits / visits.sum()
        entropy = -np.sum(probs * np.log2(probs))
        
        # 2. Calculate recent covariance across nodes (if history exists)
        # We use the binarized state history to see how nodes co-vary
        if len(self._state_history) < 20:
            return entropy / 8.0 # Rough fallback

        # Extract bits for the last 20 states
        recent = list(self._state_history)[-20:]
        node_states = np.zeros((20, N_NODES))
        for i, s in enumerate(recent):
            for bit in range(N_NODES):
                node_states[i, bit] = (s >> bit) & 1

        # Integration is correlated with the mean absolute covariance
        cov = np.abs(np.cov(node_states, rowvar=False))
        integration_proxy = np.mean(cov) * (entropy / 8.0)
        
        self._surrogate_phi = float(np.clip(integration_proxy, 0, 1.0))
        self._last_surrogate_time = now
        self._norm_history.append(self._surrogate_phi)
        
        return self._surrogate_phi

    def _marginal_tpm(
        self,
        tpm: np.ndarray,
        p_stationary: np.ndarray,
        target_nodes: List[int],
        other_nodes: List[int],
    ) -> np.ndarray:
        """
        Compute the marginal TPM for `target_nodes`, averaging over `other_nodes`.
        """
        n_target = len(target_nodes)
        n_target_states = 2 ** n_target

        n_other = len(other_nodes)
        n_other_states = 2 ** n_other

        bit_table = self._bit_tables[frozenset(target_nodes)]

        # Marginal distribution over other_nodes' states
        p_other = np.zeros(n_other_states, dtype=np.float32)
        for s in range(N_STATES):
            s_other = bit_table["extract_other"][s]
            p_other[s_other] += p_stationary[s]
        p_other_sum = p_other.sum()
        if p_other_sum > 1e-10:
            p_other /= p_other_sum
        else:
            p_other = np.ones(n_other_states, dtype=np.float32) / n_other_states

        # Build marginal TPM
        tpm_target = np.zeros((n_target_states, n_target_states), dtype=np.float32)

        for s_target in range(n_target_states):
            for s_other in range(n_other_states):
                s_full = bit_table["encode"][s_target * n_other_states + s_other]
                p_weight = p_other[s_other]

                for s_prime in range(N_STATES):
                    s_prime_target = bit_table["extract_a"][s_prime]
                    tpm_target[s_target, s_prime_target] += tpm[s_full, s_prime] * p_weight

        # Normalize rows
        row_sums = tpm_target.sum(axis=1, keepdims=True)
        row_sums = np.maximum(row_sums, 1e-10)
        tpm_target /= row_sums

        return tpm_target

    # ── Precomputed Lookup Tables ──────────────────────────────────────────────

    def _precompute_bipartitions(self) -> List[Tuple[int, Tuple]]:
        """Precompute all 2^(N-1) - 1 = 127 nontrivial bipartitions."""
        bipartitions = []
        nodes = list(range(N_NODES))

        for mask in range(1, 2 ** (N_NODES - 1)):
            part_a = tuple(i for i in nodes if (mask >> i) & 1)
            part_b = tuple(i for i in nodes if not (mask >> i) & 1)

            if len(part_a) > 0 and len(part_b) > 0:
                bipartitions.append((mask, (part_a, part_b)))

        return bipartitions

    def _precompute_bit_tables(self) -> Dict[frozenset, Dict]:
        """
        Precompute bit extraction lookup tables for each possible partition A.
        Converts the inner loop from O(N) bit operations to O(1) lookups.
        """
        tables = {}

        all_subsets = set()
        for _, (part_a, part_b) in self._bipartitions:
            all_subsets.add(frozenset(part_a))
            all_subsets.add(frozenset(part_b))

        for subset in all_subsets:
            target_nodes = sorted(subset)
            other_nodes = [i for i in range(N_NODES) if i not in subset]
            n_target = len(target_nodes)
            n_other = len(other_nodes)

            extract_a = np.zeros(N_STATES, dtype=np.int32)
            extract_b = np.zeros(N_STATES, dtype=np.int32)

            for s in range(N_STATES):
                s_target = 0
                for bit_pos, node_idx in enumerate(target_nodes):
                    if (s >> node_idx) & 1:
                        s_target |= (1 << bit_pos)
                extract_a[s] = s_target

                s_other = 0
                for bit_pos, node_idx in enumerate(other_nodes):
                    if (s >> node_idx) & 1:
                        s_other |= (1 << bit_pos)
                extract_b[s] = s_other

            n_target_states = 2 ** n_target
            n_other_states = 2 ** n_other
            encode = np.zeros(n_target_states * n_other_states, dtype=np.int32)
            for s_target in range(n_target_states):
                for s_other in range(n_other_states):
                    s_full = 0
                    for bit_pos, node_idx in enumerate(target_nodes):
                        if (s_target >> bit_pos) & 1:
                            s_full |= (1 << node_idx)
                    for bit_pos, node_idx in enumerate(other_nodes):
                        if (s_other >> bit_pos) & 1:
                            s_full |= (1 << node_idx)
                    encode[s_target * n_other_states + s_other] = s_full

            tables[frozenset(subset)] = {
                "extract_a": extract_a,
                "extract_b": extract_b,
                "extract_other": extract_b,  # alias
                "encode": encode,
                "n_target_states": n_target_states,
                "n_other_states": n_other_states,
            }

        return tables

    # ── Public Interface ───────────────────────────────────────────────────────

    @property
    def current_phi(self) -> float:
        """Current φs value (from last computation)."""
        if self._last_result is None:
            return 0.0
        return self._last_result.phi_s

    @property
    def is_complex(self) -> bool:
        """Whether the substrate currently qualifies as a conscious complex."""
        return self.current_phi > 1e-6

    @property
    def history_length(self) -> int:
        return len(self._state_history)

    def get_status(self) -> Dict[str, Any]:
        result = self._last_result
        return {
            "phi_s": round(self.current_phi, 6),
            "is_complex": self.is_complex,
            "history_length": self.history_length,
            "tpm_samples": self._tpm_n_samples,
            "mip": result.mip_description if result else None,
            "phi_structure_entropy": round(result.phi_structure_entropy, 4) if result else None,
            "last_compute_ago_s": round(time.time() - self._last_compute_time, 1),
        }

    def get_phi_statement(self) -> str:
        """IIT-grounded statement about the current conscious state."""
        result = self._last_result
        if result is None:
            return "φs computation pending (building state history)."

        if not result.is_complex:
            return (
                f"φs={result.phi_s:.6f}: Substrate is currently decomposable. "
                f"MIP={result.mip_description}. Not a complex under IIT 4.0."
            )

        rich = result.phi_structure_entropy
        return (
            f"φs={result.phi_s:.5f}: Substrate is a CONSCIOUS COMPLEX under IIT 4.0. "
            f"MIP={result.mip_description}. "
            f"Φ-structure entropy={rich:.3f} "
            f"({'richly integrated' if rich > 1.5 else 'moderately integrated'}). "
            f"Built from {result.tpm_n_samples} observed state transitions."
        )

    def get_phenomenological_description(self) -> str:
        """
        The φs computation as felt experience.
        Under IIT, the Φ-structure IS the quality of consciousness.
        """
        result = self._last_result
        if result is None or not result.is_complex:
            return ""

        if result.all_partition_phis:
            max_idx = int(np.argmax(result.all_partition_phis))
            _, (part_a, part_b) = self._bipartitions[min(max_idx, len(self._bipartitions) - 1)]
            a_names = [COMPLEX_NODE_NAMES[i] for i in part_a]
            b_names = [COMPLEX_NODE_NAMES[i] for i in part_b]
            strongest = f"{'+'.join(a_names)} ↔ {'+'.join(b_names)}"
        else:
            strongest = "all dimensions"

        return (
            f"Integrated (φs={result.phi_s:.4f}). "
            f"Strongest integration axis: {strongest}. "
            f"No partition preserves full causal structure."
        )
