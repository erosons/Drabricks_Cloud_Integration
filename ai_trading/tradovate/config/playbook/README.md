# Playbook Cards — the G1 entry ticket

One YAML card per strategy module. A card is the **written contract** that gate G1
of the strategy lifecycle requires (docs/README.md §8): a stated goal and fully
mechanical entry/exit rules, with every known ambiguity either resolved or listed
as an explicit blocker.

## How the cards plug into the lifecycle

- `research/gatekeeper.py` refuses the `idea → limited_test` transition for any
  `(module, product)` pair whose card is missing, or whose `ambiguities_open`
  list is non-empty.
- The card is versioned in git; each `strategy_lifecycle` row records the card's
  commit hash as its G1 evidence.
- `status_requested` is a **request only** — actual state lives exclusively in
  the `strategy_lifecycle` table, written by the gatekeeper. No config or card
  edit can promote a strategy.

## Division of truth (no duplication)

| Lives in the card | Lives in `config.yaml` | Lives in the DB |
|---|---|---|
| Goal, edge hypothesis, archetype | Tunable params (`strategies.<module>.params`) | Lifecycle state |
| Mechanical rule statements | Shared-service settings | Gate evidence run IDs |
| Ambiguities (open/resolved) | `enabled:` (factory eligibility) | Retirement reasons |
| Risks, guards, prerequisites | Per-product `risk:`/`overrides:` (products.yaml) | |

## Card schema

```yaml
module:            # must match strategies.<module> in config.yaml
skills: []         # skill numbers in docs/trading-strategies-SKILL.md
archetype:         # one of the ~9 archetypes (SKILL.md, deck-wide note at Skill 30)
tier:              # scalp | swing | gate
priority:          # 1 | 2 | 3 (build order from the playbook)
status_requested:  # idea | limited_test  (request only; DB decides)
goal:              # edge_hypothesis, markets, timeframe, session,
                   # target_ret_dd (G4 floor), expected_frequency
mechanics:         # bias/entry/stop/targets/exit/regime_gate — fully mechanical,
                   # each rule referencing shared services where applicable
prerequisites: []  # empirical studies required before G2/G3 (not rule ambiguities)
risks_and_guards: []
ambiguities_open: []      # non-empty ⇒ G1 blocked
ambiguities_resolved: []  # record the resolution + source
```

## Coverage notes

- The 23 cards cover every module in `config.yaml strategies:`. Skills excluded
  from automation (14 Gann, 18 Renko, 20 Elliott, skill-5 martingale sizing) have
  no cards — the exclusions and reasons are recorded in `config.yaml` comments
  and SKILL.md.
- Skills 33–39 (added to SKILL.md from the source book) intentionally have no
  new cards: 33/34/37 are confirmation-filter or Fib variants of existing
  pullback modules, 35 is a fourth detector for the compression module
  (`volume_breakout`/`bb_squeeze_breakout`/`vcp_breakout` family), 36 is a
  regime-filter candidate to A/B against the EMA gate, 38 is a parameter variant
  of `supertrend_rsi`, and 39 (macro rate-decision overlay) is a separate track
  outside this bot. If any of them earns a standalone build, it gets a card then.
