#!/usr/bin/env python3
"""Generate TREE.md from the node data inside index.html.

The tree's structure is defined once, in the NODES array of index.html. This
reads it back out so the reference document can never drift from the thing it
documents — every prerequisite, XP value and connection below is the live one.

The prose that cannot be derived — what a node actually entails, how you know
it is done, what people mistake for it — lives in DETAIL here.

    python3 scripts/make_docs.py
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "index.html")
OUT = os.path.join(ROOT, "TREE.md")

TRACKS = {
    "money": ("💰", "Money", "Revenue, collected and repeatable."),
    "skill": ("🧠", "Skills", "The capabilities that produce the revenue."),
    "body":  ("💪", "Body", "The machine you run everything else on."),
    "mind":  ("🧘", "Mindset", "Behaviour under load, and the financial floor."),
    "drive": ("🏁", "Driving", "Being able to drive it before you can afford it."),
    "apex":  ("🏆", "Convergence", "Where the tracks meet and the run-up begins."),
    "boss":  ("🏎️", "Final Boss", "The machine."),
}

# id -> (what it entails, done when, watch out for)
DETAIL = {
1: ("One calendar month in which £1,000 lands in your account from work you own — "
    "not wages, not a gift, not a loan. The number is small on purpose: its only job "
    "is to prove the mechanism exists at all. Everything above this node is that same "
    "mechanism run harder.",
    "£1,000 cleared and collected inside a single calendar month.",
    "Counting invoiced-but-unpaid. Money you have not received is a hope, not a month."),
2: ("The month that stops being pocket money and starts covering a life. Getting here "
    "usually means one of two things changed: you raised prices, or you stopped taking "
    "work that pays badly. Both are decisions, not effort.",
    "£5,000 collected inside a calendar month.",
    "Hitting it once by working a 90-hour month. If it cost you the next month, it did "
    "not count for much."),
3: ("Five figures. This is the level where most people who try this stop, and where the "
    "work shifts from finding any client to running a pipeline. It is also the last "
    "level you can reach purely by doing everything yourself.",
    "£10,000 collected inside a calendar month.",
    "One client being 80% of it. That is not a business, it is a job with extra steps."),
4: ("Twenty thousand in a month, and — the part that matters — a repeat of it. At this "
    "point the question stops being 'can I' and becomes 'what breaks if I do this "
    "again next month'.",
    "£20,000 collected in a month, and the pipeline to see the next one coming.",
    "Treating a spike as a level. A single good month is a data point, not a floor."),
5: ("Fifty thousand a month is where a business stops being a freelancer with good "
    "months. Delivery at this level cannot be only you, which is why the Skills track "
    "starts mattering more than the Money track here.",
    "£50,000 collected in a month, with delivery that survived it.",
    "Selling more than you can deliver. Revenue you have to refund was never revenue."),
6: ("Consistent £100k+ per month. Not a record month — a normal one. This is the node "
    "the whole Money track exists to reach, and the one the endgame is built on top of.",
    "Three consecutive months at £100,000 or more.",
    "Averaging your way there. Three months of £60k, £90k and £150k is not this node."),
26:("A full trading year at seven figures. Twelve months smooths out everything a good "
    "quarter can hide — seasonality, one-off deals, a single client's budget cycle.",
    "£1,000,000 collected across twelve consecutive months.",
    "Confusing contracted value with collected cash. Only what cleared counts."),

7: ("A repeatable outbound motion: a list you can rebuild, a message that gets replies, "
    "and a follow-up sequence you actually run. The skill is not writing one good "
    "email — it is knowing your numbers well enough to predict next month from this "
    "month's sends.",
    "100 contacts sent, with a reply and booking rate you can state from memory.",
    "Volume without measurement. If you cannot name your reply rate, you have not "
    "learned the skill, you have just done the activity."),
8: ("Being able to look at a funnel, find where it leaks, change one thing, and see the "
    "number move. This is the core AIGO skill and it is diagnostic, not creative — the "
    "value is in correctly identifying which stage is broken.",
    "A measured before and after on a real funnel, with the change you made named.",
    "Redesigning the whole funnel. If you change five things you have learned nothing "
    "about any of them."),
9: ("Closing four figures on a live call, repeatedly, without discounting to get there. "
    "The skill is holding the price through the silence.",
    "Three or more four-figure deals closed live, at the price you set.",
    "Closing once and calling it a skill. Three is the minimum sample that separates "
    "ability from a warm lead."),
10:("A working automation stack running on live data — CRM connected, leads routed, "
    "follow-ups firing, and failures visible when they happen. The test is not that "
    "you built it, but that it kept running while you were not watching.",
    "Automations running unattended on real data for 30 consecutive days.",
    "Building the stack as a substitute for outreach. This node is infrastructure, and "
    "infrastructure is the most comfortable place to hide."),
11:("Income that arrives without a new sale — retainers, subscriptions, or managed "
    "service. The distinction from a repeat client is that renewal is the default and "
    "cancellation is the action.",
    "Three consecutive months of recurring income that renewed without being re-sold.",
    "Calling repeat project work recurring. If you have to win it again, it is not."),
12:("The business grows in a month where you personally do less. That is the whole "
    "definition. It requires the recurring revenue underneath it and the six-figure "
    "months beside it, which is why it sits where it does.",
    "A month where revenue rose and your own delivery hours fell.",
    "Scaling the work instead of the system. More clients handled the same way is "
    "volume, not scale."),
27:("The first time someone else's hands are on the work. Usually the hardest single "
    "step in the Skills track, because it converts an implicit process in your head "
    "into something that has to be written down.",
    "One person paid, owning a recurring outcome, for 60 days.",
    "Hiring help instead of hiring ownership. If you still hold the outcome, you have "
    "bought hours, not capacity."),
28:("Five people with defined roles and outcomes they own. At five you can no longer "
    "run everything through yourself informally, which forces the operating structure "
    "the next node depends on.",
    "Five people in defined roles, each owning a named outcome.",
    "Five people all reporting into you for every decision. That is a bottleneck with "
    "a bigger payroll."),
29:("Ninety days at arm's length with the numbers holding. This is the node that makes "
    "the endgame possible: a business that needs you daily cannot fund a car, because "
    "you cannot stop earning long enough to enjoy it.",
    "90 days at arm's length with revenue flat or up.",
    "Being reachable the whole time. If you answered every day, you tested nothing."),

13:("Ninety days of training without a restart. Not a programme, not a split — the "
    "attendance itself. Everything else in this track is downstream of showing up.",
    "90 days logged, three or more sessions a week, with no restart.",
    "Restarting the count after a missed week. Miss one, continue anyway — that is the "
    "skill being tested."),
14:("A physique target you set in advance and then hit. The number matters less than "
    "having named it beforehand, because a goal set afterwards is a description.",
    "A number written down in advance — weight, body fat, or a lift — and reached.",
    "Moving the target once it is close. That converts a goal into a story."),
15:("Twelve months holding an athletic body. Not a peak, a baseline — the point at "
    "which it stops being a project and becomes the default state you return to.",
    "Twelve months inside your target range, holidays and bad months included.",
    "Peaking for photos and drifting for the other ten months."),
16:("The unglamorous half: sleep, protein, and actual recovery. It is a root node with "
    "no prerequisites because it gates the ceiling on everything else in this track, "
    "and you can start it tonight.",
    "Eight weeks of consistent sleep hours, hit protein targets and planned deloads.",
    "Optimising supplements while sleeping six hours. The order matters."),
17:("Strength, composition and the absence of chronic niggles, all at once. Most people "
    "have two of the three at any time; this node is the intersection.",
    "All three holding simultaneously for a full training block.",
    "Trading joints for numbers. A lift that costs you a shoulder is a withdrawal."),
31:("Two years of training with no layoff longer than a fortnight. This is the node that "
    "distinguishes a body you built from a body you keep, and it can only be earned by "
    "time.",
    "24 months with no injury layoff longer than two weeks.",
    "Training through a real injury to protect the streak. That ends the streak later "
    "and worse."),

18:("Thirty consecutive days of writing down what actually happened and what you "
    "actually thought. The value is not the writing, it is having a record that "
    "disagrees with your memory later.",
    "30 consecutive daily entries.",
    "Writing what you wish were true. A flattering journal is worse than none."),
19:("Ninety days with a written list of things removed. The list is the point — monk "
    "mode without a definition is just a mood.",
    "90 days, against a written list of what was removed, with the list kept.",
    "Defining it so loosely that nothing was actually given up."),
20:("No consumer debt. Nobody holds a claim on income you have not earned yet. It has "
    "no prerequisites because it is available to start immediately and it gates the "
    "entire savings branch.",
    "Zero consumer and credit debt outstanding.",
    "Rolling debt into a cheaper facility and calling it cleared."),
21:("Fifty thousand saved or invested, and left alone. Requires Zero Debt beneath it "
    "and the £10k months beside it, because saving while servicing debt is arithmetic "
    "working against you.",
    "£50,000 across savings and investments, untouched for six months.",
    "Counting money already earmarked for tax. HMRC's money was never yours."),
22:("Mind, money and body all holding at the same time — the only node in the tree that "
    "requires one branch from each of three tracks. Any one of them is achievable in "
    "isolation; the difficulty is simultaneity.",
    "Monk mode, £50k invested and peak physical shape all standing together.",
    "Letting two slide to force the third. This node measures the floor, not the peak."),
30:("Someone else reached a defined outcome using what you worked out. It is the "
    "cleanest available test of whether you understand your own process or merely "
    "execute it.",
    "One person hit a named outcome under your guidance.",
    "Giving advice and claiming the result. They have to actually get there."),

32:("A full licence plus advanced driving — IAM, RoSPA or equivalent. It sits at the "
    "very bottom of the board with no prerequisites, which is deliberate: it is the one "
    "part of the endgame you could start this month, and it gates the deposit.",
    "Full licence held, advanced driving qualification passed.",
    "Assuming the car teaches you. 765 horsepower is not where you learn."),
33:("A track day in something with real power — 500bhp or more — on a circuit, legally. "
    "It tells you whether you want the car or the idea of the car, and it is far "
    "cheaper to find that out here.",
    "One completed track day in a 500bhp+ car.",
    "A passenger ride. You need to be driving for this to answer anything."),

23:("The first thing bought outright, from profit, purely because you wanted it. A "
    "watch, a trip, a piece of equipment. Its purpose is calibration — proving you can "
    "buy something significant without it destabilising anything.",
    "Bought outright from profit, no finance, and no regret a month later.",
    "Financing it. The entire point is that it was paid for."),
24:("Half a million in assets minus liabilities, documented rather than estimated. The "
    "first genuine wealth checkpoint and the last one before the run-up begins.",
    "Assets minus liabilities at £500,000 or more, written down.",
    "Counting the business at a valuation nobody has offered."),
34:("Seven figures held. Requires both the £500k checkpoint and a £1M trading year, "
    "because net worth built on a single good year is fragile.",
    "Assets minus liabilities at £1,000,000 or more.",
    "Illiquid net worth. A million you cannot access does not buy anything."),
35:("The running costs, funded from profit, before the car exists. Insurance for a 765LT "
    "is not ordinary, servicing is scheduled and expensive, and the tyres are a "
    "consumable measured in thousands. Budget the year, then fund it.",
    "Twelve months of insurance, servicing, tyres and storage funded from profit.",
    "Budgeting the purchase and not the ownership. The purchase is the cheap part."),
36:("Somewhere secure, dry and insurable to keep it. Trivial next to the other nodes "
    "and absolutely non-optional — the insurance at this level asks where the car "
    "sleeps.",
    "Secure, dry, insurable storage arranged.",
    "On the street. Your insurer will have opinions, and so will everyone else."),
37:("The actual money, in actual cash, in a separate account, that is not working "
    "capital and not the tax reserve. Net worth is not a car; this node is the "
    "difference between being wealthy and being able to buy something.",
    "£300,000 liquid, ringfenced in a separate account, untouched for 90 days.",
    "Spending the business's operating cash. That is how the car costs you the "
    "company."),
38:("Configuration signed off and the deposit placed. The last reversible step — after "
    "this it is a build slot with your name on it.",
    "Spec signed, deposit paid, delivery slot confirmed.",
    "Speccing it before the money is ringfenced. The order in this tree is the order "
    "for a reason."),
25:("Keys. A 765LT is roughly £280,000 new, and every node beneath this one exists so "
    "that buying it changes nothing else — the business keeps running, the costs are "
    "already funded, and the cash was never operating capital.\n\n"
    "The tree is not really about the car. It is about the fact that this node is "
    "unreachable unless thirty-five other things are true first.",
    "Keys in your hand.",
    "Getting here by any route that skips a node. The prerequisites are the point."),
}


def parse_nodes(src: str) -> list[dict]:
    pattern = re.compile(
        r'\{id:(\d+),\s*t:"(\w+)",\s*n:"((?:[^"\\]|\\.)*)",\s*xp:(\d+),\s*'
        r'x:([\d.]+),\s*y:([\d.]+),\s*req:\[([^\]]*)\],\s*d:"((?:[^"\\]|\\.)*)"\s*\}'
    )
    nodes = []
    for m in pattern.finditer(src):
        raw = m.group(7).strip()
        nodes.append({
            "id": int(m.group(1)), "track": m.group(2), "name": m.group(3),
            "xp": int(m.group(4)), "y": float(m.group(6)),
            "req": [int(v) for v in raw.split(",") if v.strip()],
            "desc": m.group(8),
        })
    return sorted(nodes, key=lambda n: n["id"])


def slug(idx: int, name: str) -> str:
    text = f"{idx}. {name}".lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text.strip())


def main() -> int:
    src = open(SRC, encoding="utf-8").read()
    nodes = parse_nodes(src)
    if len(nodes) < 2:
        print("Could not parse the NODES array — has its shape changed?")
        return 1
    by_id = {n["id"]: n for n in nodes}
    missing = [n["id"] for n in nodes if n["id"] not in DETAIL]
    if missing:
        print(f"No DETAIL written for node(s): {missing}")
        return 1

    # ---- derived structure ----
    kids: dict[int, list[int]] = {n["id"]: [] for n in nodes}
    for n in nodes:
        for r in n["req"]:
            kids[r].append(n["id"])

    depth: dict[int, int] = {}
    def step(i: int) -> int:
        if i not in depth:
            depth[i] = 1 + max((step(r) for r in by_id[i]["req"]), default=0)
        return depth[i]
    for n in nodes:
        step(n["id"])

    def ancestors(i: int, seen=None) -> set:
        seen = seen if seen is not None else set()
        for r in by_id[i]["req"]:
            if r not in seen:
                seen.add(r)
                ancestors(r, seen)
        return seen

    def descendants(i: int, seen=None) -> set:
        seen = seen if seen is not None else set()
        for k in kids[i]:
            if k not in seen:
                seen.add(k)
                descendants(k, seen)
        return seen

    boss = max(nodes, key=lambda n: n["y"])["id"]
    # longest chain to the boss
    def longest(i: int) -> list[int]:
        if not by_id[i]["req"]:
            return [i]
        best = max((longest(r) for r in by_id[i]["req"]), key=len)
        return best + [i]
    critical = longest(boss)

    total_xp = sum(n["xp"] for n in nodes)
    roots = [n for n in nodes if not n["req"]]
    link = lambda i: f"[{by_id[i]['name']}](#{slug(i, by_id[i]['name'])})"

    o: list[str] = []
    w = o.append

    w("# 765LT Life Skill Tree — Complete Reference")
    w("")
    w(f"*Generated {date.today().isoformat()} by `scripts/make_docs.py` from the node "
      f"data in `index.html`. Do not hand-edit — regenerate it.*")
    w("")
    w(f"**{len(nodes)} nodes · {total_xp:,} XP · {len(critical)} steps along the longest "
      f"path to the car · {len(roots)} nodes open from a standing start.**")
    w("")

    # ---------- how it works ----------
    w("## How the tree works")
    w("")
    w("Three states, and one rule that produces all of them.")
    w("")
    w("| State | Meaning |")
    w("|---|---|")
    w("| **Locked** | At least one prerequisite is incomplete. Cannot be clicked. |")
    w("| **Available** | Every prerequisite is complete. Click to complete it. |")
    w("| **Complete** | Done. Click again to undo. |")
    w("")
    w("A node is available the moment **all** of its prerequisites are complete — "
      "prerequisites are ANDed, never ORed. There are no partial unlocks.")
    w("")
    w("**Un-completing cascades.** Clearing a node also clears everything standing on "
      "top of it, recursively. Without that the board could show a state its own rules "
      "forbid — the car owned with its run-up untouched.")
    w("")
    w("**Saved progress is pruned on load.** Anything completed whose prerequisites no "
      "longer hold is cleared, repeatedly, until the state is consistent. This is what "
      "keeps old saves honest when the tree itself changes.")
    w("")
    w("**XP is weight, not currency.** Nothing is bought with it. It exists so the "
      "progress bar reflects difficulty rather than node count — the car alone is "
      f"{by_id[boss]['xp']:,} XP, {by_id[boss]['xp']/total_xp*100:.0f}% of the board.")
    w("")

    # ---------- tracks ----------
    w("## The tracks")
    w("")
    w("| Track | Nodes | XP | Opens with | Ends at |")
    w("|---|---|---|---|---|")
    for key, (icon, label, _) in TRACKS.items():
        group = [n for n in nodes if n["track"] == key]
        if not group:
            continue
        entry = [n for n in group if not n["req"]] or [min(group, key=lambda n: depth[n["id"]])]
        end = max(group, key=lambda n: depth[n["id"]])
        w(f"| {icon} **{label}** | {len(group)} | {sum(n['xp'] for n in group):,} | "
          f"{', '.join(n['name'] for n in entry)} | {end['name']} |")
    w("")
    for key, (icon, label, blurb) in TRACKS.items():
        if any(n["track"] == key for n in nodes):
            w(f"- {icon} **{label}** — {blurb}")
    w("")

    # ---------- critical path ----------
    w("## The critical path")
    w("")
    w(f"The longest unavoidable chain — {len(critical)} steps. Every node here blocks "
      f"the one after it, so this is the shortest the tree can possibly be, no matter "
      f"what order you work in.")
    w("")
    for pos, i in enumerate(critical, 1):
        n = by_id[i]
        w(f"{pos}. **{n['name']}** — {n['xp']:,} XP {TRACKS[n['track']][0]}")
    w("")
    off = [n for n in nodes if n["id"] not in critical]
    w(f"The other {len(off)} nodes sit alongside it. "
      f"{len(ancestors(boss))} of the {len(nodes) - 1} non-car nodes are required for "
      f"the car, transitively — the tree has very little decoration.")
    w("")

    # ---------- map ----------
    w("## Map")
    w("")
    w("Bottom-to-top: arrows point from a prerequisite to what it unlocks.")
    w("")
    w("```mermaid")
    w("graph BT")
    for key, (_, label, _) in TRACKS.items():
        group = [n for n in nodes if n["track"] == key]
        if not group:
            continue
        w(f'  subgraph {key}["{label}"]')
        for n in group:
            w(f'    N{n["id"]}["{n["name"]}<br/>{n["xp"]:,} XP"]')
        w("  end")
    for n in nodes:
        for r in n["req"]:
            w(f"  N{r} --> N{n['id']}")
    w(f"  style N{boss} fill:#FF8000,stroke:#fff,color:#000")
    w("```")
    w("")

    # ---------- the nodes ----------
    w("## The nodes")
    w("")
    for key, (icon, label, blurb) in TRACKS.items():
        group = [n for n in nodes if n["track"] == key]
        if not group:
            continue
        w(f"### {icon} {label}")
        w("")
        w(f"*{blurb}*")
        w("")
        for n in sorted(group, key=lambda n: (depth[n["id"]], n["id"])):
            i = n["id"]
            entails, done_when, trap = DETAIL[i]
            blocks = descendants(i)
            w(f"#### {i}. {n['name']}")
            w("")
            w(f"`{n['xp']:,} XP` · earliest step {depth[i]} · "
              f"{TRACKS[n['track']][1]} track"
              + (f" · **blocks {len(blocks)} nodes**" if blocks else " · terminal node"))
            w("")
            w(f"> {n['desc']}")
            w("")
            w(entails)
            w("")
            w(f"**Done when:** {done_when}")
            w("")
            w(f"**Watch out:** {trap}")
            w("")
            if n["req"]:
                w(f"**Requires:** {' · '.join(link(r) for r in n['req'])}")
            else:
                w("**Requires:** nothing — open from the start.")
            w("")
            if kids[i]:
                w(f"**Unlocks:** {' · '.join(link(k) for k in kids[i])}")
            else:
                w("**Unlocks:** nothing — this is the end of its line.")
            w("")
    # ---------- reference tables ----------
    w("## Dependency reference")
    w("")
    w("| # | Node | Track | XP | Step | Requires | Unlocks | Blocks |")
    w("|---|---|---|---|---|---|---|---|")
    for n in nodes:
        i = n["id"]
        req = ", ".join(str(r) for r in n["req"]) or "—"
        unl = ", ".join(str(k) for k in kids[i]) or "—"
        w(f"| {i} | {n['name']} | {TRACKS[n['track']][0]} | {n['xp']:,} | {depth[i]} | "
          f"{req} | {unl} | {len(descendants(i))} |")
    w("")

    w("## Where to start")
    w("")
    w("Open from a standing start, with nothing beneath them:")
    w("")
    for n in sorted(roots, key=lambda n: -len(descendants(n["id"]))):
        w(f"- {TRACKS[n['track']][0]} **{n['name']}** — {n['xp']:,} XP, "
          f"unblocks {len(descendants(n['id']))} nodes")
    w("")
    w("Ranked by how much each one unblocks. The highest-leverage opening moves are "
      "the cheapest ones in the tree, which is the tree's whole argument.")
    w("")

    w("## XP by track")
    w("")
    w("| Track | XP | Share |")
    w("|---|---|---|")
    for key, (icon, label, _) in TRACKS.items():
        group = [n for n in nodes if n["track"] == key]
        if not group:
            continue
        sub = sum(n["xp"] for n in group)
        w(f"| {icon} {label} | {sub:,} | {sub/total_xp*100:.0f}% |")
    w(f"| **Total** | **{total_xp:,}** | **100%** |")
    w("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(o))
    print(f"Wrote {OUT} — {len(nodes)} nodes, {len(o)} lines, {total_xp:,} XP documented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
