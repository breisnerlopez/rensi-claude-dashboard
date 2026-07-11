#!/usr/bin/env python3
# v3 - Agregador de uso Claude. Cache por-mtime: solo re-parsea archivos que cambiaron.
import os, glob, json, subprocess, datetime as dt, re, bisect
from collections import defaultdict, Counter
from zoneinfo import ZoneInfo

HOME="/home/admin"; TZ=ZoneInfo("America/Lima")
PROJECTS=f"{HOME}/.claude/projects"; TASKS=f"{HOME}/.claude/tasks"; BLOCK_H=5
MTIME_DAYS=35
CACHE_FILE="/opt/claude-usage-web/.parsecache.json"
BLOCK_LIMIT_CACHE="/opt/claude-usage-web/.blocklimits.json"
PRICE={"opus":{"in":15e-6,"out":75e-6,"cw":18.75e-6,"cr":1.5e-6},
       "sonnet":{"in":3e-6,"out":15e-6,"cw":3.75e-6,"cr":0.3e-6},
       "haiku":{"in":0.8e-6,"out":4e-6,"cw":1e-6,"cr":0.08e-6},
       "fable":{"in":10e-6,"out":50e-6,"cw":12.5e-6,"cr":1e-6}}
WINDOW={"opus":1_000_000,"sonnet":1_000_000,"haiku":200_000,"fable":1_000_000}
PATH_RE=re.compile(r"(?:[A-Za-z]:\\[^\s]+|(?:/[\w.\-]+){2,})")
SECRET_RE=re.compile(r"(-----BEGIN[ A-Z]*PRIVATE KEY-----.*?-----END[ A-Z]*PRIVATE KEY-----"
    r"|gh[opsu]_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_\-]{16,}"
    r"|sk-ant-[A-Za-z0-9_\-]{20,}|sk-proj-[A-Za-z0-9_\-]{20,}|sk-[A-Za-z0-9]{16,}"
    r"|sk_(?:live|test)_[A-Za-z0-9]{16,}|rk_(?:live|test)_[A-Za-z0-9]{16,}|whsec_[A-Za-z0-9]{16,}"
    r"|AKIA[0-9A-Z]{16}|AIza[A-Za-z0-9_\-]{20,}"
    r"|xox(?:[baprs]-|e-|e\.xox[a-z]-)[A-Za-z0-9-]+|xapp-[A-Za-z0-9-]+"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
    r"|[Bb]earer\s+[A-Za-z0-9\-_.=]{10,}"
    r"|[a-z]+://[^\s:@/]+:[^\s:@/]+@)", re.S)
AWS_SECRET_RE=re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}")
PH_RE=re.compile(r"phases\s*:\s*\[(.*?)\]", re.S); TIT_RE=re.compile(r"title\s*:\s*['\"]([^'\"]+)")
DSC_RE=re.compile(r"description\s*:\s*['\"]([^'\"]+)")
TN_BLOCK=re.compile(r"tool-use-id>(toolu_[A-Za-z0-9]+)</tool-use-id>.*?<status>([a-z]+)</status>", re.S)
def fam(m):
    m=(m or "").lower()
    for k in PRICE:
        if k in m: return k
    return "sonnet"  # unknown/future model name: guess the mid tier, not the priciest (was "opus")
def redact(s):
    if not s: return s
    s=AWS_SECRET_RE.sub("aws_secret_access_key=[secreto]", s)
    s=SECRET_RE.sub("[secreto]", s)
    s=PATH_RE.sub(lambda m: ".../"+re.split(r"[/\\]", m.group(0).rstrip("/\\"))[-1], s)
    return s
def now_utc(): return dt.datetime.now(dt.timezone.utc)
def atomic(path,obj):
    tmp=path+".wtmp"
    with open(tmp,"w") as f: json.dump(obj,f,default=str)
    os.replace(tmp,path)

# ---- cache por-archivo (mtime+size) ----
_cache=None; _newcache={}
def _load():
    global _cache
    if _cache is None:
        try: _cache=json.load(open(CACHE_FILE))
        except: _cache={}
    return _cache
def _save():
    try: atomic(CACHE_FILE, _newcache)
    except: pass

def file_summary(path):
    """Parseo de UN transcript -> todo lo que necesitan bloques y detalle. JSON-serializable."""
    recs=[]; nmsg=0; tools=Counter(); agents={}; results=[]; wf=[]; tn={}
    last=None; first=None; gitb=None; cost=0.0; timeline=[]
    try:
        for line in open(path,encoding="utf-8",errors="ignore"):
            if "task-notification" in line:
                for tid,st in TN_BLOCK.findall(line): tn[tid]=st
            if '"usage"' not in line and '"tool_use"' not in line and '"gitBranch"' not in line and '"message"' not in line:
                continue
            try: o=json.loads(line)
            except: continue
            gb=o.get("gitBranch")
            if gb: gitb=redact(gb)
            ts=o.get("timestamp"); m=o.get("message") or {}
            if m: nmsg+=1
            if ts and not first: first=ts
            u=m.get("usage") or {}
            if u:
                inp=u.get("input_tokens",0) or 0; out=u.get("output_tokens",0) or 0
                cw=u.get("cache_creation_input_tokens",0) or 0; cr=u.get("cache_read_input_tokens",0) or 0
                pr=PRICE[fam(m.get("model"))]
                cline=inp*pr["in"]+out*pr["out"]+cw*pr["cw"]+cr*pr["cr"]
                key=""
                mid=m.get("id"); rid=o.get("requestId")
                if mid or rid: key=f"{mid}|{rid}"
                recs.append([ts, inp+out, round(cline,6), key])
                ctx=inp+cw+cr
                last=[ts, m.get("model"), ctx]; cost+=cline
            c=m.get("content")
            if isinstance(c,list):
                for b in c:
                    if not isinstance(b,dict): continue
                    if b.get("type")=="tool_use":
                        n=b.get("name",""); ip=b.get("input") or {}; tools[n]+=1
                        brief=redact(str(ip.get("description") or ip.get("subject") or ip.get("command") or ip.get("file_path") or ""))[:220]
                        timeline.append({"ts":ts,"tool":n,"brief":brief})
                        if n in ("Agent","Task"): agents[b.get("id")]={"type":ip.get("subagent_type") or "?","desc":redact(ip.get("description") or "")[:220]}
                        elif n=="Workflow":
                            sc=ip.get("script","") or ""; phs=[]; mm=PH_RE.search(sc)
                            if mm: phs=[redact(x)[:80] for x in TIT_RE.findall(mm.group(1))[:12]]
                            dsc=ip.get("description") or ""
                            if not dsc:
                                dm=DSC_RE.search(sc); dsc=dm.group(1) if dm else ""
                            wf.append({"id":b.get("id"),"desc":redact(dsc)[:240],"phases":phs})
                    if b.get("type")=="tool_result": results.append(b.get("tool_use_id"))
    except: pass
    return {"recs":recs,"nmsg":nmsg,"tools":dict(tools),"agents":agents,"results":results,
            "wf":wf,"tn":tn,"last":last,"first":first,"gitb":gitb,"cost":round(cost,4),
            "timeline":timeline[-80:]}

def get_summary(path):
    try: st=os.stat(path)
    except: return None
    c=_load().get(path)
    if c and c.get("mtime")==st.st_mtime and c.get("size")==st.st_size:
        data=c["data"]
    else:
        data=file_summary(path)
    _newcache[path]={"mtime":st.st_mtime,"size":st.st_size,"data":data}
    return data

def recent_top_files():
    cutoff=now_utc().timestamp()-MTIME_DAYS*86400
    return [f for f in glob.glob(f"{PROJECTS}/*/*.jsonl") if os.path.getmtime(f)>=cutoff]

def cm_api():
    try:
        o=subprocess.run(["bash","-lc","claude-monitor --api --once --view realtime --output json"],
            capture_output=True,text=True,timeout=20,env={**os.environ,"HOME":HOME,"PATH":f"{HOME}/.local/bin:/usr/bin:/bin"})
        d=json.loads(o.stdout); lim=d.get("limits") or {}
        return lim.get("five_hour") or {}, lim.get("seven_day") or {}, d.get("local") or {}, True
    except Exception:
        return {}, {}, {}, False

def prev_api_fail_since():
    try:
        with open("/opt/claude-usage-web/data.json") as f: return json.load(f).get("api_fail_since")
    except Exception: return None

def main(fast=False):
    files=recent_top_files()
    summaries={f:get_summary(f) for f in files}
    summaries={f:d for f,d in summaries.items() if d}
    _save()

    if fast:
        # Fast path: only re-derive the live sessions/workflows/agents/tasks
        # view (cheap -- pure local transcript parsing, no subprocess) and
        # patch it into the existing data.json in place, leaving the
        # official-API-derived numbers (blocks/pct/eta/sustainable) exactly
        # as the last full run left them. Runs on a much shorter timer than
        # the full cm_api()-bound cycle so "entrar a una sesion" feels live.
        try:
            with open("/opt/claude-usage-web/data.json") as f: data=json.load(f)
        except Exception:
            data={}
        data["sessions"]=sessions_info(summaries)
        data["sessions_generated_at"]=now_utc().isoformat()
        atomic("/opt/claude-usage-web/data.json", data)
        return

    # --- registros globales (bloques 5h/dia) con dedup por key ---
    seen=set(); recs=[]
    for f,d in summaries.items():
        for ts,tok,cost,key in d["recs"]:
            if key:
                if key in seen: continue
                seen.add(key)
            recs.append((dt.datetime.fromisoformat(ts.replace("Z","+00:00")),tok,cost))

    fh,sd,loc,api_ok=cm_api()
    api_fail_since=None if api_ok else (prev_api_fail_since() or now_utc().isoformat())
    off5=fh.get("used_percentage"); off7=sd.get("used_percentage")
    now=now_utc(); today=now.astimezone(TZ).date(); wkstart=today-dt.timedelta(days=today.weekday())
    win_end=None
    if fh.get("resets_at"):
        try: win_end=dt.datetime.fromisoformat(fh["resets_at"])
        except: win_end=None
    win_start=(win_end-dt.timedelta(hours=BLOCK_H)) if win_end else None
    # M3 fix: don't tile a single 5h grid off win_start across all of history
    # (that assumes zero idle gaps >=5h, ever). Instead derive per-segment
    # anchors: a new block starts either after an idle gap >=BLOCK_H since the
    # previous record, or by rolling forward in fixed BLOCK_H steps from the
    # prior anchor when activity is continuous past it (matches the real
    # rolling-window reset behavior). win_start (from the official API) is
    # authoritative for the current window and overrides anchors at/after it.
    _ts=sorted(t for t,_,_ in recs)
    anchors=[]
    if _ts:
        blk=_ts[0]; anchors.append(blk)
        for prev,cur in zip(_ts,_ts[1:]):
            if (cur-prev).total_seconds()>=BLOCK_H*3600:
                blk=cur
            elif (cur-blk).total_seconds()>=BLOCK_H*3600:
                k=(cur-blk).total_seconds()//(BLOCK_H*3600)
                blk=blk+dt.timedelta(hours=BLOCK_H*k)
            anchors.append(blk)
        anchors=sorted(set(anchors))
    if win_start:
        anchors=[a for a in anchors if a<win_start]+[win_start]
    def bstart(t):
        tu=t.astimezone(dt.timezone.utc)
        if anchors:
            i=bisect.bisect_right(anchors,tu)-1
            if i>=0:
                a=anchors[i]
                k=(tu-a).total_seconds()//(BLOCK_H*3600)
                return a+dt.timedelta(hours=BLOCK_H*k)
        return tu.replace(hour=(tu.hour//BLOCK_H)*BLOCK_H,minute=0,second=0,microsecond=0)
    blocks=defaultdict(lambda:{"tok":0,"cost":0.0}); days=defaultdict(lambda:{"tok":0,"cost":0.0,"blk":set()})
    for t,bt,cost in recs:
        bs=bstart(t); blocks[bs]["tok"]+=bt; blocks[bs]["cost"]+=cost
        d=t.astimezone(TZ).date().isoformat(); days[d]["tok"]+=bt; days[d]["cost"]+=cost; days[d]["blk"].add(bs)
    active_bs=bstart(now); active_tok=blocks.get(active_bs,{}).get("tok",0)
    LOW_CONF=(off5 is None) or (off5<3)
    derived_limit=active_tok/(off5/100.0) if (not LOW_CONF and active_tok>0) else None
    # M1 fix: freeze each block's token->limit ratio the moment it's the
    # active block, instead of recomputing every block's % from whichever
    # ratio happens to be live right now. A closed block's % must never
    # change on a later refresh.
    try: block_limits=json.load(open(BLOCK_LIMIT_CACHE))
    except Exception: block_limits={}
    cutoff_bl=(now-dt.timedelta(days=3)).isoformat()
    block_limits={k:v for k,v in block_limits.items() if k>=cutoff_bl}
    if derived_limit: block_limits[active_bs.isoformat()]=derived_limit
    try: atomic(BLOCK_LIMIT_CACHE, block_limits)
    except Exception: pass
    def bpct(bs,tok):
        dl=block_limits.get(bs.isoformat())
        return round(100*tok/dl,1) if dl else None
    today_blocks=[]
    sorted_bs=[bs for bs,_ in sorted(blocks.items())]
    for idx,(bs,v) in enumerate(sorted(blocks.items())):
        next_bs=sorted_bs[idx+1] if idx+1<len(sorted_bs) else None
        be=min(bs+dt.timedelta(hours=BLOCK_H), next_bs) if next_bs else bs+dt.timedelta(hours=BLOCK_H)
        if not (bs.astimezone(TZ).date()==today or (be-dt.timedelta(seconds=1)).astimezone(TZ).date()==today): continue
        act=bs<=now<be
        today_blocks.append({"start":bs.isoformat(),"end":be.isoformat(),"tokens":v["tok"],
            "cost_usd":round(v["cost"],2),"pct":(round(off5,1) if act and off5 is not None else bpct(bs,v["tok"])),
            "estimated": not (act and off5 is not None and win_start is not None), "active":act})
    def daylist(pred):
        out=[]
        for d,v in sorted(days.items()):
            dd=dt.date.fromisoformat(d)
            if pred(dd): out.append({"date":d,"tokens":v["tok"],"cost_usd":round(v["cost"],2),"blocks":len(v["blk"])})
        return out
    week=daylist(lambda d: wkstart<=d<=today); history=daylist(lambda d: d<wkstart)[-30:]
    el=round(100*max(0,min(1,(now-win_start).total_seconds()/(BLOCK_H*3600))),1) if (win_start and win_end) else None
    pace=None; eta=None
    if off5 is not None and el is not None:
        pace="baja el ritmo" if off5>el+5 else ("holgado" if off5<el-5 else "en ritmo")
        if el>2:
            proj=round(off5/el*100,0); eta={"projected_end_pct":min(999,proj)}
            if proj>=100 and off5<100 and win_start:
                rate=off5/max(1,(now-win_start).total_seconds()/60)
                if rate>0: eta["exhaust_in_min"]=round((100-off5)/rate)
    current={"official_available":api_ok and off5 is not None,"pct":off5,"resets_at":fh.get("resets_at"),
      "elapsed_pct":el,"pace_label":pace,"eta":eta,
      "cost_usd":next((b["cost_usd"] for b in today_blocks if b["active"]),None),
      "tokens_active":active_tok,"derived_limit":round(derived_limit) if derived_limit else None,
      "low_confidence":LOW_CONF,
      "weekly":{"official_available":api_ok and off7 is not None,"pct":off7,"resets_at":sd.get("resets_at")}}
    # sostenibilidad
    def sustainable():
        if off7 is None or not sd.get("resets_at"): return {}
        try: wend=dt.datetime.fromisoformat(sd["resets_at"])
        except: return {}
        days_left=(wend-now).total_seconds()/86400.0; days_elapsed=7-days_left; W_left=100-off7
        out={"days_left":round(max(0,days_left),2),"elapsed_pct":round(100*max(0,min(1,days_elapsed/7)),1)}
        out["pace_delta"]=round(off7-out["elapsed_pct"],1)
        if days_elapsed>0.1 and off7>=1:
            out["runway_days"]=round(min(999,W_left*days_elapsed/off7),1); out["proj_at_reset"]=min(999,round(off7/(days_elapsed/7.0)))
        rd=out.get("runway_days")
        out["status"]="early" if (days_elapsed<=0 or rd is None) else ("under" if rd>=days_left*1.15 else ("on" if rd>=days_left*0.85 else "over"))
        pcts=[b["pct"] for b in today_blocks if b.get("pct") is not None]
        if rd is not None and days_left>0.2 and off7>=1:
            out["ceiling_pct"]=max(0,min(100,round(100*rd/days_left)))
            if pcts: out["ceiling_basis_pct"]=round(sum(pcts)/len(pcts))
        return out
    current["weekly"].update(sustainable())
    data={"generated_at":now.isoformat(),"tz":"America/Lima","api_ok":api_ok,
      "api_fail_since":api_fail_since,
      "source":"official (anthropic oauth usage api)" if api_ok else "NO API",
      "current":current,"today_blocks":today_blocks,"week":week,"history":history,
      "sessions":sessions_info(summaries),"sessions_generated_at":now.isoformat(),
      "week_start":wkstart.isoformat(),"today":today.isoformat()}
    atomic("/opt/claude-usage-web/data.json", data)
    print(json.dumps(data,indent=1,default=str))

def sessions_info(summaries):
    now=now_utc(); live=set()
    for c in glob.glob("/proc/[0-9]*/cmdline"):
        try: cl=open(c,"rb").read().replace(b"\x00",b" ").decode("utf-8","ignore")
        except: continue
        m=re.search(r"--remote-control\s+(\S+)", cl)
        if m: live.add(m.group(1))
    outdir="/opt/claude-usage-web/session"
    try: os.makedirs(outdir,exist_ok=True)
    except: pass
    # newest file por dir (de los ya cacheados)
    newest_by_dir={}
    for f in summaries:
        d=os.path.dirname(f); mt=os.path.getmtime(f)
        if d not in newest_by_dir or mt>newest_by_dir[d][1]: newest_by_dir[d]=(f,mt)
    out=[]; kept_slugs=set()
    for d,(newest,nmt) in sorted(newest_by_dir.items()):
        s=summaries.get(newest)
        if not s or not s.get("last"): continue
        sid=os.path.basename(newest)[:-6]
        last=s["last"]; results=set(s["results"]); tn=s["tn"]
        base=os.path.basename(d)
        folder=base.split("-workspace-")[-1] if "-workspace-" in base else ("workspace" if base=="-workspace" else base)
        safe=re.sub(r"[^A-Za-z0-9_.-]","_",folder) or "root"
        win=WINDOW[fam(last[1])]
        tasks=[]; tdir=f"{TASKS}/{sid}"
        if os.path.isdir(tdir):
            for tf in glob.glob(tdir+"/*.json"):
                try:
                    td=json.load(open(tf))
                    tasks.append({"id":str(td.get("id")),"subject":redact(td.get("subject") or "")[:300],
                        "status":td.get("status") or "pending","blockedBy":[str(x) for x in (td.get("blockedBy") or [])]})
                except: continue
            tasks.sort(key=lambda x:(int(x["id"]) if str(x["id"]).isdigit() else 999))
        dead=("completed","done","cancelled")
        open_t=sum(1 for t in tasks if t["status"] not in dead)
        done_t=sum(1 for t in tasks if t["status"] in ("completed","done"))
        tot_t=sum(1 for t in tasks if t["status"]!="cancelled")
        def wst(wid):
            st=tn.get(wid)
            if st in ("completed","success"): return "done"
            if st in ("failed","error"): return "failed"
            return "running"
        subs=[{"type":a["type"],"desc":a["desc"],"status":("done" if i in results else "running")} for i,a in s["agents"].items()]
        wfl=[{"desc":w["desc"],"phases":w["phases"],"status":wst(w["id"])} for w in s["wf"]]
        try: age=(now-dt.datetime.fromisoformat(last[0].replace("Z","+00:00"))).total_seconds()/60
        except: age=None
        if age is None or age>30:
            for x in subs+wfl:
                if x["status"]=="running": x["status"]="unknown"
        last_age=round(age) if age is not None else None
        toolc=Counter(s["tools"])
        full={"folder":folder,"model":last[1],"gitBranch":s["gitb"],"context":last[2],"window":win,
              "pct":round(100*last[2]/win,1),"messages":s["nmsg"],"first":s["first"],"last":last[0],"last_age_min":last_age,
              "cost_usd":round(s["cost"],2),"active":folder in live,
              "tasks":tasks,"tasks_open":open_t,"tasks_done":done_t,"tasks_total":tot_t,
              "subagents":subs,"subagents_running":sum(1 for x in subs if x["status"]=="running"),
              "workflows":wfl,"workflows_running":sum(1 for x in wfl if x["status"]=="running"),
              "tools":dict(toolc.most_common(30)),"timeline":s["timeline"][-60:]}
        try: atomic(f"{outdir}/{safe}.json", full)
        except: pass
        kept_slugs.add(safe+".json")
        detail={"messages":s["nmsg"],"tools":dict(toolc.most_common(6)),
                "subagents_total":len(subs),"subagents_running":full["subagents_running"],
                "workflows_total":len(wfl),"workflows_running":full["workflows_running"],
                "tasks_open":open_t,"tasks_done":done_t,"tasks_total":tot_t,"gitBranch":s["gitb"],"slug":safe}
        out.append({"folder":folder,"model":last[1],"context":last[2],"window":win,
            "pct":round(100*last[2]/win,1),"last":last[0],"last_age_min":last_age,"mtime":nmt,
            "active":folder in live,"detail":detail})
    # M6 fix: prune session/<slug>.json files for projects that fell out of
    # this run's window (recent_top_files/MTIME_DAYS) so a dormant project's
    # last-known snapshot doesn't keep being served at a guessable URL forever.
    try:
        for fn in os.listdir(outdir):
            if fn.endswith(".json") and fn not in kept_slugs:
                try: os.remove(f"{outdir}/{fn}")
                except: pass
    except: pass
    out.sort(key=lambda x:(x["active"],x["mtime"]),reverse=True)
    return out[:16]

if __name__=="__main__":
    import sys
    main(fast="--fast" in sys.argv)
