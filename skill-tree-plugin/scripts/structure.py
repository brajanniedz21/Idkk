#!/usr/bin/env python3
"""The shape of the tree: trees, nodes, prerequisites, milestones, quests.

Kept separate from both the seeder and the engine so the structure has exactly
one definition. Nothing here carries progress — levels and XP are earned through
`skilltree.py apply`, never declared.

Deliberately coarse. An earlier version split skills to 155 nodes, down to
"Stippling" and "Recovery & Sleep" as separate branches, which is finer than
anyone can honestly assess about themselves. Broad skills you can actually
judge beat precise ones you cannot.
"""

TREES = [
    ("business", "Business & Growth",
     "Finding the problem a business will pay to have fixed, and fixing it."),
    ("ai_automation", "AI & Automation",
     "Making machines do the work reliably, without supervision."),
    ("content", "Content & Audience",
     "Making things people choose to watch, and understanding why they did."),
    ("creative", "Visual & Creative",
     "Drawing, design, 3D and film — the eye, and the hand that executes it."),
    ("technology", "Technology",
     "Writing, running and hosting software that does something."),
    ("fitness", "Fitness",
     "Knowing how training works versus actually training."),
    ("money", "Money",
     "Earning, keeping and deploying capital. Risk-taking is not progression."),
    ("learning", "Learning & Thinking",
     "The meta-tree. Levels here come from how well the other trees grow."),
    ("life", "Discipline & Independence",
     "Behaviour only. Intentions score nothing in this tree."),
    ("cross", "Cross-Tree Specialisations",
     "Powerful combinations, each needing real levels in several trees at once."),
]

# (id, tree, name, tier, prerequisites, unlock_requirement, hidden)
# Prerequisites are ANDed. A bare string means "that node at level 1+";
# a (node, level) pair demands a specific level.
NODES = [
    # ---------------- Business & Growth ----------------
    ("biz.fundamentals", "business", "Business Fundamentals", 1, [],
     "Explain how a business makes money end to end, in your own words.", False),
    ("biz.offer", "business", "Offer, Pricing & Positioning", 2, ["biz.fundamentals"],
     "Define one offer: who it is for, what it does, what it costs, and why you "
     "over the obvious alternative.", False),
    ("biz.copywriting", "business", "Copywriting", 3, ["biz.offer"],
     "Write copy that produced a measurable response from a real audience.", False),
    ("biz.outreach", "business", "Outreach & Client Acquisition", 3, ["biz.offer"],
     "Get a stranger into a real conversation about buying.", False),
    ("biz.growth", "business", "Growth Diagnosis & Strategy", 4,
     [("biz.fundamentals", 2)],
     "Look at a real business, find its binding constraint, change something, and "
     "measure whether you were right.", False),
    ("biz.crm", "business", "CRM & Lead Systems", 3, ["auto.fundamentals"],
     "Run a real pipeline through a system, with no lead falling through it.", False),
    ("biz.sales", "business", "Sales", 4, [("biz.outreach", 2)],
     "Close a paid deal in a live conversation.", False),
    ("biz.delivery", "business", "Delivery & Operations", 5, [("biz.sales", 2)],
     "Deliver what you sold, repeatedly, without it depending on your memory.", False),
    ("biz.scaling", "business", "Scaling", 6, [("biz.delivery", 4), ("biz.growth", 4)],
     "Increase throughput without proportionally increasing your hours.", True),

    # ---------------- AI & Automation ----------------
    ("ai.fundamentals", "ai_automation", "AI Fundamentals", 1, [],
     "Explain what a model can and cannot do, and why it fails when it fails.", False),
    ("ai.prompting", "ai_automation", "Prompting, Context & AI Tooling", 2,
     ["ai.fundamentals"],
     "Reliably get useful work out of a model on a task where the naive attempt "
     "failed — and keep the result.", False),
    ("ai.agents", "ai_automation", "AI Agents & Orchestration", 4,
     [("ai.prompting", 3)],
     "Build an agent that completes a multi-step task unattended.", False),
    ("auto.fundamentals", "ai_automation", "Automation Fundamentals", 1, [],
     "Describe a trigger, an action, and what happens when one fails.", False),
    ("auto.tools", "ai_automation", "Automation Tools (Zapier, n8n)", 2,
     ["auto.fundamentals"],
     "Ship a workflow that runs unattended on real data.", False),
    ("auto.integration", "ai_automation", "Multi-Step Automations & APIs", 3,
     [("auto.tools", 2)],
     "Chain several steps across systems you do not control, with auth, branching "
     "and error handling that behave.", False),
    ("auto.systems", "ai_automation", "Automation Architecture", 5,
     [("auto.integration", 3)],
     "Design an automation with failure handling, retries and observability.", False),
    ("auto.production", "ai_automation", "Production Automation Systems", 6,
     [("auto.systems", 5)],
     "Deploy and maintain a multi-step automation doing useful work reliably, for "
     "someone other than yourself.", True),
    ("ai.production", "ai_automation", "Production AI Systems", 7,
     [("ai.agents", 5), ("auto.production", 4)],
     "Run an AI system other people depend on, and keep it up.", True),

    # ---------------- Content & Audience ----------------
    ("yt.fundamentals", "content", "Audience Fundamentals", 1, [],
     "Explain what the platform rewards and why.", False),
    ("yt.ideas", "content", "Idea Generation", 2, ["yt.fundamentals"],
     "Generate ideas that survive contact with an audience.", False),
    ("yt.packaging", "content", "Packaging: Titles, Thumbnails, Hooks", 2,
     ["yt.fundamentals"],
     "Beat your own previous click-through or retention on a real video.", False),
    ("yt.analytics", "content", "Analytics & Competitor Intelligence", 3,
     ["yt.fundamentals"],
     "Read the data, draw a conclusion, and have it turn out correct.", False),
    ("yt.strategy", "content", "Content Strategy", 4,
     [("yt.analytics", 3), ("yt.ideas", 3)],
     "Run a deliberate content plan across a full month.", False),
    ("yt.systems", "content", "Content Systems & Scale", 5,
     [("yt.strategy", 4), ("auto.integration", 3)],
     "Automate production so publishing does not depend on your mood.", True),

    # ---------------- Visual & Creative ----------------
    ("vis.drawing", "creative", "Drawing & Rendering", 1, [],
     "Draw what is in front of you, and render form convincingly with value.", False),
    ("vis.story", "creative", "Visual Storytelling", 1, [],
     "Tell a story where the images carry the meaning.", False),
    ("vis.composition", "creative", "Composition & Perspective", 3,
     [("vis.drawing", 2)],
     "Arrange a picture so the eye goes where you intended, in a space that "
     "holds together.", False),
    ("vis.edit", "creative", "Editing & Post", 2, ["vis.story"],
     "Cut a sequence that plays better than its raw footage.", False),
    ("vis.brand", "creative", "Brand & Visual Identity", 3, ["vis.composition"],
     "Produce a coherent identity — palette, type, marks — applied consistently "
     "across several real assets.", False),
    ("vis.3d", "creative", "3D & VFX", 3, ["vis.composition"],
     "Build and render a 3D shot you would show someone.", False),
    ("vis.ai_video", "creative", "AI Video", 3, ["ai.fundamentals", "vis.story"],
     "Direct generated video toward a shot you actually wanted.", False),
    ("vis.camera", "creative", "Cinematography", 4,
     [("vis.composition", 2), ("vis.story", 2)],
     "Light and move a camera for reasons a viewer could name.", False),
    ("vis.masterwork", "creative", "Finished Body of Work", 6,
     [("vis.composition", 5), ("vis.drawing", 5)],
     "A recognisable body of finished work, not one good piece.", True),

    # ---------------- Technology ----------------
    ("tech.computing", "technology", "Computing & Version Control", 1, [],
     "Operate a machine confidently, command line and git included.", False),
    ("tech.frontend", "technology", "Frontend (HTML, CSS, JavaScript)", 2,
     ["tech.computing"],
     "Build a page that works on a phone and does something you wrote.", False),
    ("tech.code", "technology", "Code & Data (Python, APIs, Databases)", 3,
     ["tech.computing"],
     "Write a program that does a real job, talks to an API, and stores what "
     "it needs to keep.", False),
    ("tech.web", "technology", "Web Apps & Dashboards", 4, [("tech.frontend", 3)],
     "Ship a working application someone else has used.", False),
    ("tech.hosting", "technology", "Hosting & Servers", 4, [("tech.web", 2)],
     "Deploy something and keep it running.", False),
    ("tech.ai_integration", "technology", "AI Integration in Software", 5,
     [("tech.code", 3), ("ai.agents", 2)],
     "Put a model inside an application and handle it failing.", False),
    ("tech.architecture", "technology", "System Architecture", 6,
     [("tech.web", 5), ("tech.code", 4), ("tech.hosting", 4)],
     "Design a system whose parts you could justify to a sceptic.", True),

    # ---------------- Fitness ----------------
    ("fit.training", "fitness", "Training Knowledge & Technique", 1, [],
     "Execute the main lifts with form that holds, and explain why the "
     "programme is built the way it is.", False),
    ("fit.nutrition", "fitness", "Nutrition & Diet", 2, [],
     "Feed yourself to a target across a full month — tracked, not estimated.", False),
    ("fit.recovery", "fitness", "Recovery & Sleep", 2, ["fit.training"],
     "Hold a sleep and recovery routine that survives a busy week.", False),
    ("fit.consistency", "fitness", "Training Consistency", 3, ["fit.training"],
     "Train to plan for twelve consecutive weeks, bad weeks included.", False),
    ("fit.progression", "fitness", "Progressive Training", 3, [("fit.training", 2)],
     "Log progression over a training block and actually progress.", False),
    ("fit.programming", "fitness", "Independent Programming & Physique", 5,
     [("fit.progression", 4), ("fit.consistency", 4)],
     "Write your own programme, run it, and get the result you predicted.", True),

    # ---------------- Money ----------------
    ("mon.literacy", "money", "Financial Literacy", 1, [],
     "Explain income, expenses, assets and tax accurately.", False),
    ("mon.personal", "money", "Personal Money Management", 2, ["mon.literacy"],
     "Cover your own costs, know your numbers, and keep a buffer you did "
     "not spend.", False),
    ("mon.income", "money", "Earning & Business Income", 3, ["mon.literacy"],
     "Money from customers, not from wages.", False),
    ("mon.investing", "money", "Investing & Risk", 3, [("mon.literacy", 2)],
     "Explain what you own, why, and what would make you sell. Knowledge of "
     "markets and a proven record are different skills, and reading alone caps "
     "this node at level 2.", False),
    ("mon.business_finance", "money", "Business Finance", 5,
     [("mon.income", 3), ("mon.personal", 3)],
     "Run a business's numbers: margin, runway, reinvestment.", False),
    ("mon.independence", "money", "Financial Independence", 7,
     [("mon.business_finance", 5), ("mon.personal", 4)],
     "Your costs are covered by income you control.", True),

    # ---------------- Learning & Thinking ----------------
    ("lrn.research", "learning", "Research", 1, [],
     "Find a trustworthy answer to a question nobody handed you.", False),
    ("lrn.thinking", "learning", "Critical Thinking & Problem Solving", 2,
     ["lrn.research"],
     "Solve something that had no tutorial, and change your mind on the record "
     "when the evidence says so.", False),
    ("lrn.self_teaching", "learning", "Self-Teaching", 3, [("lrn.research", 2)],
     "Learn a skill to usable level without being taught, by finishing something "
     "in it.", False),
    ("lrn.synthesis", "learning", "Synthesis & Knowledge Management", 3,
     [("lrn.thinking", 2)],
     "Combine sources into a conclusion none of them stated, and keep notes you "
     "actually return to.", False),
    ("lrn.experimentation", "learning", "Experimentation", 3, [("lrn.thinking", 2)],
     "Test something properly instead of guessing.", False),
    ("lrn.systems", "learning", "Systems Thinking & Rapid Acquisition", 5,
     [("lrn.synthesis", 4), ("lrn.experimentation", 4), ("lrn.self_teaching", 5)],
     "See the feedback loop before it bites, and go zero to useful in a new "
     "domain repeatedly.", True),

    # ---------------- Discipline & Independence ----------------
    ("pd.reflection", "life", "Reflection & Self-Awareness", 1, [],
     "Review your own week honestly in writing, and predict your own failure "
     "modes before they happen.", False),
    ("pd.planning", "life", "Planning & Focus", 2, ["pd.reflection"],
     "Make a plan you then followed, and hold deep work across a month.", False),
    ("pd.consistency", "life", "Discipline & Consistency", 3, [("pd.planning", 2)],
     "Do the same important thing weekly for three months, when nobody is "
     "checking and none of it is fun.", False),
    ("life.communication", "life", "Communication", 2, [],
     "Handle a difficult conversation with an adult stranger.", False),
    ("life.organisation", "life", "Organisation & Admin", 2, [],
     "Nothing important is lost, late or forgotten, paperwork included.", False),
    ("life.selfcare", "life", "Cooking & Self-Care", 1, [],
     "Feed yourself well, routinely, without buying it ready-made.", False),
    ("life.work", "life", "Work & Business Admin", 4,
     [("life.communication", 2), ("life.organisation", 2)],
     "Register, invoice, record and file — properly — and read an agreement "
     "knowing what you just accepted.", False),
    ("life.independent", "life", "Independent Living", 6,
     [("life.work", 3), ("life.organisation", 4), ("pd.consistency", 4),
      ("mon.personal", 4)],
     "The whole machine runs without anyone underwriting it.", True),

    # ---------------- Cross-tree ----------------
    ("cross.ai_growth_operator", "cross", "AI Growth Operator", 7,
     [("biz.growth", 5), ("auto.systems", 5), ("biz.crm", 4),
      ("biz.copywriting", 4), ("yt.analytics", 4)],
     "Diagnose a real business's growth problem and build the system that "
     "fixes it.", True),
    ("cross.filmmaker", "cross", "Independent AI Filmmaker", 7,
     [("vis.camera", 5), ("vis.edit", 5), ("vis.3d", 5), ("vis.ai_video", 5),
      ("vis.story", 5)],
     "Make a film alone that an audience chooses to finish.", True),
    ("cross.agentic_business", "cross", "Agentic Business Infrastructure", 8,
     [("ai.production", 6), ("auto.production", 5), ("biz.growth", 4)],
     "A business whose operations largely run themselves.", True),
    ("cross.unknown", "cross", "???", 9, [("cross.agentic_business", 5)], "", True),
]

MILESTONES = [
    ("ms.first_client", "First Real Client", "Someone outside your circle paid you for work."),
    ("ms.first_1k", "First £1,000 Earned", "£1,000 cumulative, earned from your own work."),
    ("ms.first_paid_automation", "First Paid Automation Build",
     "Someone paid you to build an automation and it ran in their business."),
    ("ms.first_system_deployed", "First Business System Deployed",
     "A system you built is depended on by a business, yours or a client's."),
    ("ms.first_autonomous", "First Fully Autonomous Automation",
     "Runs for 30 days doing useful work without you touching it."),
    ("ms.first_short_film", "First Published Short Film",
     "Finished, released, watchable by strangers."),
    ("ms.first_3d_film", "First Successful 3D Film",
     "A complete 3D piece you would show without caveats."),
    ("ms.first_1k_subs", "First 1,000 Subscribers", "On a channel you own."),
    ("ms.first_100k_video", "First 100k-View Video", "One video, 100,000 views."),
    ("ms.first_profitable", "First Profitable Business",
     "Revenue exceeded costs across a full quarter."),
    ("ms.first_10k_month", "First £10k Month",
     "£10,000 revenue inside a single calendar month."),
    ("ms.training_year", "First Year of Consistent Training",
     "52 weeks with training maintained through the bad ones."),
]

# Short forms for the rim of the graph; full names live in the node panel.
SHORT = {
    "business": "Business", "ai_automation": "AI & Automation", "content": "Content",
    "creative": "Creative", "technology": "Technology", "fitness": "Fitness",
    "money": "Money", "learning": "Learning", "life": "Discipline", "cross": "Cross-Tree",
}


def build_nodes(created: str) -> list[dict]:
    """Structure only: every node starts at zero."""
    nodes = []
    for nid, tree, name, tier, prereqs, requirement, hidden in NODES:
        nodes.append({
            "id": nid, "tree": tree, "name": name, "tier": tier,
            "xp": 0, "level": 0, "status": "Locked", "hidden": hidden,
            "prerequisites": [
                {"node": p[0], "level": p[1]} if isinstance(p, tuple) else p
                for p in prereqs
            ],
            "next_unlock": [], "unlock_requirement": requirement,
            "evidence": [], "xp_by_type": {}, "confidence": "none",
            "last_progressed": None, "created": created,
        })
    by_id = {n["id"]: n for n in nodes}
    # next_unlock is the inverse of prerequisites — derived, never maintained twice.
    for node in nodes:
        for req in node["prerequisites"]:
            target = req["node"] if isinstance(req, dict) else req
            if target in by_id:
                by_id[target]["next_unlock"].append(node["id"])
    return nodes
