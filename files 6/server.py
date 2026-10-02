"""BedLink backend (stdlib only). Ambulance -> backend (triage) -> Hospital + Dispatch, pushed live over SSE.
Run: python3 server.py [port]. Triage score = transparent rule-based DEMO score, not clinical guidance."""
import json, os, queue, sys, threading, time, copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOCK, CLIENTS = threading.RLock(), []
def now(): return time.strftime("%H:%M:%S")
CAP = ["ICU Beds", "Emergency Beds", "Trauma Bays", "Ventilators", "Operating Rooms"]
SUP = ["Blood Units", "Oxygen Cylinders", "Ventilator Supplies", "Emergency Medication", "Trauma Kits", "IV Fluids", "PPE Kits", "Surgical Supplies"]
W = {"resource": 40, "bed": 20, "travel": 20, "freshness": 10, "load": 10}  # Operation Match weights (operational demo score)
def seed_hospitals():
    t = time.time()
    def H(name, km, cap, sup, age):
        ts = t - age  # each value: [available, total/required, last_updated_epoch]
        return dict(name=name, km=km, accepting=True, capacity={k: [v[0], v[1], ts] for k, v in zip(CAP, cap)}, supplies={k: [v[0], v[1], ts] for k, v in zip(SUP, sup)},
                    staff={r: "AVAILABLE" for r in ["Trauma Surgeon", "Emergency Physician", "Cardiologist", "Anesthesiologist", "Nurses", "Paramedics"]}, log=[])
    return {"citycare": H("CityCare General Hospital", 5.3, [(4,12),(7,20),(3,8),(5,10),(2,6)], [(42,80),(42,60),(18,30),(30,60),(9,20),(55,100),(60,100),(64,100)], 8),
            "metrocare": H("MetroCare Hospital", 7.4, [(2,10),(9,18),(1,6),(3,8),(1,4)], [(30,60),(25,40),(12,20),(40,60),(6,15),(70,100),(80,100),(50,80)], 20),
            "apollo": H("Apollo Emergency Center", 11.0, [(6,14),(5,16),(5,8),(7,10),(3,6)], [(70,90),(50,60),(20,30),(55,60),(14,20),(90,100),(85,100),(70,80)], 15),
            "sunrise": H("Sunrise Medical Center", 8.2, [(3,8),(6,12),(2,5),(2,6),(1,3)], [(25,50),(15,40),(8,15),(20,40),(4,10),(40,80),(50,80),(30,60)], 45),
            "stmary": H("St. Mary's Hospital", 9.6, [(2,6),(10,22),(1,4),(2,5),(1,3)], [(18,40),(20,30),(5,12),(25,40),(3,8),(30,60),(40,60),(22,50)], 400)}

def fresh():
    return {"ambulances": {
        "AMB-204": dict(id="AMB-204", status="AVAILABLE", level="—", loc="Station 4", dest="—", speed=0, eta=None, crew=["R. Mehta (Paramedic)", "S. Iyer (EMT)"], patient=None, vitals=None, score=None, prev=None, progress=0.0, accepted=False, hist=[]),
        "AMB-118": dict(id="AMB-118", status="AT SCENE", level="HIGH", loc="Andheri Flyover", dest="MetroCare", speed=0, eta=None, crew=["A. Khan (Paramedic)"], patient={"id": "P-0118", "age": 41, "type": "Cardiac"}, vitals=dict(hr=110, spo2=93, sys=100, dia=70, rr=22), score=58, prev=None, progress=0.0, accepted=False, hist=[]),
        "AMB-302": dict(id="AMB-302", status="AVAILABLE", level="—", loc="Depot", dest="—", speed=0, eta=None, crew=["D. Roy (Paramedic)"], patient=None, vitals=None, score=None, prev=None, progress=0.0, accepted=False, hist=[])},
     "hospitals": seed_hospitals(), "matches": {}, "scores": {}, "weights": W, "now": time.time(),
     "events": [], "api_log": []}
S = fresh()

def triage(v, kind):  # transparent weights; DEMO score only
    s = min(40, max(0, 95 - v["spo2"]) * 5) + min(25, max(0, v["hr"] - 100) * .9) + min(25, max(0, 110 - v["sys"]) * .8) + min(10, max(0, v["rr"] - 20) * 1.5)
    return int(min(100, s + (8 if kind == "Trauma" else 0)))
def level(sc): return "CRITICAL" if sc >= 75 else "HIGH" if sc >= 50 else "MODERATE"
def ev(src, msg, crit=False, amb=None, hid=None):
    S["events"].insert(0, dict(t=now(), src=src, msg=msg, crit=crit, amb=amb)); del S["events"][200:]
    hid = hid or (S["ambulances"].get(amb, {}).get("hospital") if src == "hospital" else None)
    if hid: S["hospitals"][hid]["log"].insert(0, dict(t=now(), ts=time.time(), cat="emergency", name=amb, prev=None, new=None, by="System", msg=msg))
def amb(i):
    if i not in S["ambulances"]: raise ValueError(f"Unknown ambulance {i}")
    return S["ambulances"][i]
def set_vitals(a, v, note="Patient vitals updated"):
    v = dict(v); v.setdefault("temp", (a.get("vitals") or {}).get("temp", 36.8)); a["vitals"] = v; a["prev"] = a["score"]; a["score"] = triage(v, (a["patient"] or {}).get("type")); a["level"] = level(a["score"])
    a["hist"].append(dict(t=now(), **v)); a["hist"] = a["hist"][-20:]
    ev("ambulance", f'{a["id"]} {note}: SpO₂ {v["spo2"]}%, HR {v["hr"]}, BP {v["sys"]}/{v["dia"]}', a["level"] == "CRITICAL", a["id"])
    if a["prev"] is not None and a["prev"] != a["score"]: ev("dispatch", f'Triage score changed: {a["prev"]} → {a["score"]} ({a["id"]})', a["level"] == "CRITICAL", a["id"])


# ---------- hospital data entry, lookup assistant (database/keyword based, no LLM), Operation Match ----------
SCEN = {  # configurable demo knowledge (not clinical protocol)
 "chest": dict(kw=["chest pain", "heart", "cardiac"], label="Suspected cardiac emergency", type="Cardiac", pri="CRITICAL", req=["ICU", "Emergency Bed", "Oxygen", "Emergency Medication"], vit=dict(hr=118, spo2=92, sys=96, dia=64, rr=24)),
 "accident": dict(kw=["accident", "crash", "collision", "road"], label="Critical trauma", type="Trauma", pri="CRITICAL", req=["ICU", "Trauma Bay", "Blood", "Emergency Surgery", "Ventilator"], vit=dict(hr=128, spo2=89, sys=90, dia=60, rr=26)),
 "breath": dict(kw=["breath", "asthma", "respiratory"], label="Respiratory distress", type="Respiratory", pri="CRITICAL", req=["ICU", "Oxygen", "Ventilator"], vit=dict(hr=112, spo2=86, sys=110, dia=70, rr=30)),
 "stroke": dict(kw=["stroke", "droop", "slurred"], label="Suspected stroke", type="Neurological", pri="HIGH", req=["ICU", "Emergency Bed", "Emergency Medication"], vit=dict(hr=96, spo2=95, sys=170, dia=100, rr=18)),
 "bleed": dict(kw=["bleed", "hemorrhage"], label="Major bleeding", type="Trauma", pri="CRITICAL", req=["Trauma Bay", "Blood", "Emergency Surgery", "IV Fluids"], vit=dict(hr=124, spo2=93, sys=88, dia=55, rr=24)),
 "unconscious": dict(kw=["unconscious", "unresponsive", "collapsed"], label="Altered consciousness", type="Medical", pri="CRITICAL", req=["ICU", "Oxygen", "Emergency Bed"], vit=dict(hr=60, spo2=90, sys=100, dia=60, rr=10)),
 "fever": dict(kw=["fever", "temperature"], label="High fever", type="Medical", pri="MODERATE", req=["Emergency Bed", "IV Fluids"], vit=dict(hr=104, spo2=96, sys=112, dia=72, rr=20, temp=38.9))}
RES = {"ICU": ("capacity", "ICU Beds"), "Trauma Bay": ("capacity", "Trauma Bays"), "Emergency Bed": ("capacity", "Emergency Beds"), "Ventilator": ("capacity", "Ventilators"), "Emergency Surgery": ("capacity", "Operating Rooms"),
       "Blood": ("supplies", "Blood Units"), "Oxygen": ("supplies", "Oxygen Cylinders"), "Emergency Medication": ("supplies", "Emergency Medication"), "IV Fluids": ("supplies", "IV Fluids")}
RES_KW = [("icu", "ICU"), ("trauma", "Trauma Bay"), ("ventilator", "Ventilator"), ("oxygen", "Oxygen"), ("blood", "Blood"), ("surgery", "Emergency Surgery"), ("operating", "Emergency Surgery"), ("emergency bed", "Emergency Bed")]

def match(req, t):
    out = []
    for hid, h in S["hospitals"].items():
        items = [dict(name=r, ok=h[RES[r][0]][RES[r][1]][0] > 0, qty=h[RES[r][0]][RES[r][1]][0]) for r in req]
        ages = [t - h[RES[r][0]][RES[r][1]][2] for r in req]
        bed = next((RES[r][1] for r in req if RES[r][1] in ("ICU Beds", "Trauma Bays", "Emergency Beds")), "Emergency Beds"); bq = h["capacity"][bed][0]
        age = max(ages) if ages else 0; eta = round(h["km"] * 1.5)
        core = [h["capacity"][k] for k in ("ICU Beds", "Emergency Beds", "Trauma Bays")]; load = 1 - sum(c[0] for c in core) / sum(c[1] for c in core)
        fr = dict(resource=sum(i["ok"] for i in items) / len(items), bed=0 if bq == 0 else 1 if bq >= 2 else .6, travel=max(0, 1 - eta / 30),
                  freshness=1 if age < 30 else 1 - (age - 30) / 540 if age < 300 else max(0, .5 * (900 - age) / 600), load=1 - load)
        pts = {k: round(W[k] * v, 1) for k, v in fr.items()}
        out.append(dict(id=hid, name=h["name"], score=round(sum(pts.values())), eta=eta, km=h["km"], load=round(load * 100), res=items, bed=dict(name=bed, avail=bq, ok=bq > 0),
                        fresh=dict(age=int(age), state="LIVE" if age < 60 else "AGING" if age < 900 else "STALE"), fr=fr, pts=pts, ok=fr["resource"] == 1 and bq > 0))
    return sorted(out, key=lambda m: -m["score"])

def hospital_has_resources(h, required):
    return all(h[RES[r][0]][RES[r][1]][0] > 0 for r in required)

def refresh():
    S["now"] = t = time.time()
    for aid, a in S["ambulances"].items():
        if not a.get("need"): continue
        ms = S["matches"][aid] = match(a["need"]["req"], t); rec = S["scores"].setdefault(aid, {})
        for m in ms:
            r = rec.get(m["id"])
            if r is None: rec[m["id"]] = r = dict(last=m["score"], prev=None)
            elif abs(m["score"] - r["last"]) >= 3: ev("dispatch", f'Operation Match: {m["name"]} {r["last"]} → {m["score"]}', False, aid); r["prev"], r["last"] = r["last"], m["score"]
            m["prev"] = r["prev"]
    return expire()

def q_resource(b):
    h = S["hospitals"].get(b.get("hospital")); kind, name = b.get("kind"), b.get("name")
    if not h or kind not in ("capacity", "supplies") or name not in h[kind]: raise ValueError("Unknown hospital or resource")
    r = h[kind][name]; prev = r[0]; d = int(b["delta"]); new = max(0, min(r[1] if kind == "capacity" else 9999, prev + d))
    if new == prev: raise ValueError(f"{name} is already at its {'minimum' if d < 0 else 'maximum'}")
    r[0], r[2] = new, time.time(); h["log"].insert(0, dict(t=now(), ts=r[2], cat=kind, name=name, prev=prev, new=new, by="Emergency Staff")); del h["log"][100:]
    ev("hospital", f'{h["name"]}: staff updated {name}: {prev} → {new}')

def q_staff(b):
    h = S["hospitals"][b["hospital"]]; cur = h["staff"][b["role"]]; nxt = {"AVAILABLE": "BUSY", "BUSY": "OFF DUTY", "OFF DUTY": "AVAILABLE"}[cur]; h["staff"][b["role"]] = nxt
    h["log"].insert(0, dict(t=now(), ts=time.time(), cat="staff", name=b["role"], prev=cur, new=nxt, by="Emergency Staff")); ev("hospital", f'{h["name"]}: {b["role"]} {cur} → {nxt}')

def q_fresh(b):  # demo control: age all data by 18 min, or staff "verify" (re-stamp) all values
    h = S["hospitals"][b["hospital"]]; age = b.get("mode") == "age"
    for grp in (h["capacity"], h["supplies"]):
        for r in grp.values(): r[2] = r[2] - 1080 if age else time.time()
    h["log"].insert(0, dict(t=now(), ts=time.time(), cat="system", name="All data", prev=None, new=None, by="Emergency Staff", msg="Data aged 18 min (demo)" if age else "Staff verified all values"))
    ev("hospital", f'{h["name"]}: ' + ("data aged 18 min (demo)" if age else "all values verified"))

def q_query(b):
    a = amb(b.get("id", "AMB-204")); text = str(b.get("text", "")).strip()[:300]; t = text.lower(); chat = a.setdefault("chat", [])
    if not text: raise ValueError("Type a question or pick a demo prompt")
    chat.append(dict(r="user", m=text)); sc = next((s for s in SCEN.values() if any(k in t for k in s["kw"])), None)
    if sc:
        a.update(status="EMERGENCY", eta=8, speed=62, progress=.05, accepted=False, hospital=None, request=None, dest="—", loc="Highway 7, Sector 12", need=dict(label=sc["label"], pri=sc["pri"], req=sc["req"]), patient={"id": "P-" + a["id"][-3:] + "7", "age": 34, "type": sc["type"]})
        set_vitals(a, sc["vit"]); ev("ambulance", f'{a["id"]} emergency declared: {sc["label"]} (as stated by crew)', sc["pri"] == "CRITICAL", a["id"])
    else:
        req = list(dict.fromkeys(r for k, r in RES_KW if k in t))
        if not req: chat.append(dict(r="bot", m="I can look up ICU beds, trauma bays, ventilators, oxygen, blood or operating rooms, or take a patient description (chest pain, road accident, breathing difficulty…).")); return
        a["need"] = dict(label="Resource lookup", pri="INFO", req=req)
    S["scores"][a["id"]] = {}; refresh(); ms = S["matches"][a["id"]]; ok = [m for m in ms if m["ok"]]; top = ms[0]
    head = f'Scenario as stated: {a["need"]["label"]} (not a diagnosis). ' if sc else ""
    chat.append(dict(r="bot", m=head + f'Required: {", ".join(a["need"]["req"])}. ' + (f'{len(ok)} of {len(ms)} hospitals have all of it. Best: {top["name"]}, score {top["score"]}, ETA {top["eta"]} min.' if ok else "No hospital has all of these right now; closest partial matches are shown.")))

DECLINE_REASONS = ["No ICU capacity", "No trauma bed", "Resources unavailable", "Emergency department overloaded", "Other"]
def stamp(): return time.strftime("%Y-%m-%d %H:%M:%S")

HOLD = int(os.environ.get("BEDLINK_HOLD", "120"))  # seconds each offered hospital has to confirm (env override is for testing only)
def mmss(sec): return f"{sec // 60:02d}:{sec % 60:02d}"

def next_hospital(a, r):  # deterministic: best-ranked hospital (existing Operation Match order) not yet tried, with all required resources + a bed, and accepting patients
    tried = {t["hospital_id"] for t in r["attempts"]}
    ms = S["matches"].get(a["id"]) or match(r["required"] or ["Emergency Bed"], time.time())
    return next((m for m in ms if m["id"] not in tried and m["ok"] and S["hospitals"][m["id"]]["accepting"]), None)

def offer(a, hid):  # make hospital `hid` the ONLY hospital holding this request, with its own fresh countdown
    r = a["request"]; h = S["hospitals"][hid]; m = next((m for m in S["matches"].get(a["id"], []) if m["id"] == hid), None)
    r.update(hospital_id=hid, hospital_name=h["name"], status="PENDING", state="Awaiting Confirmation", eta=m["eta"] if m else round(h["km"] * 1.5), offered_at=stamp(), decision_at=None, decline_reason=None, deadline=time.time() + HOLD, hold=HOLD)
    ev("ambulance", f'Acceptance requested from {h["name"]}: awaiting confirmation ({mmss(HOLD)} to respond)', False, a["id"])
    ev("hospital", f'INCOMING AMBULANCE REQUEST {a["id"]}: {r["condition"]}, triage {r["triage_score"]}, ETA {r["eta"]} min. Confirm within {mmss(HOLD)}', a["level"] == "CRITICAL", a["id"], hid)
    ev("dispatch", f'{a["id"]} → {h["name"]}: awaiting confirmation ({mmss(HOLD)})', False, a["id"])

def advance(a, r, outcome, reason=None):  # current hospital DECLINED / TIMED_OUT -> record it, then offer to the next-best hospital (or stop)
    r["attempts"].append(dict(hospital_id=r["hospital_id"], hospital_name=r["hospital_name"], outcome=outcome, reason=reason, at=stamp()))
    nxt = next_hospital(a, r)
    if nxt: ev("ambulance", f'{r["hospital_name"]} {"declined" if outcome == "DECLINED" else "timed out"}: offering to next-best hospital, {nxt["name"]}', False, a["id"]); offer(a, nxt["id"])
    else:
        r.update(hospital_id=None, status="NO_HOSPITAL", state="No Suitable Hospital Available", deadline=None, decision_at=stamp())
        msg = f'{a["id"]}: no suitable hospital available (all candidates declined or timed out)'; ev("ambulance", msg, True, a["id"]); ev("dispatch", msg, True, a["id"])

def expire():  # TIMEOUT: offer reached 00:00 with no decision
    changed, t = False, time.time()
    for a in S["ambulances"].values():
        r = a.get("request")
        if r and r["status"] == "PENDING" and r.get("deadline") and t >= r["deadline"] and a["status"] not in ("AVAILABLE", "ARRIVED"):
            hid, name = r["hospital_id"], r["hospital_name"]; msg = f'{name} did not respond to {a["id"]} within {mmss(HOLD)}: request timed out'
            ev("hospital", msg, False, a["id"], hid); ev("dispatch", msg, False, a["id"]); advance(a, r, "TIMED_OUT"); changed = True
    return changed

def q_request(b):  # ambulance -> ONE chosen hospital. Only creates a PENDING request: no bed/bay reserved, no status/destination/capacity change.
    a = amb(b["id"]); hid = b.get("hospital")
    if hid not in S["hospitals"]: raise ValueError("Unknown hospital")
    if not a.get("patient") or not a.get("vitals") or a["status"] in ("AVAILABLE", "ARRIVED"): raise ValueError("Pick a patient scenario first")
    required = list((a.get("need") or {}).get("req", []))
    if not hospital_has_resources(S["hospitals"][hid], required):
        raise ValueError("This hospital does not have all required equipment or bed capacity")
    cur = a.get("request")
    if cur and cur["status"] == "PENDING": raise ValueError(f'Request to {cur["hospital_name"]} is still awaiting a hospital decision')
    if cur and cur["status"] == "ACCEPTED": raise ValueError(f'{cur["hospital_name"]} has already accepted {a["id"]}')
    a["request"] = dict(ambulance_id=a["id"], hospital_id=None, hospital_name=None, status="PENDING", state="Awaiting Confirmation", condition=f'{a["level"].title()} {a["patient"]["type"]} Patient', triage_score=a["score"], level=a["level"],
                        required=list((a.get("need") or {}).get("req", [])), eta=None, created_at=stamp(), decision_at=None, decline_reason=None, attempts=[], deadline=None, hold=HOLD, offered_at=None)
    offer(a, hid)

def decision(b):  # shared guard: only the hospital the request was sent to may decide, and only while PENDING
    a = amb(b["id"]); r = a.get("request")
    if not r: raise ValueError("No hospital request for this ambulance")
    if b.get("hospital") != r["hospital_id"]: raise ValueError("This request was not sent to that hospital")
    if r["status"] != "PENDING": raise ValueError(f'Request already {r["status"].lower()}')
    if a["status"] in ("AVAILABLE", "ARRIVED"): raise ValueError("No active incoming patient")
    return a, r, S["hospitals"][r["hospital_id"]]

def q_accept(b):  # the ONLY place a request goes PENDING -> ACCEPTED (explicit hospital ACCEPT click)
    a, r, h = decision(b); hid = r["hospital_id"]
    if not hospital_has_resources(h, r["required"]):
        raise ValueError("Cannot accept: required equipment or bed capacity is unavailable")
    r.update(status="ACCEPTED", state="Accepted", confirmed=True, deadline=None, decision_at=stamp())  # stops the countdown + the chain
    a.update(accepted=True, status="EN ROUTE", hospital=hid, dest=h["name"], eta=r["eta"])
    h["capacity"]["Emergency Beds"][0] = max(0, h["capacity"]["Emergency Beds"][0] - 1); h["capacity"]["Emergency Beds"][2] = time.time()
    msg = f'{h["name"]} accepted {a["id"]}'
    ev("hospital", msg, False, a["id"], hid); ev("ambulance", msg, False, a["id"]); ev("dispatch", msg, False, a["id"])

def q_decline(b):  # the ONLY place a request goes PENDING -> DECLINED (explicit hospital DECLINE click)
    a, r, h = decision(b); hid = r["hospital_id"]; reason = b.get("reason") or None
    if reason not in (None, *DECLINE_REASONS): raise ValueError("Unknown decline reason")
    msg = f'{h["name"]} declined {a["id"]}' + (f': {reason}' if reason else "")
    ev("hospital", msg, False, a["id"], hid); ev("ambulance", msg, False, a["id"]); ev("dispatch", msg, False, a["id"])
    advance(a, r, "DECLINED", reason)  # immediately offer to next-best hospital with a fresh countdown

NEW = {"/api/hospital/resource": q_resource, "/api/hospital/staff": q_staff, "/api/hospital/freshness": q_fresh, "/api/ambulance/query": q_query, "/api/ambulance/hospital-request": q_request, "/api/ambulance/select": q_request, "/api/hospital/accept": q_accept, "/api/hospital/decline": q_decline}
def ticker():
    tick = 0
    while True:
        time.sleep(1); tick += 1
        with LOCK:
            changed = refresh()  # expires timed-out offers and moves them to the next hospital
            if changed or tick % 5 == 0: push()  # push immediately on a timeout, else every 5s to keep freshness-driven scores live

def route(method, path, b):
    refresh()
    if method == "GET":
        if path in ("/api/state", "/api/ambulances", "/api/hospitals", "/api/hospital/resources", "/api/events"):
            return {"/api/ambulances": list(S["ambulances"].values()), "/api/hospitals": [h["name"] for h in S["hospitals"].values()], "/api/hospital/resources": S["hospitals"], "/api/events": S["events"]}.get(path, S)
        raise KeyError(path)
    if path == "/api/ambulance/alert":
        a = amb(b["id"])
        if a["status"] in ("AVAILABLE", "ARRIVED"): a.update(hospital=None, request=None, accepted=False, dest="—")  # new emergency: no hospital chosen yet
        a.update(status="EMERGENCY", eta=int(b.get("eta", 7)), speed=62, progress=0.05, loc="Highway 7, Sector 12", patient={"id": "P-" + a["id"][-3:] + "7", "age": int(b.get("age", 34)), "type": b.get("type", "Trauma")})
        ev("ambulance", f'{a["id"]} emergency declared ({a["patient"]["type"]})', True, a["id"]); set_vitals(a, b.get("vitals") or dict(hr=128, spo2=89, sys=90, dia=60, rr=26)); ev("dispatch", f'{a["id"]} emergency alert: triage {a["score"]}, ETA {a["eta"]} min. No hospital selected yet', a["level"] == "CRITICAL", a["id"])
    elif path == "/api/ambulance/vitals": a = amb(b["id"]); set_vitals(a, {**{k: int(b["vitals"][k]) for k in ("hr", "spo2", "sys", "dia", "rr")}, **({"temp": float(b["vitals"]["temp"])} if "temp" in b["vitals"] else {})})
    elif path == "/api/ambulance/location":
        a = amb(b["id"]); a["progress"] = min(1.0, a["progress"] + .15); a["eta"] = max(0, (a["eta"] or 0) - 1); a["loc"] = b.get("loc", f'En route · {int(a["progress"]*100)}% to hospital'); ev("dispatch", f'{a["id"]} location updated, ETA {a["eta"]} min', False, a["id"])
    elif path == "/api/ambulance/action":
        a, act = amb(b["id"]), b["action"]
        if not a["vitals"]: raise ValueError("Send an emergency alert first")
        if act == "worsen": v = dict(a["vitals"]); v.update(hr=v["hr"] + 10, spo2=v["spo2"] - 4, sys=v["sys"] - 8, temp=round(v.get("temp", 36.8) + .3, 1)); set_vitals(a, v, "condition worsening")
        elif act == "stable": set_vitals(a, dict(hr=88, spo2=97, sys=118, dia=76, rr=16, temp=36.8), "marked stable")
        elif act == "request": a["status"] = "REQUESTED"; ev("hospital", f'{a["id"]} requests hospital bed', False, a["id"])
        elif act == "arrived": a.update(status="ARRIVED", eta=0, progress=1.0, speed=0, loc="CityCare Emergency Bay"); ev("hospital", f'{a["id"]} arrived — patient handed over', False, a["id"])
        else: raise ValueError("Unknown action")
    elif path == "/api/hospital/prepare":
        a = amb(b["id"]); r = a.get("request")
        if not r or r["status"] != "ACCEPTED": raise ValueError("Accept the ambulance before preparing a trauma bay")
        if a["status"] in ("AVAILABLE", "ARRIVED"): raise ValueError("No active incoming patient")
        h = S["hospitals"][r["hospital_id"]]
        h["capacity"]["Trauma Bays"][0] = max(0, h["capacity"]["Trauma Bays"][0] - 1); h["staff"]["Trauma Surgeon"] = "BUSY"; ev("hospital", "Trauma bay prepared; trauma surgeon notified", False, a["id"])
    elif path in NEW: NEW[path](b)
    elif path == "/api/demo/reset": S.clear(); S.update(fresh())
    else: raise KeyError(path)
    return {"ok": True}

def demo():  # simulates the AMBULANCE side only; hospital ACCEPT/DECLINE is never simulated
    for p, d, w in [("/api/ambulance/query", {"id": "AMB-204", "text": "Road Accident"}, 1.5), ("/api/ambulance/alert", {"id": "AMB-204", "vitals": dict(hr=104, spo2=94, sys=108, dia=70, rr=21)}, 1.5), ("/api/ambulance/location", {"id": "AMB-204"}, 1.5),
                    ("/api/ambulance/action", {"id": "AMB-204", "action": "worsen"}, 1.5), ("/api/ambulance/action", {"id": "AMB-204", "action": "worsen"}, 1.5),
                    ("/api/ambulance/hospital-request", {"id": "AMB-204", "hospital": "citycare"}, 1.5), ("/api/ambulance/location", {"id": "AMB-204"}, 1.5)]:
        with LOCK:
            try: route("POST", p, d); push()
            except ValueError: pass
        time.sleep(w)

def push():
    refresh(); msg = json.dumps(S); [q.put(msg) for q in list(CLIENTS)]

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, o): d = json.dumps(o).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def _api(self, m):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}") if m == "POST" else {}
        with LOCK:
            try:
                if self.path == "/api/demo": threading.Thread(target=demo, daemon=True).start(); code, out = 200, {"ok": True}
                else: out, code = route(m, self.path, body), 200
            except (KeyError, ValueError, TypeError) as e: out, code = {"error": {"code": "BAD_REQUEST", "message": str(e)}}, 422
            if self.path != "/api/state": S["api_log"].insert(0, dict(t=now(), m=m, p=self.path, s=code)); del S["api_log"][30:]
            if m == "POST": push()
        self._j(code, out)
    def do_POST(self): self._api("POST")
    def do_GET(self):
        if self.path == "/api/stream":
            q = queue.Queue(); CLIENTS.append(q); self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.end_headers()
            try:
                with LOCK: refresh(); q.put(json.dumps(S))
                while True:
                    try: self.wfile.write(f"data: {q.get(timeout=15)}\n\n".encode())
                    except queue.Empty: self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except Exception: pass
            finally: CLIENTS.remove(q)
        elif self.path.startswith("/api/"): self._api("GET")
        else:
            d = (Path(__file__).parent / "index.html").read_bytes(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)

if __name__ == "__main__":
    threading.Thread(target=ticker, daemon=True).start(); p = int(sys.argv[1]) if len(sys.argv) > 1 else 8100; print(f"BedLink on http://localhost:{p}"); ThreadingHTTPServer(("0.0.0.0", p), H).serve_forever()
