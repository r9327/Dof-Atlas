# Structured Guide contracts — Phase 7E

The new semantic boundary is `tools.guide_integrity_contracts`.

Runtime/UI producers can normalize action dictionaries into `GuideAction` values. Guide Integrity validates those values without scraping rendered text. The first deterministic contracts cover drop purchase alternatives, preparation/action duplication, positive quantities, natural acquisition vs preparation, and grouping consecutive interactions with the same canonical NPC/map.

Existing text heuristics remain compatibility diagnostics until each producer emits equivalent structured data. They must not be promoted blindly from REVIEW to HARD.
