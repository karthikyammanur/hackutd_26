/-!
# Safe Signal: a machine-checked model of the decision policy

Proves R1, R5 and R6 from `context/rules.md` (and R7 as a bonus) on a small model of
`services/agents/decision/decide.py`. Core Lean only, no Mathlib:

    lean proofs/SafeSignal.lean

What this does and doesn't show: the theorems are about this model, not about the Python itself. The model
mirrors the shape of `decide()`. Thresholds are parameters, so the proofs survive any retuning of `config.py`.

Scores are per-mille naturals (0 to 1000) standing in for Python's floats in [0, 1].
-/

namespace SafeSignal

inductive Level where
  | none | nudge | whisper | alert
  deriving DecidableEq, Repr

def Level.rank : Level → Nat
  | .none => 0
  | .nudge => 1
  | .whisper => 2
  | .alert => 3

structure Risk where
  score : Nat
  level : Level
  deriving DecidableEq, Repr

def zeroRisk : Risk := ⟨0, .none⟩

def maxLevel (a b : Level) : Level :=
  if a.rank ≤ b.rank then b else a

/-- `contracts.state.merge_risk` -/
def merge (old new : Risk) : Risk :=
  ⟨max old.score new.score, maxLevel old.level new.level⟩

/-- `config.py`. Any values work, as long as the R7 cap sits under whisper and the ladder is ordered. -/
structure Thresholds where
  nudge : Nat
  whisper : Nat
  alert : Nat
  cap : Nat
  capBelowWhisper : cap < whisper
  whisperBelowAlert : whisper ≤ alert

def levelFor (t : Thresholds) (s : Nat) : Level :=
  if t.alert ≤ s then .alert
  else if t.whisper ≤ s then .whisper
  else if t.nudge ≤ s then .nudge
  else .none

/-- Noisy-OR on per-mille scores: 1 - (1-a)(1-b) rewritten as a + (1-a)b. -/
def orScore (a b : Nat) : Nat := a + (1000 - a) * b / 1000

def orAll (xs : List Nat) : Nat := xs.foldl orScore 0

/-- A Call Guardian flag: its per-mille contribution, and whether it can lift the R7 cap
    (a confident gift_cards, safe_account or remote_access flag). -/
structure FlagIn where
  weight : Nat
  liftsCap : Bool

/-- What `decide()` sees. A missing caller is modeled as `paused`: both return the previous risk. -/
structure State where
  emergency : Bool
  paused : Bool
  trusted : Bool
  signals : List Nat
  flags : List FlagIn
  prev : Risk

def detScore (s : State) : Nat := orAll s.signals
def llmScore (s : State) : Nat := orAll (s.flags.map FlagIn.weight)
def capApplies (s : State) : Bool := s.trusted && !(s.flags.any FlagIn.liftsCap)

def ruleScore (t : Thresholds) (s : State) : Nat :=
  let c := orScore (detScore s) (llmScore s)
  if capApplies s then min c t.cap else c

def ruleRisk (t : Thresholds) (s : State) : Risk :=
  ⟨ruleScore t s, levelFor t (ruleScore t s)⟩

/-- The decision rule, in the same order as `decide()`. -/
def decide (t : Thresholds) (s : State) : Risk :=
  if s.emergency then zeroRisk
  else if s.paused then s.prev
  else merge s.prev (ruleRisk t s)

/-- New evidence during a call: more signals, more flags. -/
structure Evidence where
  signals : List Nat
  flags : List FlagIn

/-- One step of a call: add the evidence, decide, and carry the risk forward. -/
def advance (t : Thresholds) (s : State) (e : Evidence) : State :=
  let s' := { s with signals := s.signals ++ e.signals, flags := s.flags ++ e.flags }
  { s' with prev := decide t s' }

/-- Replay a whole call. -/
def run (t : Thresholds) (s : State) : List Evidence → State
  | [] => s
  | e :: es => run t (advance t s e) es

/-! ## Helper lemmas -/

theorem orScore_ge_left (a b : Nat) : a ≤ orScore a b := by
  unfold orScore; omega

theorem orScore_zero (a : Nat) : orScore a 0 = a := by
  simp [orScore]

/-- Scores stay in range: noisy-OR of two valid per-mille scores is a valid per-mille score. -/
theorem orScore_le_scale (a b : Nat) (ha : a ≤ 1000) (hb : b ≤ 1000) : orScore a b ≤ 1000 := by
  unfold orScore
  have h : (1000 - a) * b / 1000 ≤ 1000 - a :=
    Nat.div_le_of_le_mul (by
      have := Nat.mul_le_mul_left (1000 - a) hb
      omega)
  omega

theorem levelFor_mono (t : Thresholds) {a b : Nat} (h : a ≤ b) :
    (levelFor t a).rank ≤ (levelFor t b).rank := by
  unfold levelFor
  repeat' split
  all_goals first | omega | simp [Level.rank]

theorem maxLevel_rank_left (a b : Level) : a.rank ≤ (maxLevel a b).rank := by
  unfold maxLevel; split <;> omega

theorem maxLevel_rank_right (a b : Level) : b.rank ≤ (maxLevel a b).rank := by
  unfold maxLevel; split <;> omega

theorem maxLevel_mono (p : Level) {a b : Level} (h : a.rank ≤ b.rank) :
    (maxLevel p a).rank ≤ (maxLevel p b).rank := by
  unfold maxLevel
  repeat' split
  all_goals omega

theorem merge_keeps_old (old new : Risk) :
    old.score ≤ (merge old new).score ∧ old.level.rank ≤ (merge old new).level.rank :=
  ⟨Nat.le_max_left _ _, maxLevel_rank_left _ _⟩

theorem merge_mono (p : Risk) {a b : Risk} (hs : a.score ≤ b.score) (hl : a.level.rank ≤ b.level.rank) :
    (merge p a).score ≤ (merge p b).score ∧ (merge p a).level.rank ≤ (merge p b).level.rank := by
  constructor
  · simp only [merge]; omega
  · exact maxLevel_mono _ hl

/-! ## R1: never interfere with an emergency call -/

/-- On an emergency number the decision is zero risk at `none`, whatever the evidence or history. -/
theorem r1_emergency_is_none (t : Thresholds) (s : State) (h : s.emergency = true) :
    decide t s = zeroRisk ∧ (decide t s).level = .none := by
  simp [decide, h, zeroRisk]

theorem advance_keeps_emergency (t : Thresholds) (s : State) (e : Evidence) :
    (advance t s e).emergency = s.emergency := rfl

/-- R1 over a whole call: after any evidence at all, an emergency call is still at `none`. -/
theorem r1_whole_call (t : Thresholds) (es : List Evidence) :
    ∀ s : State, s.emergency = true → s.prev = zeroRisk → (run t s es).prev.level = .none := by
  induction es with
  | nil =>
    intro s _ hp
    simp [run, hp, zeroRisk]
  | cons e es ih =>
    intro s he _
    simp only [run]
    apply ih
    · rw [advance_keeps_emergency]; exact he
    · simp [advance, decide, he]

/-! ## R5: risk only goes up during a call -/

/-- One decision never lowers the previous score or level (emergency calls are always zero, see R1). -/
theorem r5_decide_never_lowers (t : Thresholds) (s : State) (h : s.emergency = false) :
    s.prev.score ≤ (decide t s).score ∧ s.prev.level.rank ≤ (decide t s).level.rank := by
  unfold decide
  simp only [h, Bool.false_eq_true, ite_false]
  split
  · exact ⟨Nat.le_refl _, Nat.le_refl _⟩
  · exact merge_keeps_old _ _

theorem r5_advance_never_lowers (t : Thresholds) (s : State) (e : Evidence) (h : s.emergency = false) :
    s.prev.score ≤ (advance t s e).prev.score ∧
    s.prev.level.rank ≤ (advance t s e).prev.level.rank := by
  exact r5_decide_never_lowers t { s with signals := s.signals ++ e.signals, flags := s.flags ++ e.flags } h

/-- R5 over a whole call: at the end, score and level are at least where the call started. -/
theorem r5_whole_call (t : Thresholds) (es : List Evidence) :
    ∀ s : State, s.emergency = false →
      s.prev.score ≤ (run t s es).prev.score ∧ s.prev.level.rank ≤ (run t s es).prev.level.rank := by
  induction es with
  | nil =>
    intro s _
    exact ⟨Nat.le_refl _, Nat.le_refl _⟩
  | cons e es ih =>
    intro s h
    have step := r5_advance_never_lowers t s e h
    have rest := ih (advance t s e) (by rw [advance_keeps_emergency]; exact h)
    exact ⟨Nat.le_trans step.1 rest.1, Nat.le_trans step.2 rest.2⟩

/-! ## R6: an LLM can raise risk, never lower it below the deterministic score -/

/-- The same state with every LLM flag removed: the deterministic baseline. -/
def noFlags (s : State) : State := { s with flags := [] }

theorem ruleScore_flags_ge (t : Thresholds) (s : State) :
    ruleScore t (noFlags s) ≤ ruleScore t s := by
  have hbase : orScore (detScore (noFlags s)) (llmScore (noFlags s)) = detScore s := by
    simp [llmScore, noFlags, orAll, detScore, orScore_zero]
  have hge : detScore s ≤ orScore (detScore s) (llmScore s) := orScore_ge_left _ _
  unfold ruleScore
  simp only [hbase]
  by_cases htr : s.trusted = true
  · have hcap0 : capApplies (noFlags s) = true := by simp [capApplies, noFlags, htr]
    rw [hcap0]
    by_cases hc : capApplies s = true <;> simp [hc] <;> omega
  · have hcap0 : capApplies (noFlags s) = false := by simp [capApplies, noFlags, htr]
    have hc : capApplies s = false := by simp [capApplies, htr]
    rw [hcap0, hc]
    simpa using hge

/-- R6: however the LLM's flags look, the decision is at least the decision without them. -/
theorem r6_llm_never_lowers (t : Thresholds) (s : State) :
    (decide t (noFlags s)).score ≤ (decide t s).score ∧
    (decide t (noFlags s)).level.rank ≤ (decide t s).level.rank := by
  have hs := ruleScore_flags_ge t s
  have hrule : (ruleRisk t (noFlags s)).score ≤ (ruleRisk t s).score := hs
  have hlevel : (ruleRisk t (noFlags s)).level.rank ≤ (ruleRisk t s).level.rank :=
    levelFor_mono t hs
  unfold decide
  have hE : (noFlags s).emergency = s.emergency := rfl
  have hP : (noFlags s).paused = s.paused := rfl
  have hPrev : (noFlags s).prev = s.prev := rfl
  rw [hE, hP, hPrev]
  split
  · exact ⟨Nat.le_refl _, Nat.le_refl _⟩
  · split
    · exact ⟨Nat.le_refl _, Nat.le_refl _⟩
    · exact merge_mono _ hrule hlevel

/-! ## R7 (bonus): a call the customer dialed to a verified number stays at or below nudge -/

theorem levelFor_cap_le_nudge (t : Thresholds) {x : Nat} (h : x ≤ t.cap) :
    (levelFor t x).rank ≤ Level.nudge.rank := by
  have h1 := t.capBelowWhisper
  have h2 := t.whisperBelowAlert
  unfold levelFor
  repeat' split
  all_goals first | omega | simp [Level.rank]

theorem r7_trusted_stays_quiet (t : Thresholds) (s : State)
    (hemg : s.emergency = false) (htr : s.trusted = true)
    (hnolift : s.flags.any FlagIn.liftsCap = false)
    (hprev : s.prev.level.rank ≤ Level.nudge.rank) :
    (decide t s).level.rank ≤ Level.nudge.rank := by
  have hcap : capApplies s = true := by simp [capApplies, htr, hnolift]
  have hscore : ruleScore t s ≤ t.cap := by
    simp only [ruleScore, hcap, ite_true]
    omega
  have hlevel : (ruleRisk t s).level.rank ≤ Level.nudge.rank := levelFor_cap_le_nudge t hscore
  unfold decide
  simp only [hemg, Bool.false_eq_true, ite_false]
  split
  · exact hprev
  · simp only [merge, maxLevel]
    split <;> omega

end SafeSignal

/-! Print every axiom each headline theorem relies on (`lean` output shows no `sorryAx`). -/
#print axioms SafeSignal.r1_whole_call
#print axioms SafeSignal.r5_whole_call
#print axioms SafeSignal.r6_llm_never_lowers
#print axioms SafeSignal.r7_trusted_stays_quiet
