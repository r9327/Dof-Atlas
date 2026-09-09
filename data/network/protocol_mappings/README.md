# Dofus Atlas — protocol mappings

This directory is reserved for **reviewed runtime protocol mappings** bound to an exact Dofus Unity build fingerprint.

Do not place packet captures, discovery reports, consensus reports, guessed aliases or stale protocol files here.

## Runtime rule

Network progression is fail-closed.

A mapping is usable only when:

1. `build_sha256` exactly matches the active local Unity build fingerprint derived from `GameAssembly.dll` + `global-metadata.dat`;
2. exactly one valid mapping exists for that fingerprint;
3. it provides `character_identified` plus the abstract `quest_completion` capability;
4. `quest_completion` comes from an explicitly reviewed provider such as one exact completion event or one exact finished-quest snapshot;
5. the decoder receives server-to-client traffic only;
6. decoded character/quest IDs are still validated by the existing Atlas catalogue/progression services before persistent mutation.

There is intentionally no "latest known mapping" fallback and no cross-build alias reuse.

## Integrated Dofus 3.6.10.10 path

The application contains a reviewed **non-authoritative** 3.6.10.10 profile based on the reconstructed current client protocol plus public real-wire observations:

- roster: `type.ankama.com/kvi`;
- selected character: `type.ankama.com/kva`;
- system information message: `type.ankama.com/lqn`;
- quest-completed semantic: information type `0`, message id `56`, quest id in parameter `0`.

The profile is deliberately stored in code, not as a runtime mapping. Public/version evidence by itself is never sufficient to mutate progression.

### In-app calibration

The Home screen exposes **Calibrer le suivi réseau** after the Quêtes/Succès context is ready and no exact verified mapping is available.

Calibration:

1. fingerprints the exact local Dofus build;
2. passively observes server-to-client traffic only;
3. correlates `kvi → kva` in the same transport session and resolves the Dofus character name to an existing Atlas `slot:N`;
4. requires at least **two distinct known Atlas quest IDs** observed through the reviewed `lqn / 56` semantic;
5. invalidates evidence if the local build changes;
6. writes no quest/success/guide progression while calibration is running;
7. stops its capture reader before any mapping installation;
8. binds the calibration certificate to the exact local build and a SHA-256 digest of the in-code reviewed profile;
9. installs the mapping atomically only when all calibration gates pass.

After installation, the application composes and starts the normal verified network runtime. The calibrated mapping is persisted in this directory for the exact build, so a later Atlas start may use it without recalibrating while the Dofus build fingerprint remains identical.

### Live progression

Once the verified runtime is active:

```text
Dofus server event
    → exact-build decoder
    → verified character/session route
    → existing QuestProgressService
    → existing AchievementProgressService synchronization
    → Guide Ultime derives its state from the same progression truth
```

No second progression store is created.

The Qt bridge drains only lightweight result/status queues. Fingerprinting, capture bootstrap and network reads stay off the UI thread. The currently visible Home/Encyclopédie progression is refreshed after a changed quest result; hidden Encyclopédie tabs use their existing `refresh_external_progress()` contract when opened.

The network runtime remains active when Atlas is merely hidden to the system tray. `QApplication.aboutToQuit` stops the network coordinator/readers on an actual application quit.

## Current `lqn` safety contract

The current completion decoder accepts only:

- exact reviewed `type_url`;
- server-to-client direction;
- exact local build fingerprint;
- message id `56` exactly once;
- information type `0` (explicit zero or proto3-omitted zero);
- configured quest-id parameter index;
- strict positive ASCII decimal quest id.

Message ids `54` and `55` (quest start/update semantics) cannot complete a quest. Wrong-build, wrong-direction, malformed, duplicated or nonnumeric payloads fail closed.

## Optional finished-quests snapshot

Atlas also contains a specialized additive `finished_quests_snapshot` decoder/runtime path for a future exactly proven `QuestsEvent` mapping.

A snapshot may only add known completed quests. Absence from a snapshot never uncompletes local progression. Snapshot batch application performs one coordinated quest-progress mutation and one Success synchronization instead of one disk write per quest.

No current snapshot opcode is installed merely from historical aliases.

## Capture-free local status

The active local build and exact mapping state can still be inspected without opening capture:

```powershell
py -3.13 -m app.network.protocol_status
```

The command never mutates progression. Typical reasons include:

- `no_window_handles`;
- `build_fingerprint_unavailable`;
- `mapping_no_exact_match`;
- `mapping_ambiguous_exact_match`;
- `mapping_missing_required_events`;
- `mapping_ready_not_started`.

`mapping_ready_not_started` means only that an exact local mapping is structurally eligible for runtime composition.

## Advanced payload-free discovery path

The older/general discovery workflow remains available for future protocol changes and additional events. It uses known local values only in memory and stores metadata-only evidence:

- no packet payload storage;
- no IP addresses or ports;
- no session identifiers;
- no character names in reports;
- no expected quest/achievement IDs in reports.

Both current `type.ankama.com/...` and legacy `ankama.com/...` Ankama type URL forms are accepted by the evidence parser; foreign domains are rejected.

Each observation has a random `capture_id` so the same run cannot be counted twice as independent evidence. Reports remain explicitly non-authoritative:

```text
purpose = protocol_mapping_discovery_evidence_only
authoritative_mapping = false
```

Store generated evidence under `.cache/` and run capture commands from an Administrator terminal because Windows `SIO_RCVALL` requires elevation.

Example character observations:

```powershell
$EvidenceDir = ".\.cache\dofus_atlas\network_evidence"
New-Item -ItemType Directory -Force $EvidenceDir | Out-Null

py -3.13 -m app.network.discovery_probe --event character_identified --slot 1 --seconds 15 > "$EvidenceDir\character_1.json"
py -3.13 -m app.network.discovery_probe --event character_identified --slot 2 --seconds 15 > "$EvidenceDir\character_2.json"
py -3.13 -m app.network.discovery_consensus "$EvidenceDir\character_1.json" "$EvidenceDir\character_2.json" > "$EvidenceDir\character_consensus.json"
```

Example direct quest-completion observations for a future/direct scalar mapping:

```powershell
py -3.13 -m app.network.discovery_probe --event quest_completed --id <QUEST_ID> --seconds 15 > "$EvidenceDir\quest_1.json"
py -3.13 -m app.network.discovery_probe --event quest_completed --id <OTHER_QUEST_ID> --seconds 15 > "$EvidenceDir\quest_2.json"
py -3.13 -m app.network.discovery_consensus "$EvidenceDir\quest_1.json" "$EvidenceDir\quest_2.json" > "$EvidenceDir\quest_consensus.json"
```

Two genuinely distinct observations and, for quest completion, two different real quest IDs are required for meaningful consensus.

## Advanced deobfuscation / scalar mapping audit

The historical consensus + `dofus-deobfs` path remains useful for direct scalar message mappings and future protocol research. It must not be used to pretend that a specialized current provider such as `lqn / 56` is the historical `QuestValidatedEvent`.

A deobfuscation bundle binds generated report bytes to an exact local build fingerprint:

```powershell
py -3.13 -m app.network.deobfs_bundle `
  --output "$EvidenceDir\deobfs_bundle.json" `
  --report <DEOBFS_DIR>\reports\enum_matches.txt `
  --report <DEOBFS_DIR>\reports\structure_matches.txt
```

The bundle stores build/report digests only; no raw network content or account information.

Lower-level semantic and mapping audits remain available:

```powershell
py -3.13 -m app.network.deobfs_audit --consensus "$EvidenceDir\character_consensus.json" `
  --report <DEOBFS_DIR>\reports\enum_matches.txt `
  --report <DEOBFS_DIR>\reports\structure_matches.txt `
  --expected-message CharacterSelectionEvent
```

```powershell
py -3.13 -m app.network.mapping_audit --mapping .\candidate_mapping.json "$EvidenceDir\character_consensus.json" "$EvidenceDir\quest_consensus.json"
```

```powershell
py -3.13 -m app.network.readiness_audit --mapping .\candidate_mapping.json `
  --bundle "$EvidenceDir\deobfs_bundle.json" `
  --report <DEOBFS_DIR>\reports\enum_matches.txt `
  --report <DEOBFS_DIR>\reports\structure_matches.txt `
  "$EvidenceDir\character_consensus.json" "$EvidenceDir\quest_consensus.json"
```

These scalar audits intentionally reject specialized/correlated providers instead of falsely certifying them through historical scalar semantics.

## Explicit legacy/scalar installation

For a manually reviewed scalar candidate, the explicit installer remains available:

```powershell
py -3.13 -m app.network.mapping_install --candidate .\candidate_mapping.json `
  --bundle "$EvidenceDir\deobfs_bundle.json" `
  --report <DEOBFS_DIR>\reports\enum_matches.txt `
  --report <DEOBFS_DIR>\reports\structure_matches.txt `
  "$EvidenceDir\character_consensus.json" "$EvidenceDir\quest_consensus.json"
```

It re-runs readiness, checks candidate bytes did not change during audit, refuses ambiguous/different exact-build mappings, writes atomically and re-selects the installed mapping. It never starts capture itself.

## Minimal direct-scalar mapping example

This example is illustrative only and must not be copied as current-build truth:

```json
{
  "schema_version": 1,
  "game_version": "EXACT_VERIFIED_VERSION",
  "build_sha256": "64_HEX_CHARACTERS",
  "messages": {
    "type.ankama.com/EXACT_ALIAS": {
      "event_type": "quest_completed",
      "fields": [
        {
          "output_name": "quest_id",
          "path": [1],
          "kind": "positive_int",
          "required": true
        }
      ]
    }
  }
}
```

Never copy an alias, protobuf path or semantic provider from an older Dofus build merely because its shape looks similar.
