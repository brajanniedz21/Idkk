#!/usr/bin/env python3
"""Build the initial PERSONAL_SKILL_TREE.json.

Every node starts at level 0 with zero XP and zero evidence. That is
deliberate: this file defines the *shape* of the tree — what exists, what
depends on what — not any claim about what has been achieved. Levels are
earned through `skilltree.py apply`, never seeded.

Re-running this OVERWRITES the tree and destroys progression history.
It is a one-time bootstrap, not part of the daily loop.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "PERSONAL_SKILL_TREE.json")

TREES = [
    ("entrepreneurship", "Entrepreneurship",
     "Building and running a business that people actually pay for."),
    ("growth_ops", "AI Growth Operating",
     "The specialisation: diagnosing a business's growth problem and fixing it with systems."),
    ("ai_automation", "AI & Automation",
     "Making machines do the work reliably, without supervision."),
    ("content_youtube", "Content & YouTube",
     "Making things people choose to watch, and understanding why they did."),
    ("filmmaking", "Filmmaking & Visual Creation",
     "Telling stories with images — camera, 3D, or generated."),
    ("art", "Art",
     "Hand skill. Levels here need finished work, not references saved."),
    ("fitness", "Fitness",
     "Knowing how training works versus actually training."),
    ("money", "Money & Financial Skills",
     "Earning, keeping, and deploying capital. Risk-taking is not progression."),
    ("technology", "Technology",
     "Writing, running, and hosting software that does something."),
    ("learning", "Learning",
     "The meta-tree. Levels here come from how well other trees grow."),
    ("personal_development", "Personal Development",
     "Behaviour only. Intentions score nothing in this tree."),
    ("life_independence", "Life & Independence",
     "The ability to run your own life without anyone underwriting it."),
    ("cross", "Cross-Tree Specialisations",
     "Powerful combinations. Each requires real levels in several trees at once."),
]

# (id, name, tier, prerequisites, unlock_requirement, hidden)
# Prerequisites are ANDed. A bare string means "that node at level 1+";
# a (node, level) pair demands a specific level.
NODES = [
    # ---------------- Entrepreneurship ----------------
    ("ent.fundamentals", "entrepreneurship", "Business Fundamentals", 1, [],
     "Explain how a business makes money end to end, in your own words.", False),
    ("ent.market_research", "entrepreneurship", "Market Research", 2, ["ent.fundamentals"],
     "Research a real niche and write down what its buyers actually want.", False),
    ("ent.offer", "entrepreneurship", "Offer Creation", 2, ["ent.fundamentals"],
     "Define one offer: who it is for, what it does, what it costs.", False),
    ("ent.positioning", "entrepreneurship", "Positioning", 3, ["ent.offer", "ent.market_research"],
     "State why someone should pick you over the obvious alternative.", False),
    ("ent.pricing", "entrepreneurship", "Pricing", 3, ["ent.offer"],
     "Set a price you can defend and hold it in a real conversation.", False),
    ("ent.copywriting", "entrepreneurship", "Copywriting", 3, ["ent.offer"],
     "Write copy that produced a measurable response from a real audience.", False),
    ("ent.acquisition", "entrepreneurship", "Client Acquisition", 3, ["ent.offer"],
     "Get a stranger into a real conversation about buying.", False),
    ("ent.sales", "entrepreneurship", "Sales", 4, ["ent.acquisition", "ent.positioning"],
     "Close a paid deal in a live conversation.", False),
    ("ent.delivery", "entrepreneurship", "Client Delivery", 4, ["ent.sales"],
     "Deliver what you sold, to a client's satisfaction.", False),
    ("ent.operations", "entrepreneurship", "Operations", 5, [("ent.delivery", 3)],
     "Run delivery repeatedly without it depending on your memory.", False),
    ("ent.scaling", "entrepreneurship", "Scaling", 6, [("ent.operations", 4), ("ent.pricing", 4)],
     "Increase throughput without proportionally increasing your hours.", True),

    # ---------------- AI Growth Operating ----------------
    ("gro.diagnosis", "growth_ops", "Growth Diagnosis", 3, [("ent.fundamentals", 2)],
     "Look at a real business and correctly identify its binding constraint.", False),
    ("gro.funnel", "growth_ops", "Funnel Analysis", 3, ["gro.diagnosis"],
     "Map a real funnel stage by stage with real numbers attached.", False),
    ("gro.conversion", "growth_ops", "Conversion Analysis", 4, ["gro.funnel"],
     "Find where a real funnel leaks and quantify the loss.", False),
    ("gro.crm", "growth_ops", "CRM Systems", 3, ["auto.fundamentals"],
     "Configure a CRM that a real pipeline actually runs through.", False),
    ("gro.leads", "growth_ops", "Lead Management", 4, ["gro.crm"],
     "Run a lead from capture to outcome without one falling through.", False),
    ("gro.experiments", "growth_ops", "Growth Experiments", 4, ["gro.funnel"],
     "Run a change with a measured before and after.", False),
    ("gro.revops", "growth_ops", "Revenue Operations", 5, [("gro.leads", 3), ("gro.conversion", 3)],
     "Own the systems between a lead and recognised revenue.", False),
    ("gro.strategy", "growth_ops", "Growth Strategy", 5, [("gro.experiments", 3), ("gro.diagnosis", 4)],
     "Choose what NOT to do, and be right about it in hindsight.", False),
    ("gro.architect", "growth_ops", "Growth Systems Architect", 6,
     [("gro.revops", 5), ("gro.strategy", 5)],
     "Design a growth system another operator could run without you.", True),

    # ---------------- AI & Automation ----------------
    ("ai.fundamentals", "ai_automation", "AI Fundamentals", 1, [],
     "Explain what a model can and cannot do, and why it fails when it fails.", False),
    ("ai.prompting", "ai_automation", "Prompt Engineering", 2, ["ai.fundamentals"],
     "Reliably get a useful output on a task where a naive prompt failed.", False),
    ("ai.context", "ai_automation", "Context Engineering", 3, [("ai.prompting", 3)],
     "Design what the model sees, not just what you ask it.", False),
    ("ai.claude_code", "ai_automation", "Claude & Claude Code", 2, ["ai.fundamentals"],
     "Use an agentic coding tool to ship a change you kept.", False),
    ("ai.agents", "ai_automation", "AI Agents", 4, [("ai.context", 3)],
     "Build an agent that completes a multi-step task unattended.", False),
    ("ai.cost", "ai_automation", "AI Cost Optimisation", 4, [("ai.agents", 2)],
     "Cut the cost of a running AI workload without losing output quality.", False),
    ("ai.local", "ai_automation", "Local AI", 4, [("ai.fundamentals", 3)],
     "Run a model locally and use it for real work.", False),
    ("ai.orchestration", "ai_automation", "Agent Orchestration", 5,
     [("ai.agents", 4), ("auto.architecture", 3)],
     "Coordinate several agents on one job, with handoffs that hold.", False),
    ("ai.prod_systems", "ai_automation", "Production AI Systems", 7,
     [("ai.orchestration", 5), ("auto.production", 4)],
     "Run an AI system other people depend on, and keep it up.", True),
    ("ai.unknown_1", "ai_automation", "???", 8, [("ai.prod_systems", 6)], "", True),

    ("auto.fundamentals", "ai_automation", "Automation Fundamentals", 1, [],
     "Describe a trigger, an action, and what happens when one fails.", False),
    ("auto.zapier", "ai_automation", "Zapier", 2, ["auto.fundamentals"],
     "Ship a Zap that runs on real data.", False),
    ("auto.n8n", "ai_automation", "n8n", 2, ["auto.fundamentals"],
     "Ship an n8n workflow that runs on real data.", False),
    ("auto.multistep", "ai_automation", "Multi-Step Automations", 3, [("auto.zapier", 2)],
     "Chain four or more steps with branching that behaves.", False),
    ("auto.apis", "ai_automation", "APIs", 3, ["auto.multistep"],
     "Call a third-party API with auth and handle its error responses.", False),
    ("auto.webhooks", "ai_automation", "Webhooks", 4, ["auto.apis"],
     "Receive a live webhook and act on its payload correctly.", False),
    ("auto.crm_integration", "ai_automation", "CRM Integrations", 4,
     [("auto.webhooks", 2), ("gro.crm", 2)],
     "Wire a CRM to another system so records stay in sync.", False),
    ("auto.cross_platform", "ai_automation", "Cross-Platform Systems", 5,
     [("auto.crm_integration", 3)],
     "Move data correctly across three or more systems you do not control.", False),
    ("auto.architecture", "ai_automation", "Automation Architecture", 5,
     [("auto.cross_platform", 3)],
     "Design an automation with failure handling, retries, and observability.", False),
    ("auto.production", "ai_automation", "Production Automation Systems", 6,
     [("auto.architecture", 5)],
     "Deploy and maintain a multi-step automation doing useful work reliably, "
     "for someone other than yourself.", True),

    # ---------------- Content & YouTube ----------------
    ("yt.fundamentals", "content_youtube", "YouTube Fundamentals", 1, [],
     "Explain what the platform rewards and why.", False),
    ("yt.ideas", "content_youtube", "Idea Generation", 2, ["yt.fundamentals"],
     "Generate ideas that survive contact with an audience.", False),
    ("yt.titles", "content_youtube", "Titles & Packaging", 2, ["yt.fundamentals"],
     "Write a title that outperformed your own previous one.", False),
    ("yt.thumbnails", "content_youtube", "Thumbnails", 2, ["yt.fundamentals"],
     "Produce a thumbnail with a measurably better click-through rate.", False),
    ("yt.formats", "content_youtube", "Shorts & Long-Form", 2, ["yt.fundamentals"],
     "Publish in both formats and know which serves which purpose.", False),
    ("yt.hooks", "content_youtube", "Hooks & Retention", 3, [("yt.titles", 2)],
     "Improve the retention curve of a real video.", False),
    ("yt.analytics", "content_youtube", "Analytics", 3, ["yt.fundamentals"],
     "Read your own data and draw a conclusion that turned out correct.", False),
    ("yt.competitor", "content_youtube", "Competitor Intelligence", 4, [("yt.analytics", 3)],
     "Explain another channel's performance and predict its next move.", False),
    ("yt.strategy", "content_youtube", "Content Strategy", 4,
     [("yt.analytics", 3), ("yt.ideas", 3)],
     "Run a deliberate content plan across a full month.", False),
    ("yt.pipeline", "content_youtube", "Automated Content Pipeline", 5,
     [("auto.multistep", 3), ("yt.strategy", 3)],
     "Automate production so publishing does not depend on your mood.", False),
    ("yt.growth_operator", "content_youtube", "YouTube Growth Operator", 6,
     [("yt.strategy", 5), ("yt.pipeline", 4), ("yt.competitor", 4)],
     "Grow a channel other than your own, on purpose.", True),

    # ---------------- Filmmaking ----------------
    ("film.storytelling", "filmmaking", "Visual Storytelling", 1, [],
     "Tell a story where the images carry the meaning.", False),
    ("film.composition", "filmmaking", "Composition", 2, ["film.storytelling"],
     "Frame a shot that reads instantly.", False),
    ("film.lighting", "filmmaking", "Lighting", 3, ["film.composition"],
     "Light a scene to a specific intended mood.", False),
    ("film.camera", "filmmaking", "Camera Movement", 3, ["film.composition"],
     "Move the camera for a reason a viewer could name.", False),
    ("film.cinematography", "filmmaking", "Cinematography", 4,
     [("film.lighting", 3), ("film.camera", 3)],
     "Shoot a sequence that holds together visually.", False),
    ("film.editing", "filmmaking", "Editing", 2, ["film.storytelling"],
     "Cut a sequence that plays better than its raw footage.", False),
    ("film.sound", "filmmaking", "Sound Design", 3, ["film.editing"],
     "Build a soundscape a viewer would miss if removed.", False),
    ("film.colour", "filmmaking", "Colour", 3, ["film.editing"],
     "Grade a sequence to a deliberate, consistent look.", False),
    ("film.3d", "filmmaking", "3D Filmmaking", 3, ["film.composition"],
     "Build and render a 3D shot you would show someone.", False),
    ("film.environment", "filmmaking", "Environment Design", 4, [("film.3d", 3)],
     "Build a 3D environment that reads as a real place.", False),
    ("film.animation", "filmmaking", "Animation", 4, [("film.3d", 3)],
     "Animate motion that reads as intentional, not default.", False),
    ("film.vfx", "filmmaking", "Visual Effects", 5, [("film.3d", 3), ("film.editing", 3)],
     "Composite an effect that survives a second viewing.", False),
    ("film.ai_video", "filmmaking", "AI Video", 3, ["ai.fundamentals", "film.storytelling"],
     "Direct generated video toward a shot you actually wanted.", False),
    ("film.short", "filmmaking", "Short Films", 5,
     [("film.cinematography", 3), ("film.editing", 4)],
     "Finish and release a short film.", False),
    ("film.3d_production", "filmmaking", "3D Cinematic Production", 6,
     [("film.3d", 5), ("film.environment", 4), ("film.animation", 4)],
     "Produce a finished cinematic piece entirely in 3D.", True),

    # ---------------- Art ----------------
    ("art.observation", "art", "Observation", 1, [],
     "Draw what is in front of you rather than what you assume is there.", False),
    ("art.proportion", "art", "Proportion", 2, ["art.observation"],
     "Get relationships right without measuring every time.", False),
    ("art.shading", "art", "Shading & Value", 3, ["art.observation"],
     "Render form convincingly with value alone.", False),
    ("art.perspective", "art", "Perspective", 3, [("art.proportion", 2)],
     "Construct a believable space from imagination.", False),
    ("art.media", "art", "Pen & Pencil Media", 3, ["art.shading"],
     "Control ballpoint and coloured pencil deliberately, not accidentally.", False),
    ("art.stippling", "art", "Stippling", 3, [("art.shading", 2)],
     "Complete a stippled piece with controlled tonal range.", False),
    ("art.digital", "art", "Digital Art", 3, ["art.shading"],
     "Finish a digital piece to the same standard as your traditional work.", False),
    ("art.composition", "art", "Composition (Art)", 4, [("art.perspective", 2)],
     "Arrange a picture so the eye goes where you intended.", False),
    ("art.character", "art", "Character Art", 4, [("art.proportion", 3), ("art.shading", 3)],
     "Draw a figure that reads as a specific person.", False),
    ("art.environment", "art", "Environmental Art", 4,
     [("art.perspective", 3), ("art.composition", 2)],
     "Draw a place with depth and atmosphere.", False),
    ("art.style", "art", "Artistic Style Development", 6,
     [("art.composition", 5), ("art.character", 4)],
     "Produce a recognisable body of work, not one good drawing.", True),

    # ---------------- Fitness ----------------
    ("fit.technique", "fitness", "Exercise Technique", 1, [],
     "Execute the main lifts with form that holds under load.", False),
    ("fit.knowledge", "fitness", "Training Knowledge", 1, [],
     "Explain why a programme is built the way it is.", False),
    ("fit.overload", "fitness", "Progressive Overload", 2, ["fit.knowledge", "fit.technique"],
     "Log progression over eight weeks and actually progress.", False),
    ("fit.hypertrophy", "fitness", "Hypertrophy Training", 3, [("fit.overload", 2)],
     "Run a hypertrophy block to completion and measure the result.", False),
    ("fit.strength", "fitness", "Strength Training", 3, [("fit.overload", 2)],
     "Add meaningful weight to a main lift over a training block.", False),
    ("fit.calisthenics", "fitness", "Calisthenics", 3, [("fit.technique", 2)],
     "Earn a bodyweight skill you could not previously do.", False),
    ("fit.consistency", "fitness", "Training Consistency", 3, ["fit.technique"],
     "Train to plan for twelve consecutive weeks.", False),
    ("fit.nutrition", "fitness", "Nutrition Knowledge", 1, [],
     "Explain energy balance and protein requirements accurately.", False),
    ("fit.macros", "fitness", "Macro Management", 2, ["fit.nutrition"],
     "Hit your macro targets across a full week — tracked, not estimated.", False),
    ("fit.meal_planning", "fitness", "Meal Planning", 3, [("fit.macros", 2)],
     "Feed yourself to plan for a month without it collapsing.", False),
    ("fit.recovery", "fitness", "Recovery & Sleep", 2, ["fit.knowledge"],
     "Hold a sleep and recovery routine that survives a busy week.", False),
    ("fit.programming", "fitness", "Independent Programme Design", 5,
     [("fit.hypertrophy", 4), ("fit.overload", 4)],
     "Write your own programme, run it, and get the predicted result.", False),
    ("fit.physique", "fitness", "Physique Development", 6,
     [("fit.programming", 4), ("fit.consistency", 5), ("fit.meal_planning", 4)],
     "A visible, sustained change over a year or more.", True),

    # ---------------- Money ----------------
    ("mon.literacy", "money", "Financial Literacy", 1, [],
     "Explain income, expenses, assets, and tax accurately.", False),
    ("mon.budgeting", "money", "Budgeting", 2, ["mon.literacy"],
     "Track and control your spending for three consecutive months.", False),
    ("mon.saving", "money", "Saving", 2, [("mon.budgeting", 2)],
     "Build a buffer you did not spend.", False),
    ("mon.income", "money", "Income Generation", 3, ["mon.literacy"],
     "Earn money from something you built or did.", False),
    ("mon.investing", "money", "Investing Knowledge", 3, [("mon.literacy", 2)],
     "Explain what you own, why, and what would make you sell.", False),
    ("mon.risk", "money", "Risk Management", 4, [("mon.investing", 2)],
     "Size a position so a bad outcome does not hurt you.", False),
    ("mon.business_income", "money", "Business Income", 4, [("mon.income", 3), ("ent.sales", 2)],
     "Money from customers, not from wages.", False),
    ("mon.trading_knowledge", "money", "Trading Knowledge", 3, [("mon.investing", 2)],
     "Understand mechanics, edge, and why most participants lose.", False),
    ("mon.trading_ability", "money", "Demonstrated Trading Ability", 6,
     [("mon.trading_knowledge", 5), ("mon.risk", 5)],
     "A documented, risk-adjusted record over a long period. Knowledge does not "
     "unlock this node, and gambling never will.", True),
    ("mon.entrepreneurial_finance", "money", "Entrepreneurial Finance", 5,
     [("mon.business_income", 3), ("mon.budgeting", 3)],
     "Run a business's numbers: margin, runway, reinvestment.", False),
    ("mon.independence", "money", "Financial Independence", 7,
     [("mon.entrepreneurial_finance", 5), ("mon.saving", 4)],
     "Your costs are covered by income you control.", True),

    # ---------------- Technology ----------------
    ("tech.computing", "technology", "General Computing", 1, [],
     "Operate a machine confidently, including the command line.", False),
    ("tech.git", "technology", "Git & GitHub", 2, ["tech.computing"],
     "Use branches, commits, and pull requests without fear.", False),
    ("tech.html", "technology", "HTML & CSS", 2, ["tech.computing"],
     "Build a page that looks right on a phone and a desktop.", False),
    ("tech.python", "technology", "Python", 2, ["tech.computing"],
     "Write a script that does a job you would otherwise do by hand.", False),
    ("tech.js", "technology", "JavaScript", 3, [("tech.html", 2)],
     "Make a page do something interactive that you wrote yourself.", False),
    ("tech.apis", "technology", "APIs in Code", 3, [("tech.python", 2)],
     "Consume an API in code with auth, paging, and error handling.", False),
    ("tech.databases", "technology", "Databases", 4, [("tech.python", 3)],
     "Model and query data that outlives a single script run.", False),
    ("tech.web", "technology", "Web Development", 4, [("tech.js", 3), ("tech.html", 3)],
     "Ship a working web app someone else has used.", False),
    ("tech.cloud", "technology", "Cloud & Hosting", 4, [("tech.web", 2)],
     "Deploy something and keep it running.", False),
    ("tech.rpi", "technology", "Raspberry Pi", 3, [("tech.computing", 2)],
     "Run a Pi doing a real job continuously.", False),
    ("tech.servers", "technology", "Local Servers & Networking", 4, [("tech.rpi", 2)],
     "Run a service on your own network, reachable and secured.", False),
    ("tech.dashboards", "technology", "Dashboard Development", 4, [("tech.web", 2)],
     "Build an interface that makes data legible at a glance.", False),
    ("tech.ai_integration", "technology", "AI Integration in Software", 5,
     [("tech.apis", 3), ("ai.agents", 2)],
     "Put a model inside an application and handle it failing.", False),
    ("tech.architecture", "technology", "System Architecture", 6,
     [("tech.web", 5), ("tech.databases", 4), ("tech.cloud", 4)],
     "Design a system whose parts you could justify to a sceptic.", True),

    # ---------------- Learning ----------------
    ("lrn.research", "learning", "Research", 1, [],
     "Find a trustworthy answer to a question nobody handed you.", False),
    ("lrn.critical", "learning", "Critical Thinking", 2, ["lrn.research"],
     "Change your mind because of evidence, on the record.", False),
    ("lrn.problem_solving", "learning", "Problem Solving", 2, ["lrn.research"],
     "Solve something that had no tutorial.", False),
    ("lrn.self_teaching", "learning", "Self-Teaching", 3, [("lrn.research", 2)],
     "Learn a skill to usable level without being taught.", False),
    ("lrn.synthesis", "learning", "Information Synthesis", 3, [("lrn.critical", 2)],
     "Combine several sources into a conclusion none of them stated.", False),
    ("lrn.experimentation", "learning", "Experimentation", 3, [("lrn.problem_solving", 2)],
     "Test something properly instead of guessing.", False),
    ("lrn.knowledge_mgmt", "learning", "Knowledge Management", 3, [("lrn.synthesis", 2)],
     "Keep notes you actually return to and use.", False),
    ("lrn.project_based", "learning", "Project-Based Learning", 4,
     [("lrn.self_teaching", 3), ("lrn.experimentation", 2)],
     "Finish a project whose purpose was learning, and finish it.", False),
    ("lrn.rapid", "learning", "Rapid Skill Acquisition", 5,
     [("lrn.project_based", 4), ("lrn.self_teaching", 5)],
     "Go from zero to useful in a new domain, repeatedly.", False),
    ("lrn.systems_thinking", "learning", "Systems Thinking", 5,
     [("lrn.synthesis", 4), ("lrn.experimentation", 4)],
     "See the feedback loop before it bites you.", False),
    ("lrn.cross_domain", "learning", "Cross-Domain Problem Solving", 6,
     [("lrn.systems_thinking", 4), ("lrn.rapid", 4)],
     "Solve a problem in one field using a tool from another.", True),

    # ---------------- Personal Development ----------------
    ("pd.reflection", "personal_development", "Reflection", 1, [],
     "Review your own week honestly, in writing.", False),
    ("pd.journaling", "personal_development", "Journaling", 2, ["pd.reflection"],
     "Keep it going for a month without a gap.", False),
    ("pd.planning", "personal_development", "Planning", 2, ["pd.reflection"],
     "Make a plan you then followed.", False),
    ("pd.decisions", "personal_development", "Decision Making", 3, [("pd.reflection", 2)],
     "Make a hard call, record your reasoning, and check it later.", False),
    ("pd.focus", "personal_development", "Focus & Attention Management", 3, [("pd.planning", 2)],
     "Hold deep work sessions consistently across a month.", False),
    ("pd.consistency", "personal_development", "Consistency", 3, [("pd.planning", 2)],
     "Do the same important thing weekly for three months.", False),
    ("pd.confidence", "personal_development", "Confidence", 3, [],
     "Act despite discomfort, repeatedly, in situations that matter.", False),
    ("pd.self_awareness", "personal_development", "Self-Awareness", 3,
     [("pd.reflection", 2), ("pd.journaling", 2)],
     "Predict your own failure modes before they happen.", False),
    ("pd.discipline", "personal_development", "Discipline", 4, [("pd.consistency", 3)],
     "Keep the standard when nobody is checking and nothing is fun.", False),
    ("pd.delayed_gratification", "personal_development", "Delayed Gratification", 4,
     [("pd.discipline", 2)],
     "Choose the slower, larger payoff — and be seen to do it more than once.", False),
    ("pd.independence", "personal_development", "Personal Independence", 5,
     [("pd.discipline", 4), ("pd.decisions", 4)],
     "Run your own direction without external pressure holding it up.", True),

    # ---------------- Life & Independence ----------------
    ("life.cooking", "life_independence", "Cooking", 1, [],
     "Feed yourself well, routinely, without buying it ready-made.", False),
    ("life.organisation", "life_independence", "Organisation", 1, [],
     "Nothing important is lost, late, or forgotten.", False),
    ("life.communication", "life_independence", "Communication", 2, [],
     "Handle a difficult conversation with an adult stranger.", False),
    ("life.scheduling", "life_independence", "Scheduling", 2, ["life.organisation"],
     "Run your week from a calendar you trust.", False),
    ("life.money_mgmt", "life_independence", "Personal Money Management", 2,
     [("mon.budgeting", 2)],
     "Cover your own costs and know your numbers.", False),
    ("life.admin", "life_independence", "Personal Administration", 3,
     [("life.organisation", 2)],
     "Handle official paperwork yourself, correctly and on time.", False),
    ("life.employment", "life_independence", "Employment", 3, [("life.communication", 2)],
     "Get and hold a role, or deliberately choose not to need one.", False),
    ("life.travel", "life_independence", "Travel", 3, [("life.organisation", 2)],
     "Plan and complete a trip end to end, alone.", False),
    ("life.business_admin", "life_independence", "Business Administration", 4,
     [("life.admin", 2), ("ent.operations", 2)],
     "Register, invoice, record, and file — properly.", False),
    ("life.contracts", "life_independence", "Contracts & Legal Basics", 4,
     [("life.business_admin", 2)],
     "Read an agreement and know what you just accepted.", False),
    ("life.housing", "life_independence", "Housing", 5,
     [("life.money_mgmt", 4), ("life.employment", 3)],
     "Secure and sustain your own place to live.", True),
    ("life.independent_living", "life_independence", "Independent Living", 6,
     [("life.housing", 3), ("life.cooking", 4), ("life.admin", 4)],
     "The whole machine runs without anyone underwriting it.", True),

    # ---------------- Cross-tree ----------------
    ("cross.ai_growth_operator", "cross", "AI Growth Operator", 7,
     [("gro.strategy", 5), ("auto.architecture", 5), ("gro.crm", 4),
      ("ent.copywriting", 4), ("yt.analytics", 4), ("ent.fundamentals", 4)],
     "Diagnose a real business's growth problem and build the system that fixes it.", True),
    ("cross.independent_filmmaker", "cross", "Independent AI Filmmaker", 7,
     [("film.cinematography", 5), ("film.editing", 5), ("film.3d", 5),
      ("film.ai_video", 5), ("film.storytelling", 5)],
     "Make a film alone that an audience chooses to finish.", True),
    ("cross.agentic_business", "cross", "Agentic Business Infrastructure", 8,
     [("ai.prod_systems", 6), ("auto.production", 5), ("gro.revops", 4)],
     "A business whose operations largely run themselves.", True),
    ("cross.unknown_1", "cross", "???", 9, [("cross.agentic_business", 5)], "", True),
    ("cross.unknown_2", "cross", "???", 9, [("cross.ai_growth_operator", 6)], "", True),
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
    ("ms.first_short_film", "First Published Short Film", "Finished, released, watchable by strangers."),
    ("ms.first_3d_film", "First Successful 3D Film", "A complete 3D piece you would show without caveats."),
    ("ms.first_1k_subs", "First 1,000 Subscribers", "On a channel you own."),
    ("ms.first_100k_video", "First 100k-View Video", "One video, 100,000 views."),
    ("ms.first_profitable", "First Profitable Business", "Revenue exceeded costs across a full quarter."),
    ("ms.first_10k_month", "First £10k Month", "£10,000 revenue inside a single calendar month."),
    ("ms.training_year", "First Year of Consistent Training",
     "52 weeks with training maintained through the bad ones."),
]

QUESTS = [
    {
        "name": "Calibration: the honest inventory",
        "description": "Run the calibration intake. Tell Claude, per tree, what you have "
                       "actually built, shipped, or done — not what you have read about. "
                       "This is the only time the tree accepts retrospective evidence in bulk, "
                       "and it decides how accurate everything after it is.",
        "reward": "Seeds the tree with real levels instead of zeros",
        "unlocks": "Every other quest becomes meaningful",
        "difficulty": 2,
        "proof": "A completed intake covering all 12 trees, including the empty ones.",
    },
    {
        "name": "Ship one automation end to end",
        "description": "Pick one real, annoying, repeated task in your own life or work. "
                       "Build it in n8n or Zapier. Let it run on live data for a week.",
        "reward": "+80–150 Automation XP, evidence class 3",
        "unlocks": "APIs → Webhooks chain",
        "difficulty": 3,
        "proof": "It ran unattended on real data and you can show what it did.",
    },
    {
        "name": "Finish one thing in the creative tree",
        "description": "One finished piece — a drawing, a 3D shot, a short edit. Finished, "
                       "not started. The art and film trees are the easiest to accumulate "
                       "knowledge in and the hardest to accumulate evidence in.",
        "reward": "+20–50 XP with experience-class evidence",
        "unlocks": "Raises the level cap on that branch from 2 to 6",
        "difficulty": 2,
        "proof": "A completed piece, dated.",
    },
    {
        "name": "Put one number on one funnel",
        "description": "Take any real funnel — yours or a business you can see — and attach "
                       "actual numbers to each stage. Growth Diagnosis is the gateway node "
                       "for the entire AI Growth Operating tree and it does not open on theory.",
        "reward": "+50 Growth XP, opens Funnel Analysis",
        "unlocks": "Growth Diagnosis → Funnel Analysis → Conversion Analysis",
        "difficulty": 3,
        "proof": "A stage-by-stage breakdown with real figures and a named constraint.",
    },
    {
        "name": "Four weeks of logged training",
        "description": "Four consecutive weeks, logged. Not a programme design, not research "
                       "into optimal splits — the log itself.",
        "reward": "+40–80 Fitness XP toward Consistency",
        "unlocks": "Progressive Overload",
        "difficulty": 3,
        "proof": "A training log with four unbroken weeks.",
    },
]


def build() -> dict:
    now = dt.date.today().isoformat()
    nodes = []
    for nid, tree, name, tier, prereqs, requirement, hidden in NODES:
        nodes.append({
            "id": nid,
            "tree": tree,
            "name": name,
            "tier": tier,
            "xp": 0,
            "level": 0,
            "status": "Locked",
            "hidden": hidden,
            "prerequisites": [
                {"node": p[0], "level": p[1]} if isinstance(p, tuple) else p
                for p in prereqs
            ],
            "next_unlock": [],
            "unlock_requirement": requirement,
            "evidence": [],
            "xp_by_type": {},
            "confidence": "none",
            "last_progressed": None,
            "created": now,
        })

    # next_unlock is the inverse of prerequisites — derive it rather than
    # maintaining two copies that can disagree.
    by_id = {n["id"]: n for n in nodes}
    for node in nodes:
        for req in node["prerequisites"]:
            target = req["node"] if isinstance(req, dict) else req
            if target in by_id:
                by_id[target]["next_unlock"].append(node["id"])

    return {
        "schema_version": 1,
        "player": {
            "name": "Brajan",
            "created": now,
            "last_update": None,
            "player_level": 0,
            "total_xp": 0,
        },
        "build": {
            "primary_class": None,
            "secondary_class": None,
            "creative_class": None,
            "confidence": "none",
            "note": "Left empty on purpose. A build is read off sustained behaviour "
                    "over months; naming one early makes the tree describe an "
                    "aspiration rather than a person.",
        },
        "attributes": {},
        "trees": [
            {"id": tid, "name": name, "description": desc, "status": "active"}
            for tid, name, desc in TREES
        ],
        "nodes": nodes,
        "milestones": [
            {"id": mid, "name": name, "requirement": req, "unlocked": False, "date": None}
            for mid, name, req in MILESTONES
        ],
        "quests": QUESTS,
        "interest_signals": [],
        "history": [],
    }


if __name__ == "__main__":
    if os.path.exists(OUT) and "--force" not in sys.argv:
        print(f"{OUT} already exists. Re-seeding destroys all progression history.\n"
              f"Pass --force if that is genuinely what you want.")
        sys.exit(1)
    tree = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(tree, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"Seeded {OUT} with {len(tree['nodes'])} nodes across {len(tree['trees'])} trees, "
          f"{len(tree['milestones'])} milestones, all at level 0.")
