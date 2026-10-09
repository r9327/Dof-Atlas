from __future__ import annotations

"""Doctor overlay on the *existing* exact-SHA Graphify export.

An independent local HTML viewer; no server, CDN, Qt runtime or graph rebuild.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import Any

MAX_NODES = 15000
MAX_LINKS = 50000
MAX_SOURCE_INSPECTION_FILES = 16
MAX_SOURCE_SIGNALS_PER_FILE = 6


def _domain(path: str) -> str:
    parts = path.split("/")
    if len(parts) > 3 and parts[:2] == ["app", "modules"]:
        return "/".join(parts[:3])
    return "/".join(parts[:2]) if len(parts) > 1 else path


def compact_graph(graph: dict[str, Any], audit: dict[str, Any],
                  trace: dict[str, Any] | None = None,
                  inspection: dict[str, Any] | None = None,
                  lineage: dict[str, Any] | None = None,
                  comparison: dict[str, Any] | None = None) -> dict[str, Any]:
    nodes = graph.get("nodes", [])[:MAX_NODES]
    indexed = {item["id"]: number for number, item in enumerate(nodes)}
    # Stable source-file comparisons, never match ephemeral Leiden community IDs.
    source_changes: dict[str, dict[str, Any]] = {}
    if comparison is not None:
        if comparison.get("candidate_sha") != graph.get("built_at_commit"):
            raise ValueError("Baseline comparison does not match graph SHA")
        def change(path: str) -> dict[str, Any]:
            return source_changes.setdefault(path, {
                "added_imports": [], "removed_imports": [],
                "new_orphan": False, "new_weak": False,
            })
        for field, kind in (("new_import_file_pairs", "added_imports"),
                            ("removed_import_file_pairs", "removed_imports")):
            for pair in comparison.get(field, [])[:80]:
                if isinstance(pair, (list, tuple)) and len(pair) == 2 and all(
                    isinstance(value, str) for value in pair
                ):
                    change(pair[0])[kind].append(pair[1])
        for field, kind in (("new_orphan_symbols", "new_orphan"),
                            ("new_weak_symbols", "new_weak")):
            for item in comparison.get(field, [])[:80]:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    change(item["path"])[kind] = True
    file_reasons: dict[str, list[str]] = {}
    review_by_file: dict[str, set[str]] = {}
    for field, reason, category in (

        ("orphan_nodes", "Isolated Graphify node; not proof of dead code", "orphan"),
        ("weak_production_candidates", "Weakly connected candidate", "weak"),
        ("high_fanout_files", "High fanout coupling candidate", "fanout"),
        ("blocking_findings", "Doctor source-confirmed forbidden dependency", "forbidden"),
    ):
        for item in audit.get(field, []):
            path = item.get("file") or item.get("path") or item.get("source")
            if isinstance(path, str):
                values = file_reasons.setdefault(path, [])
                if reason not in values:
                    values.append(reason)
                review_by_file.setdefault(path, set()).add(category)
    for community in audit.get("isolated_communities", []):
        # A disconnected community does not imply its containing Python file
        # lacks imports/calls from other communities. Make this explicit.
        linked = set(community.get("sample_linked_production_files", []))
        for path in community.get("sample_source_files", [])[:8]:
            if not isinstance(path, str) or not path.startswith("app/"):
                continue
            reason = ("Graphify subcommunity isolated; file linked elsewhere"
                      if path in linked else
                      "Graphify subcommunity isolated; file reachability unproven")
            values = file_reasons.setdefault(path, [])
            if reason not in values:
                values.append(reason)
            review_by_file.setdefault(path, set()).add("island")
    # Expose Doctor's existing prioritized remediation plan in the graph
    # inspector, without promoting speculative candidate findings to P0.
    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    file_actions: dict[str, dict[str, str]] = {}
    for task in (audit.get("remediation_plan") or {}).get("tasks", []):
        level = task.get("priority")
        if level not in priority_rank:
            continue
        for source_path in task.get("paths", [])[:20]:
            if not isinstance(source_path, str):
                continue
            before = file_actions.get(source_path)
            if before is None or priority_rank[level] < priority_rank[before["priority"]]:
                file_actions[source_path] = {
                    "priority": level, "kind": str(task.get("kind") or ""),
                    "action": str(task.get("action") or ""),
                }
    # Read-only AST source evidence is separate from Graphify predictions and
    # runtime observations. Only explicitly scanned files can show findings.
    source_evidence: dict[str, list[dict[str, Any]]] = {}
    if isinstance(inspection, dict):
        def add(path: Any, line: Any, kind: str, subject: Any) -> None:
            if not isinstance(path, str):
                return
            bucket = source_evidence.setdefault(path, [])
            if len(bucket) < MAX_SOURCE_SIGNALS_PER_FILE:
                bucket.append({"line": str(line or ""), "kind": kind,
                               "subject": str(subject or "")[:180],
                               "confidence": "STATIC_SOURCE_REVIEW_ONLY"})
        for key, kind in (
            ("missing_internal_import_candidates", "Missing internal import candidate"),
            ("silent_exceptions", "Swallowed exception pattern"),
            ("data_lineage_candidates", "Literal JSON string reference"),
        ):
            for item in inspection.get(key, [])[:80]:
                if isinstance(item, dict):
                    add(item.get("path"), item.get("line"), kind,
                        item.get("module") or item.get("data_reference") or "")
        for group in inspection.get("near_duplicate_candidates", [])[:80]:
            if isinstance(group, dict):
                for item in group.get("occurrences", [])[:16]:
                    if isinstance(item, dict):
                        add(item.get("path"), item.get("line"),
                            "Similar AST shape (not semantic equality)", item.get("symbol"))
    if isinstance(lineage, dict):
        for entry in lineage.get("references", [])[:80]:
            if not isinstance(entry, dict):
                continue
            path = entry.get("source")
            label = entry.get("data_reference")
            for ui in entry.get("possible_ui_importers", [])[:8]:
                if not isinstance(ui, dict):
                    continue
                ui_path = ui.get("path")
                if not isinstance(ui_path, str):
                    continue
                existing = source_evidence.setdefault(ui_path, [])
                if len(existing) >= MAX_SOURCE_SIGNALS_PER_FILE:
                    continue
                existing.append({
                    "line": "", "kind": "Possible JSON reference via import chain",
                    "subject": f"{path} : {label}"[:180],
                    "confidence": "STATIC_IMPORT_PATH_NOT_RUNTIME_FLOW",
                })
    trace_status = "NOT_PROVIDED"
    runtime_pairs: set[tuple[str, str]] = set()
    observed_lifecycle: dict[str, Any] = {"status": "NOT_TRUSTED"}
    trace_events = trace.get("events") if isinstance(trace, dict) else None
    if isinstance(trace, dict):
        trace_sha = trace.get("candidate_sha")
        graph_sha = graph.get("built_at_commit")
        if (isinstance(trace_sha, str) and isinstance(graph_sha, str)
                and len(graph_sha) == 40 and trace_sha == graph_sha
                and trace.get("worktree_clean") is True
                and not trace.get("truncated")
                and isinstance(trace_events, list) and len(trace_events) <= 50000
                and all(isinstance(row, dict) for row in trace_events)):
            trace_status = "MATCHED"
            from .runtime_observation import summarize_runtime_lifecycle
            observed_lifecycle = summarize_runtime_lifecycle(trace)
            runtime_pairs = {
                (row["source"], row["target"])
                for row in trace.get("events", [])
                if row.get("type") == "python_call_edge"
                and isinstance(row.get("source"), str)
                and isinstance(row.get("target"), str)
            }
        else:
            trace_status = "STALE_OR_INCOMPLETE"
    elif trace is not None:
        trace_status = "STALE_OR_INCOMPLETE"
    qt_pairs: set[tuple[str, str]] = set()
    if trace_status == "MATCHED" and trace is not None:
        qt_pairs = {
            (row["source"], row["target"])
            for row in trace.get("events", [])
            if row.get("type") == "qt_signal_connect_returned"
            and isinstance(row.get("source"), str)
            and isinstance(row.get("target"), str)
        }
    symbol_calls: list[dict[str, Any]] = []
    if trace_status == "MATCHED" and trace is not None:
        symbol_calls = [
            {field: row[field] for field in (
                "source", "target", "caller_symbol", "callee_symbol",
                "caller_line", "callee_line", "confidence",
            ) if field in row}
            for row in trace.get("events", [])
            if row.get("type") == "python_symbol_call"
            and isinstance(row.get("source"), str)
            and isinstance(row.get("target"), str)
        ][:384]
    open_worker_files = {row["source"] for row in observed_lifecycle.get("worker_starts_unpaired", [])}
    cache_released_files = set(observed_lifecycle.get("cache_release_sources", []))
    observed_files = {file for pair in runtime_pairs for file in pair}
    qt_files = {file for pair in qt_pairs for file in pair}
    qt_sites: set[str] = set()
    if trace_status == "MATCHED" and trace is not None:
        qt_sites = {row["source"] for row in trace.get("events", [])
                    if row.get("type") == "qt_c_call_site"
                    and isinstance(row.get("source"), str)}
    # Existing source-backed community cohesion audit is advisory. Store it
    # once per community, never duplicate the same row for every symbol node.
    cohesion = audit.get("community_cohesion") or {}
    boundary_rows = cohesion.get("candidates", []) if isinstance(cohesion, dict) else []
    community_reviews = [
        {key: row[key] for key in (
            "community", "production_files", "internal_extracted_edges",
            "external_extracted_edges", "classification", "automatic_merge"
        ) if key in row}
        for row in boundary_rows[:80] if isinstance(row, dict)
    ]
    selected = []
    for item in nodes:
        file = item.get("source_file") or ""
        selected.append({
            "id": str(item["id"]), "label": str(item.get("label") or ""),
            "file": file, "domain": _domain(file), "community": item.get("community"),
            "line": str(item.get("source_location") or ""),
            "reasons": file_reasons.get(file, []),
            "review_categories": sorted(
                review_by_file.get(file, set())
                | ({"ast"} if source_evidence.get(file) else set())
                | ({"doctor"} if file_actions.get(file) else set())
                | ({"worker"} if file in open_worker_files else set())
            ),
            "source_evidence": source_evidence.get(file, []),
            "snapshot_changes": source_changes.get(file),
            "doctor_task": file_actions.get(file),
            "runtime_observed": file in observed_files,
            "qt_call_site_observed": file in qt_sites,
            "qt_connection_observed": file in qt_files,
            "worker_start_unpaired_at_trace_end": file in open_worker_files,
            "cache_release_observed": file in cache_released_files,
        })
    edges = []
    for link in graph.get("links", []):
        if len(edges) >= MAX_LINKS:
            break
        a, b = indexed.get(link.get("source")), indexed.get(link.get("target"))
        if a is not None and b is not None:
            edges.append({"a": a, "b": b, "relation": str(link.get("relation") or "")})
    # Runtime calls are separate edges; they do not fabricate static imports.
    first_by_file: dict[str, int] = {}
    for number, row in enumerate(selected):
        first_by_file.setdefault(row["file"], number)
    for a, b in sorted(runtime_pairs):
        if len(edges) >= MAX_LINKS:
            break
        if a in first_by_file and b in first_by_file:
            edges.append({"a": first_by_file[a], "b": first_by_file[b],
                          "relation": "OBSERVED_PYTHON_CALL", "observed": True})
    for a, b in sorted(qt_pairs):
        if len(edges) >= MAX_LINKS:
            break
        if a in first_by_file and b in first_by_file:
            edges.append({"a": first_by_file[a], "b": first_by_file[b],
                          "relation": "QT_CONNECT_RETURNED", "observed": True})
    return {
        "nodes": selected, "edges": edges, "candidate_sha": graph.get("built_at_commit"),
        "snapshot_diff": comparison,
        "community_review_candidates": community_reviews,
        "community_review_total": int(cohesion.get("candidate_count") or 0)
        if isinstance(cohesion, dict) else 0,
        "trace_status": trace_status, "observed_runtime_file_pairs": len(runtime_pairs),
        "observed_lifecycle": observed_lifecycle,
        "observed_symbol_calls": symbol_calls,
        "source_inspection_status": (inspection or {}).get("status", "NOT_RUN"),
        "json_lineage_review_leads": (lineage or {}).get("references_with_ui_importers", 0),
        "json_lineage_runtime_proven": False,
        "source_inspection_files": len((inspection or {}).get("paths_inspected", [])),
        "source_inspection_truncated": bool((inspection or {}).get("truncated")),
        "symbol_calls_bounded": bool(isinstance(trace, dict) and trace.get("symbol_edges_truncated")),
        "qt_call_site_files": len(qt_sites),
        "raw_nodes": len(graph.get("nodes", [])), "raw_links": len(graph.get("links", [])),
        "truncated": len(graph.get("nodes", [])) > MAX_NODES or len(graph.get("links", [])) > MAX_LINKS,
        "disclaimer": "A flagged node is not proof of dead code; native runtime connections require trace evidence.",
    }


HTML = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Doctor Atlas — Graphify interactif</title>
<style>
:root{font:14px system-ui,sans-serif;color-scheme:dark;background:#0d1420;color:#ecf1fc}
*{box-sizing:border-box}body{margin:0}header{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding:12px 18px;border-bottom:1px solid #29354c}
h1{font-size:17px;margin:0 20px 0 0}input,select,button{background:#172437;color:#fff;border:1px solid #41526f;border-radius:6px;padding:7px}
main{display:grid;grid-template-columns:minmax(0,1fr) 330px;height:calc(100vh - 64px)}
canvas{width:100%;height:100%;touch-action:none;cursor:grab}
aside{border-left:1px solid #29354c;padding:16px;overflow:auto;overflow-wrap:anywhere}
small{color:#9baec9}a{color:#8dc9ff}li{margin-bottom:8px} .warning{color:#ffbd6b}
@media(max-width:850px){main{grid-template-columns:1fr;height:auto}canvas{height:65vh}aside{border-left:none;border-top:1px solid #29354c}}
</style></head><body>
<header><h1>Doctor Atlas × Graphify</h1>
<input id="search" type="search" placeholder="Chercher symbole ou fichier" aria-label="Rechercher">
<select id="domain" aria-label="Domaine"><option value="">Tous les domaines</option></select>
<select id="community" aria-label="Communauté Graphify"><option value="">Toutes les communautés</option></select>
<select id="relation" aria-label="Relation du graphe"><option value="">Toutes les relations</option></select>
<select id="priority" aria-label="Priorité Doctor"><option value="">Toutes priorités</option><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select>
<select id="reviewKind" aria-label="Catégorie de diagnostic Doctor"><option value="">Tous les diagnostics</option></select>
<label><input id="flagged" type="checkbox"> À examiner uniquement</label>
<button id="reset">Recentrer</button><button id="refreshGit">Actualiser Git</button>
<button id="graphPrev" type="button" aria-label="Page précédente du graphe">◀</button>
<small id="graphPage" aria-live="polite">Page 1</small>
<button id="graphNext" type="button" aria-label="Page suivante du graphe">▶</button>
<small id="summary"></small><small id="liveStatus">Graphe statique</small></header>
<main><canvas id="map" aria-label="Graphe interactif, zoom molette, déplacement souris"></canvas>
<aside><h2>Inspection du code</h2><div id="snapshotDetails"></div><div id="coverageDetails"></div><div id="nodeDetails">Clique sur un nœud pour voir les dépendances, les preuves et les raisons d'examen.</div>
<hr><small id="limits"></small></aside></main>
<script id="doctor-data" type="application/json">__GRAPH_DATA__</script>
<script>
(()=>{'use strict';
const data=JSON.parse(document.getElementById('doctor-data').textContent);
const canvas=document.getElementById('map'),ctx=canvas.getContext('2d');
const search=document.getElementById('search'),domain=document.getElementById('domain');
const community=document.getElementById('community');
const relation=document.getElementById('relation');
const flagged=document.getElementById('flagged'),details=document.getElementById('nodeDetails');
const priority=document.getElementById('priority');
const reviewKind=document.getElementById('reviewKind');
const inventory=data.file_coverage;
const snapshot=data.snapshot_diff;
if(snapshot){
 const section=document.getElementById('snapshotDetails');
 const heading=document.createElement('h3');heading.textContent='Changements depuis le graphe de référence';
 section.appendChild(heading);
 const summary=document.createElement('p');
 summary.textContent='Référence '+snapshot.baseline_sha.slice(0,9)+' → '+snapshot.candidate_sha.slice(0,9)+
  ' · '+snapshot.new_import_file_pairs.length+' imports ajoutés · '+
  snapshot.removed_import_file_pairs.length+' imports retirés · '+
  snapshot.new_orphan_symbols.length+' nouveaux orphelins candidats';
 section.appendChild(summary);
 const caveat=document.createElement('small');
 caveat.textContent='Diff statique consultatif ; aucune preuve de régression ou de code mort. Les listes peuvent être tronquées.';
 section.appendChild(caveat);
 section.appendChild(document.createElement('hr'));
}
if(inventory){
 const section=document.getElementById('coverageDetails');
 const heading=document.createElement('h3');heading.textContent='Fichiers Python couverts';section.appendChild(heading);
 const count=document.createElement('p');
 count.textContent=inventory.represented+'/'+inventory.tracked+' représentés dans le graphe';
 section.appendChild(count);
 const status=document.createElement('small');
 status.textContent=inventory.status+' · Pas une preuve de code utilisé ou mort';
 section.appendChild(status);
 if(inventory.missing_total){
  const details=document.createElement('details');
  const summary=document.createElement('summary');
  summary.textContent=inventory.missing_total+' fichiers absents du graphe';
  details.appendChild(summary);
  inventory.missing_examples.forEach(path=>{
   const p=document.createElement('p');p.textContent=path;details.appendChild(p);
  });
  section.appendChild(details);
 }
 section.appendChild(document.createElement('hr'));
}
const neighbors=new Map(), nodes=data.nodes;
const relationCounts=new Map();
data.edges.forEach(e=>{
  const kind=String(e.relation||'non typée');
  relationCounts.set(kind,(relationCounts.get(kind)||0)+1);
  if(!neighbors.has(e.a))neighbors.set(e.a,[]);
  if(!neighbors.has(e.b))neighbors.set(e.b,[]);
  neighbors.get(e.a).push({n:e.b,relation:e.relation,direction:'out'});
  neighbors.get(e.b).push({n:e.a,relation:e.relation,direction:'in'});
});
[...relationCounts].sort((a,b)=>a[0].localeCompare(b[0])).forEach(([kind,count])=>{
 const option=document.createElement('option');option.value=kind;
 option.textContent=kind+' ('+count+')';relation.appendChild(option);
});
const groups=[...new Set(nodes.map(n=>n.domain))].sort();
groups.forEach(g=>{let opt=document.createElement('option');opt.value=g;opt.textContent=g;domain.appendChild(opt)});
const communityReview=new Map((data.community_review_candidates||[]).map(row=>[String(row.community),row]));
// All counts are bounded by the already-loaded Graphify node payload.
const reviewLabels={orphan:'Nœuds isolés',weak:'Connexions faibles',fanout:'Couplage élevé',
 forbidden:'Imports interdits confirmés',island:'Communautés isolées',
 ast:'Indices AST / JSON',doctor:'Actions Doctor',worker:'Workers à vérifier'};
const reviewCounts=new Map();
nodes.forEach(n=>(n.review_categories||[]).forEach(kind=>
 reviewCounts.set(kind,(reviewCounts.get(kind)||0)+1)));
[...reviewCounts].sort((a,b)=>a[0].localeCompare(b[0])).forEach(([kind,count])=>{
 const option=document.createElement('option');option.value=kind;
 option.textContent=(reviewLabels[kind]||kind)+' ('+count+' nœuds)';
 reviewKind.appendChild(option);
});
const communityCounts=new Map();
nodes.forEach(n=>{
 if(n.community===null||n.community===undefined)return;
 const id=String(n.community);
 communityCounts.set(id,(communityCounts.get(id)||0)+1);
});
[...communityCounts].sort((a,b)=>a[0].localeCompare(b[0],undefined,{numeric:true})).forEach(([id,count])=>{
 const option=document.createElement('option');option.value=id;
 option.textContent='Communauté '+id+' ('+count+' nœuds)'+(communityReview.has(id)?' · cohésion à examiner':'');
 community.appendChild(option);
});
function hash(s){let n=2166136261;for(let i=0;i<s.length;i++)n=Math.imul(n^s.charCodeAt(i),16777619);return n>>>0}
const offsets=new Map(groups.map((g,i)=>[g,i]));
const positions=nodes.map(n=>{
  const seed=hash(n.file+'|'+n.id),angle=(seed%65521)/65521*Math.PI*2;
  const group=offsets.get(n.domain)||0,outer=360+125*Math.sqrt(group);
  const groupAngle=group*2.39996323,small=12+Math.sqrt((seed>>>9)%2400)*1.8;
  return {x:Math.cos(groupAngle)*outer+Math.cos(angle)*small,
          y:Math.sin(groupAngle)*outer+Math.sin(angle)*small};
});
const PAGE_SIZE=1200;
let scale=.36,panX=0,panY=0,drag=null,selected=-1,visible=[],matches=[],pageIndex=0,pathStart=-1;
let changedFiles=new Set();
let importChanges=new Map(),importErrors=new Map(),importStatus='UNKNOWN';
let lastRefresh=0,refreshInFlight=false,lastLabel='';
function fit(){const rect=canvas.getBoundingClientRect();canvas.width=Math.max(1,Math.round(rect.width*devicePixelRatio));canvas.height=Math.max(1,Math.round(rect.height*devicePixelRatio));render()}
function filter(resetPage=true){const needle=search.value.toLowerCase().trim(),group=domain.value,level=priority.value,cluster=community.value,kind=reviewKind.value;
matches=nodes.map((n,i)=>i).filter(i=>{const n=nodes[i];return (!group||n.domain===group)&&
 (!cluster||String(n.community)===cluster)&&
 (!kind||(n.review_categories||[]).includes(kind))&&
 (!level||(n.doctor_task&&n.doctor_task.priority===level))&&
 (!flagged.checked||n.reasons.length||n.doctor_task||n.source_evidence.length||n.worker_start_unpaired_at_trace_end)&&
 (!needle||(n.file+' '+n.label).toLowerCase().includes(needle))});
const pages=Math.max(1,Math.ceil(matches.length/PAGE_SIZE));
if(resetPage)pageIndex=0;
pageIndex=Math.max(0,Math.min(pageIndex,pages-1));
visible=matches.slice(pageIndex*PAGE_SIZE,(pageIndex+1)*PAGE_SIZE);
document.getElementById('graphPrev').disabled=pageIndex===0;
document.getElementById('graphNext').disabled=pageIndex>=pages-1;
document.getElementById('graphPage').textContent='Page '+(pageIndex+1)+' / '+pages;
document.getElementById('summary').textContent=visible.length+' affichés · '+matches.length+' filtrés / '+nodes.length+' nœuds · relations de la page uniquement';
render()}
function screen(p){return {x:canvas.width/2+(p.x+panX)*scale*devicePixelRatio,
y:canvas.height/2+(p.y+panY)*scale*devicePixelRatio}}
let drawScheduled=false;
function render(){
 if(drawScheduled)return;
 drawScheduled=true;
 requestAnimationFrame(()=>{drawScheduled=false;paint()});
}
function paint(){
 if(!ctx)return;
 ctx.fillStyle='#0d1420';ctx.fillRect(0,0,canvas.width,canvas.height);
 const subset=new Set(visible);ctx.strokeStyle='#2b4259';ctx.lineWidth=1;
 if(visible.length<=3500){for(const e of data.edges){
 if(!subset.has(e.a)||!subset.has(e.b))continue;
 if(relation.value && e.relation!==relation.value)continue;
 let a=screen(positions[e.a]),b=screen(positions[e.b]);
 ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
 }}
 for(const i of visible){const p=screen(positions[i]),n=nodes[i];
 if(p.x < -10||p.x>canvas.width+10||p.y < -10||p.y>canvas.height+10)continue;
 ctx.beginPath();ctx.arc(p.x,p.y,i===selected?6:3,0,2*Math.PI);
 ctx.fillStyle=i===selected?'#ffdf86':changedFiles.has(n.file)?'#f9b454':(n.reasons.length||n.source_evidence.length)?'#ff8d7d':(n.runtime_observed||n.qt_call_site_observed)?'#b39cf5':'#70b9e9';ctx.fill()}
}
function pick(x,y){let best=-1,distance=100;for(const i of visible){
 const p=screen(positions[i]),d=(p.x-x)**2+(p.y-y)**2;
 if(d<distance){distance=d;best=i}}return best}
function show(i){selected=i;const n=nodes[i];details.replaceChildren();
function line(tag,text){const el=document.createElement(tag);el.textContent=text;details.appendChild(el);return el}
line('h3',n.label||n.file);line('p',n.file+(n.line?' · '+n.line:''));
if(changedFiles.has(n.file))line('p','Fichier modifié depuis le graphe : dépendances statiques potentiellement périmées.');
if(importChanges.has(n.file)){
 const delta=importChanges.get(n.file);
 line('h4','Imports Python modifiés (AST courant versus commit du graphe)');
 delta.added_imports.forEach(x=>line('p','+ L'+x.line+' '+x.statement));
 delta.removed_imports.forEach(x=>line('p','− ancienne L'+x.baseline_line+' '+x.statement));
 if(delta.imports_truncated)line('p','Détails tronqués : analyse ciblée nécessaire.');
}
if(importErrors.has(n.file))line('p','Inspection AST incomplète : '+importErrors.get(n.file));
line('p','Communauté Graphify : '+String(n.community??'non déterminée'));
if(n.snapshot_changes){
 const changes=n.snapshot_changes;
 line('h4','Différences Graphify depuis la référence');
 changes.added_imports.forEach(path=>line('p','+ import vers '+path));
 changes.removed_imports.forEach(path=>line('p','− import vers '+path));
 if(changes.new_orphan)line('p','Nouveau symbole orphelin candidat : vérifier ses consommateurs.');
 if(changes.new_weak)line('p','Symbole nouvellement peu connecté : examen nécessaire.');
}
if(n.review_categories.length){
 line('p','Catégories de diagnostic à vérifier : '+n.review_categories.map(kind=>reviewLabels[kind]||kind).join(', '));
}
const boundary=communityReview.get(String(n.community));
if(boundary){
 line('h4','Frontières de communauté à examiner');
 line('p',boundary.production_files+' fichiers de production · '+boundary.internal_extracted_edges+
 ' liens internes extraits · '+boundary.external_extracted_edges+' liens externes extraits.');
 line('p','Cohésion faible selon le graphe statique : ni fusion ni suppression automatique. Vérifier responsabilités, imports et appels réels.');
}
if(n.runtime_observed)line('p','Appel Python observé dans une trace opt-in correspondant au SHA.');
const symbolCalls=(data.observed_symbol_calls||[]).filter(e=>e.source===n.file||e.target===n.file);
if(symbolCalls.length){
 line('h4','Appels de fonctions observés (scénario opt-in)');
 symbolCalls.slice(0,20).forEach(e=>line('p',
  e.source+':'+e.caller_line+' '+e.caller_symbol+' → '+e.target+':'+e.callee_line+' '+e.callee_symbol));
 if(symbolCalls.length>20||data.symbol_calls_bounded)line('p','Observations partielles : aucune conclusion sur les fonctions non vues.');
}
if(n.qt_call_site_observed)line('p','Appel PySide observé au site d’appel ; récepteur non prouvé.');
if(n.qt_connection_observed)line('p','Connexion Qt explicitement instrumentée ; exécution du récepteur non prouvée.');
if(n.worker_start_unpaired_at_trace_end)line('p','Worker démarré sans arrêt observé avant la fin de cette trace ; une activité en cours est possible, ce n’est pas une fuite mémoire prouvée.');
if(n.cache_release_observed)line('p','Libération de cache explicitement marquée dans le scénario runtime.');
if(n.doctor_task){
 line('h4','Priorité Doctor : '+n.doctor_task.priority);
 line('p',n.doctor_task.kind+' · '+n.doctor_task.action);
 line('p','Proposition à vérifier dans le code et les tests, jamais correction automatique.');
}
if(n.source_evidence.length){
 line('h4','Indices AST du fichier (examen nécessaire)');
 n.source_evidence.forEach(e=>line('p',e.kind+(e.line?' · L'+e.line:'')+(e.subject?' · '+e.subject:'')));
}
if(n.reasons.length){line('h4','Pourquoi Doctor signale ce nœud');n.reasons.forEach(v=>line('p','• '+v))}
else line('p','Aucun signal prioritaire dans cet extrait de diagnostic.');
const link=document.createElement('a');
const locationMatch=String(n.line||'').match(/(?:^|:)([0-9]+)(?::[0-9]+)?$/);
const lineAnchor=locationMatch?'#L'+locationMatch[1]:'';
link.href='https://github.com/r9327/Dof-Atlas/blob/'+encodeURIComponent(data.candidate_sha||'main')+'/'+n.file.split('/').map(encodeURIComponent).join('/')+lineAnchor;
link.target='_blank';link.rel='noopener noreferrer';link.textContent='Voir le code sur GitHub';details.appendChild(link);
const adj=neighbors.get(i)||[];
const shownAdj=adj.filter(e=>!relation.value||e.relation===relation.value);
line('h4','Voisins du graphe ('+shownAdj.length+' / '+adj.length+' avec ce filtre)');
shownAdj.slice(0,40).forEach(e=>{
 const button=document.createElement('button');button.type='button';
 button.textContent=(e.direction==='out'?'→ ':'← ')+nodes[e.n].file+' · '+e.relation;
 button.addEventListener('click',()=>revealNode(e.n));
 details.appendChild(button);
});
if(shownAdj.length>40)line('small','Liste limitée à 40 voisins, sans supprimer les relations du graphe.');
const startButton=document.createElement('button');startButton.type='button';
startButton.textContent=pathStart===i?'Départ sélectionné':'Définir comme départ du chemin';
startButton.addEventListener('click',()=>{pathStart=i;show(i)});
details.appendChild(startButton);
if(pathStart>=0&&pathStart!==i){
 const pathButton=document.createElement('button');pathButton.type='button';
 pathButton.textContent='Chercher les dépendances depuis '+nodes[pathStart].file;
 pathButton.addEventListener('click',()=>showGraphPath(pathStart,i));
 details.appendChild(pathButton);
}
if(pathStart===i)line('p','Choisis un autre nœud puis cherche son chemin de dépendances.');
const impactButton=document.createElement('button');impactButton.type='button';
impactButton.textContent='Explorer les consommateurs (imports inverses)';
impactButton.addEventListener('click',()=>showReverseImpact(i));
details.appendChild(impactButton);
render()}
function focusNode(i){
 const loc=positions[i];
 if(!loc)return;
 panX=-loc.x;panY=-loc.y;
 scale=Math.max(scale,.55);
 show(i);
}
function revealNode(i){
 let offset=matches.indexOf(i);
 if(offset<0){
  search.value='';domain.value='';community.value='';reviewKind.value='';priority.value='';flagged.checked=false;
  filter(true);offset=matches.indexOf(i);
 }
 if(offset>=0){pageIndex=Math.floor(offset/PAGE_SIZE);filter(false);focusNode(i)}
}
function showReverseImpact(source){
 // Imported-by is static structural review, never observed behavior or deadness.
 const queue=[{node:source,depth:0}],seen=new Set([source]),candidates=[];
 let cursor=0,truncated=false;
 while(cursor<queue.length){
  const current=queue[cursor++];
  if(current.depth>=2)continue;
  for(const edge of neighbors.get(current.node)||[]){
   if(edge.direction!=='in'||!['imports','imports_from'].includes(edge.relation))continue;
   if(seen.has(edge.n))continue;
   if(seen.size>=2000){truncated=true;break}
   seen.add(edge.n);queue.push({node:edge.n,depth:current.depth+1});
   if(candidates.length<30)candidates.push({node:edge.n,depth:current.depth+1,relation:edge.relation});
  }
  if(truncated)break;
 }
 const section=document.createElement('section');
 const header=document.createElement('h4');
 header.textContent='Consommateurs possibles (imports inverses, 2 sauts maximum)';
 section.appendChild(header);
 const status=document.createElement('p');
 status.textContent=(seen.size-1)+' nœuds atteints dans ce budget ; '+(truncated?'revue partielle. ':'30 résultats affichés maximum. ')+
  'Relations structurales uniquement : valider les fichiers avant tout refactor.';
 section.appendChild(status);
 candidates.forEach(row=>{
  const button=document.createElement('button');button.type='button';
  button.textContent='Niveau '+row.depth+' : '+nodes[row.node].file+' ('+row.relation+')';
  button.addEventListener('click',()=>revealNode(row.node));
  section.appendChild(button);
 });
 details.appendChild(section);
}
function showGraphPath(from,to){
 // On-demand, directional Graphify relationships only; never a runtime proof.
 const queue=[from], depth=new Map([[from,0]]), previous=new Map();
 let cursor=0,complete=true,found=from===to;
 while(cursor<queue.length&&!found){
  const here=queue[cursor++],distance=depth.get(here);
  if(distance>=8){complete=false;continue}
  for(const edge of neighbors.get(here)||[]){
   if(edge.direction!=='out'||(relation.value&&edge.relation!==relation.value))continue;
   if(depth.has(edge.n))continue;
   if(depth.size>=4000){complete=false;break}
   depth.set(edge.n,distance+1);previous.set(edge.n,{from:here,relation:edge.relation});
   queue.push(edge.n);
   if(edge.n===to){found=true;break}
  }
  if(depth.size>=4000&&!found)break;
 }
 const section=document.createElement('section');
 const heading=document.createElement('h4');heading.textContent='Chemin de relations Graphify';section.appendChild(heading);
 if(!found){
  const note=document.createElement('p');
  note.textContent=(complete?'Aucun chemin orienté trouvé dans ce graphe extrait.':'Recherche partielle (8 sauts ou 4 000 nœuds). Chemin non établi.')+' Ce résultat ne prouve jamais du code mort.';
  section.appendChild(note);
 }else{
  const chain=[to];let next=to;
  while(next!==from){next=previous.get(next).from;chain.unshift(next)}
  const note=document.createElement('small');
  note.textContent=(chain.length-1)+' relation(s) extraites/observées ; ce chemin ne prouve pas une exécution.';
  section.appendChild(note);
  chain.forEach((nodeIndex,index)=>{
   const button=document.createElement('button');button.type='button';
   const parent=index?previous.get(nodeIndex):null;
   button.textContent=(parent?'→ '+parent.relation+' → ':'Départ : ')+nodes[nodeIndex].file;
   button.addEventListener('click',()=>revealNode(nodeIndex));
   section.appendChild(button);
  });
 }
 details.appendChild(section);
}
canvas.addEventListener('pointerdown',e=>{canvas.setPointerCapture(e.pointerId);drag={x:e.clientX,y:e.clientY,px:panX,py:panY,moved:false}});
canvas.addEventListener('pointermove',e=>{if(!drag)return;const dx=(e.clientX-drag.x)/scale,dy=(e.clientY-drag.y)/scale;
if(Math.abs(dx)+Math.abs(dy)>5)drag.moved=true;panX=drag.px+dx;panY=drag.py+dy;render()});
canvas.addEventListener('pointerup',e=>{if(!drag)return;const moved=drag.moved;drag=null;
if(!moved){const r=canvas.getBoundingClientRect();const found=pick((e.clientX-r.left)*devicePixelRatio,(e.clientY-r.top)*devicePixelRatio);if(found>=0)show(found)}});
canvas.addEventListener('wheel',e=>{e.preventDefault();scale=Math.max(.025,Math.min(3,scale*(e.deltaY>0?.84:1.16)));render()},{passive:false});
[search,domain,community,reviewKind,priority,flagged].forEach(el=>el.addEventListener('input',()=>filter(true)));
relation.addEventListener('change',()=>{if(selected>=0)show(selected);else render()});
document.getElementById('graphPrev').addEventListener('click',()=>{pageIndex--;filter(false)});
document.getElementById('graphNext').addEventListener('click',()=>{pageIndex++;filter(false)});
search.addEventListener('keydown',event=>{
 if(event.key==='Enter'&&matches.length){event.preventDefault();pageIndex=0;filter(false);focusNode(matches[0])}
});
document.getElementById('reset').addEventListener('click',()=>{scale=.36;panX=0;panY=0;render()});
document.getElementById('limits').textContent='Trace: '+data.trace_status+' · '+data.observed_runtime_file_pairs+' relations de fichiers observées. '+data.disclaimer+(data.truncated?' Attention : graphe tronqué pour une visualisation fluide.':'');
async function refreshLive(force=false){
 if(document.hidden||refreshInFlight||(!force&&Date.now()-lastRefresh<1500))return;
 lastRefresh=Date.now();
 refreshInFlight=true;
 const label=document.getElementById('liveStatus');
 try{
  const response=await fetch('/api/live',{cache:'no-store'});
  if(!response.ok)throw new Error('status '+response.status);
  const live=await response.json();
  const next=new Set(live.changed_files||[]);
  const importData=live.source_import_delta||{};
  const nextImportChanges=new Map((importData.changes||[]).map(row=>[row.path,row]));
  const nextImportErrors=new Map((importData.errors||[]).map(row=>[row.path,row.reason]));
  const before=JSON.stringify([...importChanges,...importErrors]);
  const after=JSON.stringify([...nextImportChanges,...nextImportErrors]);
  const changed=next.size!==changedFiles.size||[...next].some(path=>!changedFiles.has(path))||before!==after;
  changedFiles=next;
  importChanges=nextImportChanges;
  importErrors=nextImportErrors;
  importStatus=importData.status||'UNKNOWN';
  const filesShown=new Set(nodes.map(n=>n.file));
  const unknown=[...changedFiles].filter(path=>!filesShown.has(path)).length;
  let caption=live.graph_stale?'Graphe figé · '+live.changed_count+' fichiers modifiés · '+unknown+' hors graphe':'Graphe inchangé · suivi à la demande';
  if(live.truncated)caption+=' (liste partielle)';
  label.textContent=caption+' · imports '+importStatus;
  if(changed){if(selected>=0)show(selected);else render();}
 }catch(error){label.textContent='Suivi Git indisponible · graphe figé';}
 finally{refreshInFlight=false;}
}
if(location.hostname==='127.0.0.1'||location.hostname==='localhost'){
 document.getElementById('refreshGit').addEventListener('click',()=>refreshLive(true));
 window.addEventListener('focus',()=>refreshLive());
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshLive()});
 // Heartbeat keeps the *local* viewer alive while visible; it never invokes Git.
 setInterval(()=>{if(!document.hidden)fetch('/api/ping',{cache:'no-store'}).catch(()=>{})},60000);
 refreshLive(true);
}
// Populate the initial node set before the first canvas render.
window.addEventListener('resize',fit);filter();fit();
})();
</script></body></html>"""


def render_html(payload: dict[str, Any]) -> str:
    # An untrusted symbol/file label cannot close the JSON script or inject HTML.
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return HTML.replace("__GRAPH_DATA__", encoded)


def load_snapshot_comparison(
    root: Path, graph: dict[str, Any], baseline_path: Path
) -> dict[str, Any]:
    """Compare an explicitly supplied snapshot inside graphify-out, read-only."""
    from .graph_intelligence import compare_graphs

    root = root.resolve()
    allowed = root / "graphify-out"
    if baseline_path.is_symlink():
        raise ValueError("Symlink baseline snapshots are not allowed")
    selected = baseline_path.resolve()
    if not selected.is_relative_to(allowed) or not selected.is_file():
        raise ValueError("Baseline graph must be a regular file under graphify-out")
    if selected.stat().st_size > 25_000_000:
        raise ValueError("Baseline graph exceeds 25 MB")
    baseline = json.loads(selected.read_text(encoding="utf-8"))
    if not isinstance(baseline, dict):
        raise ValueError("Baseline graph JSON must be an object")
    return compare_graphs(baseline, graph)


def export_interactive_graph(root: Path, *, trace_path: Path | None = None,
                             allow_stale: bool = False,
                             baseline_path: Path | None = None) -> dict[str, Any]:
    from .architecture import graph_status
    from .graph_audit import audit_current_graph, inspect_graph
    root = root.resolve()
    status = graph_status(root)
    stale = status.get("status") == "STALE"
    if status.get("status") != "PASS" and not (allow_stale and stale):
        return {"status": "BLOCKED", "reason": status.get("reason"), "graph_status": status.get("status")}
    try:
        graph = json.loads(Path(status["graph"]).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        return {"status": "BLOCKED", "reason": str(exc)}
    built_at = graph.get("built_at_commit")
    if not isinstance(built_at, str) or not re.fullmatch(r"[0-9a-fA-F]{7,40}", built_at):
        return {"status": "BLOCKED", "reason": "Graphify source commit provenance missing."}
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", built_at + "^{commit}"],
        cwd=root, text=True, capture_output=True, timeout=10, check=False,
    )
    if resolved.returncode != 0 or len(resolved.stdout.strip()) != 40:
        return {"status": "BLOCKED", "reason": "Graphify source commit could not be resolved."}
    snapshot_commit = resolved.stdout.strip()
    if not stale and status["git"]["head"] != snapshot_commit:
        return {"status": "BLOCKED", "reason": "Graphify source commit disagrees with current HEAD."}
    if stale:
        # Never validate a historical graph against today's changed source.
        # Show structural candidates only; no historical graph == current proof.
        audit = inspect_graph(graph, root=None)
    else:
        audit = audit_current_graph(root, graph_evidence=status)
        if audit["status"] not in {"PASS", "REVIEW"}:
            return {"status": "BLOCKED", "reason": "Doctor graph audit is not valid."}
    graph["built_at_commit"] = snapshot_commit
    trace = None
    if trace_path is not None:
        selected_path = trace_path.resolve()
        if not selected_path.is_relative_to(root / ".ai" / "runtime") or not selected_path.is_file():
            return {"status": "BLOCKED", "reason": "Trace must exist in .ai/runtime."}
        if selected_path.stat().st_size > 10_000_000:
            return {"status": "BLOCKED", "reason": "Trace too large; bounded trace required."}
        try:
            trace = json.loads(selected_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            return {"status": "BLOCKED", "reason": str(exc)}
    # Explicit graph-ui action only: inspect at most 16 flagged Python files.
    # Never scan the repository periodically or certify historical graph data.
    inspection: dict[str, Any] | None = None
    source_scan_truncated = False
    if not stale:
        selected: list[str] = []
        seen: set[str] = set()
        for kind in ("blocking_findings", "orphan_nodes",
                     "weak_production_candidates", "high_fanout_files"):
            for row in audit.get(kind, []):
                if not isinstance(row, dict):
                    continue
                path = row.get("file") or row.get("path") or row.get("source")
                if (isinstance(path, str) and path.startswith(("app/", "tools/"))
                        and path.endswith(".py") and path not in seen):
                    seen.add(path)
                    selected.append(path)
        source_scan_truncated = len(selected) > MAX_SOURCE_INSPECTION_FILES
        source_paths = [x for x in selected[:MAX_SOURCE_INSPECTION_FILES] if
                        (root / x).is_file() and not (root / x).is_symlink()]
        if source_paths:
            from .deep_intelligence import scan_sources
            inspection = scan_sources(root, source_paths)
    lineage = None
    if inspection is not None and inspection.get("data_lineage_candidates"):
        from .deep_intelligence import trace_literal_json_to_ui
        lineage = trace_literal_json_to_ui(graph, inspection["data_lineage_candidates"])
    comparison = None
    if baseline_path is not None:
        try:
            comparison = load_snapshot_comparison(root, graph, baseline_path)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            return {"status": "BLOCKED", "reason": f"Baseline graph: {exc}"}
    payload = compact_graph(graph, audit, trace=trace, inspection=inspection,
                            lineage=lineage, comparison=comparison)
    payload["source_scan_selection_truncated"] = source_scan_truncated
    from .file_coverage import tracked_python
    inventory = tracked_python(root)
    graph_files = {row.get("source_file") for row in graph["nodes"]
                   if isinstance(row.get("source_file"), str)}
    missing = sorted(set(inventory) - graph_files)
    payload["file_coverage"] = {
        "tracked": len(inventory), "represented": len(inventory) - len(missing),
        "missing_total": len(missing), "missing_examples": missing[:60],
        "truncated": len(missing) > 60,
        "status": "HISTORICAL" if stale else "CURRENT_SNAPSHOT",
        "runtime_proof": False,
    }
    destination = root / "graphify-out" / "doctor_graph.html"
    destination.write_text(render_html(payload), encoding="utf-8")
    return {
        "status": "REVIEW" if stale else "PASS",
        "candidate_sha": snapshot_commit, "graph_status": status["status"],
        "path": str(destination), "trace_status": payload["trace_status"],
        "nodes_shown": len(payload["nodes"]),
        "links_shown": len(payload["edges"]), "truncated": payload["truncated"],
        "source_inspection": payload["source_inspection_status"],
        "source_scan_files": payload["source_inspection_files"],
        "json_lineage_review_leads": payload["json_lineage_review_leads"],
        "baseline_sha": comparison["baseline_sha"] if comparison else None,
        "snapshot_comparison_status": comparison["status"] if comparison else "NOT_PROVIDED",
        "source_scan_truncated": source_scan_truncated or payload["source_inspection_truncated"],
        "tests_executed": False, "graph_rebuilt": False,
    }
