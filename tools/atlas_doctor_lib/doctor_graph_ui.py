from __future__ import annotations

"""Doctor overlay on the *existing* exact-SHA Graphify export.

An independent local HTML viewer; no server, CDN, Qt runtime or graph rebuild.
"""
import json
from pathlib import Path
from typing import Any

MAX_NODES = 8000
MAX_LINKS = 25000


def _domain(path: str) -> str:
    parts = path.split("/")
    if len(parts) > 3 and parts[:2] == ["app", "modules"]:
        return "/".join(parts[:3])
    return "/".join(parts[:2]) if len(parts) > 1 else path


def compact_graph(graph: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", [])[:MAX_NODES]
    indexed = {item["id"]: number for number, item in enumerate(nodes)}
    file_reasons: dict[str, list[str]] = {}
    for field, reason in (
        ("orphan_nodes", "Isolated Graphify node; not proof of dead code"),
        ("weak_production_candidates", "Weakly connected candidate"),
        ("high_fanout_files", "High fanout coupling candidate"),
        ("blocking_findings", "Doctor source-confirmed forbidden dependency"),
    ):
        for item in audit.get(field, []):
            path = item.get("file") or item.get("path") or item.get("source")
            if isinstance(path, str):
                values = file_reasons.setdefault(path, [])
                if reason not in values:
                    values.append(reason)
    selected = []
    for item in nodes:
        file = item.get("source_file") or ""
        selected.append({
            "id": str(item["id"]), "label": str(item.get("label") or ""),
            "file": file, "domain": _domain(file), "community": item.get("community"),
            "line": str(item.get("source_location") or ""),
            "reasons": file_reasons.get(file, []),
        })
    edges = []
    for link in graph.get("links", []):
        if len(edges) >= MAX_LINKS:
            break
        a, b = indexed.get(link.get("source")), indexed.get(link.get("target"))
        if a is not None and b is not None:
            edges.append({"a": a, "b": b, "relation": str(link.get("relation") or "")})
    return {
        "nodes": selected, "edges": edges, "candidate_sha": graph.get("built_at_commit"),
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
<label><input id="flagged" type="checkbox"> À examiner uniquement</label>
<button id="reset">Recentrer</button><small id="summary"></small></header>
<main><canvas id="map" aria-label="Graphe interactif, zoom molette, déplacement souris"></canvas>
<aside><h2>Inspection du code</h2><div id="nodeDetails">Clique sur un nœud pour voir les dépendances, les preuves et les raisons d'examen.</div>
<hr><small id="limits"></small></aside></main>
<script id="doctor-data" type="application/json">__GRAPH_DATA__</script>
<script>
(()=>{'use strict';
const data=JSON.parse(document.getElementById('doctor-data').textContent);
const canvas=document.getElementById('map'),ctx=canvas.getContext('2d');
const search=document.getElementById('search'),domain=document.getElementById('domain');
const flagged=document.getElementById('flagged'),details=document.getElementById('nodeDetails');
const neighbors=new Map(), nodes=data.nodes;data.edges.forEach(e=>{
  if(!neighbors.has(e.a))neighbors.set(e.a,[]);
  if(!neighbors.has(e.b))neighbors.set(e.b,[]);
  neighbors.get(e.a).push({n:e.b,relation:e.relation,direction:'out'});
  neighbors.get(e.b).push({n:e.a,relation:e.relation,direction:'in'});
});
const groups=[...new Set(nodes.map(n=>n.domain))].sort();
groups.forEach(g=>{let opt=document.createElement('option');opt.value=g;opt.textContent=g;domain.appendChild(opt)});
function hash(s){let n=2166136261;for(let i=0;i<s.length;i++)n=Math.imul(n^s.charCodeAt(i),16777619);return n>>>0}
const offsets=new Map(groups.map((g,i)=>[g,i]));
const positions=nodes.map(n=>{
  const seed=hash(n.file+'|'+n.id),angle=(seed%65521)/65521*Math.PI*2;
  const group=offsets.get(n.domain)||0,outer=360+125*Math.sqrt(group);
  const groupAngle=group*2.39996323,small=12+Math.sqrt((seed>>>9)%2400)*1.8;
  return {x:Math.cos(groupAngle)*outer+Math.cos(angle)*small,
          y:Math.sin(groupAngle)*outer+Math.sin(angle)*small};
});
let scale=.36,panX=0,panY=0,drag=null,selected=-1,visible=[];
function fit(){const rect=canvas.getBoundingClientRect();canvas.width=Math.max(1,Math.round(rect.width*devicePixelRatio));canvas.height=Math.max(1,Math.round(rect.height*devicePixelRatio));render()}
function filter(){const needle=search.value.toLowerCase().trim(),group=domain.value;
visible=nodes.map((n,i)=>i).filter(i=>{const n=nodes[i];return (!group||n.domain===group)&&
 (!flagged.checked||n.reasons.length)&&(!needle||(n.file+' '+n.label).toLowerCase().includes(needle))});
document.getElementById('summary').textContent=visible.length+' / '+nodes.length+' nœuds';render()}
function screen(p){return {x:canvas.width/2+(p.x+panX)*scale*devicePixelRatio,
y:canvas.height/2+(p.y+panY)*scale*devicePixelRatio}}
function render(){
 if(!ctx)return;
 ctx.fillStyle='#0d1420';ctx.fillRect(0,0,canvas.width,canvas.height);
 const subset=new Set(visible);ctx.strokeStyle='#2b4259';ctx.lineWidth=1;
 if(visible.length<=3500){for(const e of data.edges){
 if(!subset.has(e.a)||!subset.has(e.b))continue;
 let a=screen(positions[e.a]),b=screen(positions[e.b]);
 ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
 }}
 for(const i of visible){const p=screen(positions[i]),n=nodes[i];
 if(p.x < -10||p.x>canvas.width+10||p.y < -10||p.y>canvas.height+10)continue;
 ctx.beginPath();ctx.arc(p.x,p.y,i===selected?6:3,0,2*Math.PI);
 ctx.fillStyle=i===selected?'#ffdf86':n.reasons.length?'#ff8d7d':'#70b9e9';ctx.fill()}
}
function pick(x,y){let best=-1,distance=100;for(const i of visible){
 const p=screen(positions[i]),d=(p.x-x)**2+(p.y-y)**2;
 if(d<distance){distance=d;best=i}}return best}
function show(i){selected=i;const n=nodes[i];details.replaceChildren();
function line(tag,text){const el=document.createElement(tag);el.textContent=text;details.appendChild(el);return el}
line('h3',n.label||n.file);line('p',n.file+(n.line?' · '+n.line:''));
line('p','Communauté Graphify : '+String(n.community??'non déterminée'));
if(n.reasons.length){line('h4','Pourquoi Doctor signale ce nœud');n.reasons.forEach(v=>line('p','• '+v))}
else line('p','Aucun signal prioritaire dans cet extrait de diagnostic.');
const link=document.createElement('a');link.href='https://github.com/r9327/Dof-Atlas/blob/'+encodeURIComponent(data.candidate_sha||'main')+'/'+n.file.split('/').map(encodeURIComponent).join('/');
link.target='_blank';link.rel='noopener noreferrer';link.textContent='Voir le code sur GitHub';details.appendChild(link);
const adj=neighbors.get(i)||[];line('h4','Connexions affichées ('+adj.length+')');
adj.slice(0,40).forEach(e=>line('p',e.direction==='out'?'→ '+nodes[e.n].file+' · '+e.relation:'← '+nodes[e.n].file+' · '+e.relation));
render()}
canvas.addEventListener('pointerdown',e=>{canvas.setPointerCapture(e.pointerId);drag={x:e.clientX,y:e.clientY,px:panX,py:panY,moved:false}});
canvas.addEventListener('pointermove',e=>{if(!drag)return;const dx=(e.clientX-drag.x)/scale,dy=(e.clientY-drag.y)/scale;
if(Math.abs(dx)+Math.abs(dy)>5)drag.moved=true;panX=drag.px+dx;panY=drag.py+dy;render()});
canvas.addEventListener('pointerup',e=>{if(!drag)return;const moved=drag.moved;drag=null;
if(!moved){const r=canvas.getBoundingClientRect();const found=pick((e.clientX-r.left)*devicePixelRatio,(e.clientY-r.top)*devicePixelRatio);if(found>=0)show(found)}});
canvas.addEventListener('wheel',e=>{e.preventDefault();scale=Math.max(.025,Math.min(3,scale*(e.deltaY>0?.84:1.16)));render()},{passive:false});
[search,domain,flagged].forEach(el=>el.addEventListener('input',filter));
document.getElementById('reset').addEventListener('click',()=>{scale=.36;panX=0;panY=0;render()});
document.getElementById('limits').textContent=data.disclaimer+(data.truncated?' Attention : graphe tronqué pour une visualisation fluide.':'');
window.addEventListener('resize',fit);fit();filter();
})();
</script></body></html>"""


def render_html(payload: dict[str, Any]) -> str:
    # An untrusted symbol/file label cannot close the JSON script or inject HTML.
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return HTML.replace("__GRAPH_DATA__", encoded)


def export_interactive_graph(root: Path) -> dict[str, Any]:
    from .architecture import graph_status
    from .graph_audit import audit_current_graph
    root = root.resolve()
    status = graph_status(root)
    if status.get("status") != "PASS":
        return {"status": "BLOCKED", "reason": status.get("reason"), "graph_status": status.get("status")}
    graph = json.loads(Path(status["graph"]).read_text(encoding="utf-8"))
    if graph.get("built_at_commit") != status["git"]["head"]:
        return {"status": "BLOCKED", "reason": "Exact candidate SHA is required for visual diagnosis."}
    audit = audit_current_graph(root, graph_evidence=status)
    if audit["status"] not in {"PASS", "REVIEW"}:
        return {"status": "BLOCKED", "reason": "Doctor graph audit is not valid."}
    payload = compact_graph(graph, audit)
    destination = root / "graphify-out" / "doctor_graph.html"
    destination.write_text(render_html(payload), encoding="utf-8")
    return {
        "status": "PASS", "candidate_sha": status["git"]["head"],
        "path": str(destination), "nodes_shown": len(payload["nodes"]),
        "links_shown": len(payload["edges"]), "truncated": payload["truncated"],
        "tests_executed": False, "graph_rebuilt": False,
    }
