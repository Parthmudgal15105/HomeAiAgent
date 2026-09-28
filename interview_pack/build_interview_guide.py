from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


OUT = "/Users/parthmudgal/Code/HomeAiAgent/AI_Home_Lab_Operator_Interview_Guide.docx"
NAVY = "17324D"
BLUE = "2C648F"
PALE_BLUE = "EAF2F8"
PALE_GRAY = "F4F6F7"
MID_GRAY = "D9E0E5"
DARK = RGBColor(0, 0, 0)
MUTED = RGBColor(76, 86, 96)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color=MID_GRAY, size="6"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:color"), color)


def set_cell_margins(cell, top=110, start=120, bottom=110, end=120):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def keep_with_next(paragraph):
    paragraph.paragraph_format.keep_with_next = True


def no_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    tr_pr.append(cant_split)


doc = Document()
section = doc.sections[0]
section.page_width = Inches(8.5)
section.page_height = Inches(11)
section.top_margin = Inches(0.68)
section.bottom_margin = Inches(0.68)
section.left_margin = Inches(0.78)
section.right_margin = Inches(0.78)

styles = doc.styles
normal = styles["Normal"]
normal.font.name = "Aptos"
normal._element.rPr.rFonts.set(qn("w:ascii"), "Aptos")
normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos")
normal.font.size = Pt(10.5)
normal.font.color.rgb = DARK
normal.paragraph_format.space_after = Pt(5)
normal.paragraph_format.line_spacing = 1.08

for style_name, size, before, after in (
    ("Title", 30, 0, 14),
    ("Subtitle", 13, 0, 8),
    ("Heading 1", 20, 18, 8),
    ("Heading 2", 14, 13, 5),
    ("Heading 3", 11.5, 9, 3),
):
    st = styles[style_name]
    st.font.name = "Aptos Display" if style_name in ("Title", "Heading 1", "Heading 2") else "Aptos"
    st._element.rPr.rFonts.set(qn("w:ascii"), st.font.name)
    st._element.rPr.rFonts.set(qn("w:hAnsi"), st.font.name)
    st.font.size = Pt(size)
    st.font.color.rgb = DARK
    st.font.bold = style_name != "Subtitle"
    st.paragraph_format.space_before = Pt(before)
    st.paragraph_format.space_after = Pt(after)
    st.paragraph_format.keep_with_next = True

styles["Title"].paragraph_format.space_before = Pt(70)
styles["Subtitle"].font.color.rgb = MUTED

for name, indent, size in (("Bullet Clean", 0.24, 10.3), ("Bullet Compact", 0.22, 9.8)):
    st = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    st.base_style = styles["Normal"]
    st.font.name = "Aptos"
    st.font.size = Pt(size)
    st.paragraph_format.left_indent = Inches(indent)
    st.paragraph_format.first_line_indent = Inches(-0.17)
    st.paragraph_format.space_after = Pt(2.5)
    st.paragraph_format.line_spacing = 1.04

code_style = styles.add_style("Architecture", WD_STYLE_TYPE.PARAGRAPH)
code_style.font.name = "Liberation Mono"
code_style._element.rPr.rFonts.set(qn("w:ascii"), "Liberation Mono")
code_style._element.rPr.rFonts.set(qn("w:hAnsi"), "Liberation Mono")
code_style.font.size = Pt(9.2)
code_style.paragraph_format.left_indent = Inches(0.35)
code_style.paragraph_format.right_indent = Inches(0.25)
code_style.paragraph_format.space_before = Pt(3)
code_style.paragraph_format.space_after = Pt(3)
code_style.paragraph_format.line_spacing = 1.0

quote_style = styles.add_style("Interview Answer", WD_STYLE_TYPE.PARAGRAPH)
quote_style.base_style = styles["Normal"]
quote_style.font.size = Pt(10.5)
quote_style.paragraph_format.left_indent = Inches(0.28)
quote_style.paragraph_format.right_indent = Inches(0.18)
quote_style.paragraph_format.space_before = Pt(3)
quote_style.paragraph_format.space_after = Pt(7)
quote_style.paragraph_format.keep_together = True


def clear_paragraph_borders(paragraph):
    p_pr = paragraph._p.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is not None:
        p_pr.remove(borders)
    borders = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right", "between", "bar"):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "nil")
        borders.append(node)
    p_pr.append(borders)


def add_title(text, subtitle=None):
    p = doc.add_paragraph(style="Title")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.add_run(text)
    clear_paragraph_borders(p)
    if subtitle:
        s = doc.add_paragraph(style="Subtitle")
        s.add_run(subtitle)


def add_heading(text, level=1):
    return doc.add_heading(text, level=level)


def add_body(text, bold_lead=None):
    p = doc.add_paragraph()
    if bold_lead and text.startswith(bold_lead):
        p.add_run(bold_lead).bold = True
        p.add_run(text[len(bold_lead):])
    else:
        p.add_run(text)
    return p


def add_bullets(items, compact=False):
    style = "Bullet Compact" if compact else "Bullet Clean"
    for item in items:
        p = doc.add_paragraph(style=style)
        p.add_run("• ")
        if isinstance(item, tuple):
            lead, rest = item
            p.add_run(lead).bold = True
            p.add_run(rest)
        else:
            p.add_run(item)


def add_numbered(items):
    for i, item in enumerate(items, 1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.28)
        p.paragraph_format.first_line_indent = Inches(-0.22)
        p.paragraph_format.space_after = Pt(3)
        p.add_run(f"{i}. ").bold = True
        p.add_run(item)


def add_answer(text):
    p = doc.add_paragraph(style="Interview Answer")
    p.add_run(text)
    return p


def add_table(headers, rows, widths=None, font_size=9.3):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    header = table.rows[0]
    set_repeat_table_header(header)
    for idx, label in enumerate(headers):
        cell = header.cells[idx]
        set_cell_shading(cell, NAVY)
        set_cell_border(cell)
        set_cell_margins(cell, top=120, bottom=120)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(label)
        r.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)
        r.font.size = Pt(font_size)
        if widths:
            cell.width = Inches(widths[idx])
    for row_idx, values in enumerate(rows):
        row = table.add_row()
        no_split(row)
        for idx, value in enumerate(values):
            cell = row.cells[idx]
            set_cell_border(cell)
            set_cell_margins(cell)
            if row_idx % 2:
                set_cell_shading(cell, PALE_BLUE)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.02
            r = p.add_run(str(value))
            r.font.size = Pt(font_size)
            if widths:
                cell.width = Inches(widths[idx])
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def page_break():
    doc.add_page_break()


def add_timing(minute, title, goal, script):
    h = add_heading(f"{minute}  {title}", 2)
    p = doc.add_paragraph()
    p.paragraph_format.keep_with_next = True
    p.add_run("Purpose  ").bold = True
    p.add_run(goal)
    add_answer(script)


# Cover
add_title("AI Home Lab Operator Interview Guide", "Project explanation  Technical foundations  System design questions  15 to 20 minute discussion")
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(18)
p.add_run("Project focus").bold = True
p.add_run("  A private AI assisted infrastructure investigator for an Ubuntu home server")
p = doc.add_paragraph()
p.add_run("Prepared from").bold = True
p.add_run("  The HomeAiAgent repository and its verified implementation records")
p = doc.add_paragraph()
p.add_run("Current project snapshot").bold = True
p.add_run("  September 2026")
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(28)
p.add_run("Use this guide to explain the project at three depths, answer technical follow ups, and avoid overstating what has been validated.").italic = True

page_break()

# How to use
add_heading("How to use this guide", 1)
add_body("The interview story is strongest when you present the project as a safety controlled incident investigation system. The language model chooses the next diagnostic step, but ordinary application code decides what tools exist, validates every argument, records evidence, limits the loop, gates writes behind one time approval, and verifies recovery before closing the incident.")
add_heading("Preparation order", 2)
add_numbered([
    "Memorize the 30 second overview and the six sentence architecture summary.",
    "Practice the 15 to 20 minute discussion aloud until it fits your natural speaking pace.",
    "Draw the architecture and both end to end flows from memory.",
    "Choose three challenges that you personally handled and add any missing personal details.",
    "Review the foundations section so you can explain why each component exists.",
    "Use the question bank for mock interviews. Answer first, then compare with the suggested answer.",
])
add_heading("Accuracy rule", 2)
add_body("Only claim work you personally completed. The repository establishes the implemented behavior and measured results, but it does not establish whether the project was solo or collaborative. Before the interview, replace the contribution prompts in this guide with your exact ownership. Keep the measured limitations: the local qwen2.5 3B model produced valid JSON but failed the eight case diagnosis benchmark, and the deployed Gemini generation check was blocked by quota after a successful local smoke test.")
add_heading("Three levels of explanation", 2)
add_table(
    ["Depth", "When to use it", "What to cover"],
    [
        ("30 seconds", "Opening question or resume walkthrough", "Problem, users, architecture in one line, and the safety result"),
        ("2 to 3 minutes", "Explain the project", "Request flow, main components, one hard design decision, and measured status"),
        ("15 to 20 minutes", "Project deep dive", "Architecture, agent loop, data model, security, evaluation, challenges, tradeoffs, and roadmap"),
    ],
    widths=[1.15, 2.15, 3.7],
)

page_break()

# One-page cheat sheet
add_heading("Interview cheat sheet", 1)
add_heading("One sentence", 2)
add_answer("I built a private home lab operator that uses a bounded language model agent to investigate incidents through allowlisted diagnostic tools, preserve evidence in PostgreSQL, retrieve local runbooks from Qdrant, and require a signed one time operator approval before any supported change.")
add_heading("Six sentence architecture", 2)
add_numbered([
    "A Next.js dashboard authenticates the operator and proxies requests to a loopback only FastAPI backend.",
    "FastAPI owns the incident state machine and starts a bounded asynchronous investigation.",
    "The configured model, local Ollama by default or opt in Gemini, returns a schema constrained decision rather than arbitrary text or commands.",
    "The backend validates that decision against an allowlisted tool registry and sends permitted diagnostics to a separate non root host gateway.",
    "PostgreSQL stores observations, hypotheses, actions, audit events, and reports; Ollama embeddings and Qdrant retrieve runbooks and previously verified incidents.",
    "A write is executed only after exact operator approval, an HMAC signed one use dispatch, and configured recovery checks for the target and its dependencies.",
])
add_heading("Numbers worth memorizing", 2)
add_table(
    ["Item", "Verified value", "Correct interpretation"],
    [
        ("Backend tests", "161 passed", "Broad deterministic regression coverage"),
        ("Frontend tests", "9 passed", "Session and proxy behavior plus build and type checks"),
        ("Gateway operations", "19 of 19", "Execution succeeded; it does not mean every target was healthy"),
        ("Scripted incidents", "8 of 8", "Tests orchestration and safety, not LLM intelligence"),
        ("RAG retrieval", "Recall at 4 equals 11 of 11", "Small authored set, not a general quality guarantee"),
        ("qwen2.5 3B", "0 of 8 root causes", "Valid JSON did not imply sound diagnostic reasoning"),
        ("Gemini smoke", "1 of 1 in 22.4611 seconds", "One synthetic Redis case, not full acceptance"),
    ],
    widths=[1.45, 1.55, 4.0],
    font_size=8.8,
)
add_heading("Core limitation", 2)
add_body("The system is safe enough to fail closed, but model quality still determines whether it reaches a useful diagnosis. Production writes remain narrowly restricted to an isolated demo target while broader model validation and target specific verification are incomplete.")

page_break()

# Opening pitches
add_heading("Opening answers", 1)
add_heading("30 second overview", 2)
add_answer("AI Home Lab Operator is a private incident investigation tool for my Ubuntu home server. An operator describes a symptom, and a bounded LLM agent chooses from typed, allowlisted diagnostics such as HTTP checks, container inspection, logs, networking, memory, and disk. The backend records observations and hypotheses, requires evidence citations for a diagnosis, and does not expose a shell or Docker socket to the model. Any supported change needs exact human approval and a signed one time request, followed by deterministic recovery checks. I built it to explore how an agent can be useful in operations without giving probabilistic model output unrestricted control of the host.")
add_heading("2 to 3 minute architecture explanation", 2)
add_answer("The browser talks to a Next.js dashboard over Tailscale. The browser authenticates with an operator password and receives a short lived signed session cookie; the Next.js server keeps the backend bearer token and proxies only approved API paths. FastAPI owns incident creation, investigation, approvals, verification, and persistence. When an investigation starts, it runs a bounded asynchronous agent loop. On each step, the backend builds redacted context from the incident, prior observations, hypotheses, topology, retrieved runbooks, and the current tool registry. The configured reasoning provider returns a structured decision such as a tool call, diagnosis, approval request, request for user input, or stop. Pydantic and JSON Schema validation reject malformed arguments, unknown tools, unauthorized writes, duplicate calls, foreign observation IDs, and unsupported evidence claims.")
add_answer("Read only diagnostics go through a separate host gateway. That gateway runs as a dedicated service account and exposes a small vocabulary instead of a general shell. It applies its own allowlists, time and output limits, URL destination checks, redaction, and target restrictions. PostgreSQL stores the durable investigation record. Ollama embeddings and Qdrant retrieve server specific runbooks and verified incident history, but retrieved text can only guide the investigation; a diagnosis must still cite current observations. If the model proposes a permitted low risk action, the operator approves the exact tool and arguments. The backend durably claims it, signs it with HMAC, and the gateway records the action ID in a one use ledger before execution. The incident becomes resolved only when administrator configured checks confirm the target and dependent service are healthy.")
add_heading("Contribution answer to personalize", 2)
add_body("Use the following answer only where it matches your work. Replace the final sentence with one or two details that clearly distinguish your decisions from repository level facts.")
add_answer("My contribution covered the application architecture and implementation across the dashboard, FastAPI controller, bounded agent loop, database model, retrieval pipeline, host gateway, approval protocol, deployment, and evaluation harness. The decisions I would highlight are separating model reasoning from host execution, requiring current incident evidence for diagnoses, treating approvals as exact one time capabilities, and separating deterministic orchestration tests from real model quality tests. I also diagnosed and addressed [your strongest implementation problem], and I personally validated [the deployment or benchmark you ran].")

page_break()

# 15-20 minute script
add_heading("15 to 20 minute project discussion", 1)
add_body("This script is designed for roughly 17 minutes at a calm technical speaking pace. Do not recite it mechanically. Use the bold time markers to recover your place, and pause for interviewer questions after the architecture and evaluation sections.")

add_timing("0 to 1 minute", "Problem and motivation", "Establish the practical problem and project thesis.",
"I run several services on a home Ubuntu server, including a separate CodeDuel application. When something fails, troubleshooting usually means moving among container state, logs, HTTP endpoints, system services, networking, and past notes. The hard part is not collecting one metric; it is choosing the next useful check and keeping the conclusion tied to current evidence. I built AI Home Lab Operator to test whether a language model can drive that investigation while a deterministic control plane constrains what it is allowed to observe or change. The intended user is an authenticated operator on the private Tailscale network, not the public internet.")

add_timing("1 to 3 minutes", "System architecture", "Name each trust boundary and why it exists.",
"The frontend is a Next.js dashboard. It creates an expiring signed browser session, protects state changing requests against cross origin use, and proxies a fixed set of routes to a FastAPI backend. The backend is loopback only. It owns the incident state machine, database writes, model interaction, tool validation, approvals, and recovery verification. PostgreSQL is the source of truth for incidents, observations, hypotheses, proposed actions, audit events, and evaluation runs. The reasoning provider is configurable: local Ollama is the privacy first default, while Gemini is an explicit cloud option. RAG stays local using Ollama embeddings and Qdrant. Host diagnostics live behind a separate gateway process. This separation means the model and backend container never receive a general shell or a Docker socket.")

add_timing("3 to 6 minutes", "Investigation flow", "Show how a symptom becomes an evidence backed diagnosis.",
"Suppose the operator reports that CodeDuel submissions are stuck. The UI creates an incident and asks FastAPI to investigate it. FastAPI atomically claims the incident and starts a background task, with one concurrent investigation by default because the server has limited CPU and memory. The agent retrieves relevant runbooks or previously resolved incidents, then builds a bounded, redacted context. The model must return one structured decision. If it requests a diagnostic tool, the backend checks that the tool exists, its risk label is correct, and the arguments match the advertised schema. The gateway repeats enforcement and performs the check with deadlines and bounded output. The backend records the result as an observation before the next model decision. The model can update hypotheses, but supporting and contradicting observation IDs must belong to this incident. To diagnose, it must cite current observations and at least one successful diagnostic. The backend caps confidence based on distinct evidence families, so repeated logs cannot manufacture high confidence.")

add_timing("6 to 8 minutes", "Approval and recovery", "Explain the highest value safety mechanism.",
"Diagnosis and remediation are separate phases. A diagnosis can propose a low risk write such as starting or restarting an explicitly allowed container, but it cannot execute it. The action is stored with exact arguments, a reason, a status, and an expiry. When the operator approves, the service validates the evidence and checks that the topology contains recovery tests for both the action target and the affected service. It then atomically marks the action as claimed before dispatch. The backend signs the action ID, tool, canonical arguments, and short expiry with HMAC. The gateway verifies that signature and inserts the action ID into a local SQLite ledger before running it. A replay therefore fails even if someone resends the same request. If the outcome is uncertain, the system does not retry automatically. After a successful command, read only health checks run across dependencies, and only a complete match changes the incident to resolved.")

add_timing("8 to 10 minutes", "Retrieval and data", "Explain what RAG adds and what it is not allowed to prove.",
"Runbooks are split into bounded sections, embedded locally, and stored in a Qdrant collection whose name includes an embedding model identifier. That avoids mixing vectors created in incompatible embedding spaces. At investigation time, the symptom is embedded and Qdrant returns the nearest runbook or verified incident chunks above a similarity threshold. Retrieval improves context and can suggest which diagnostic to try, but it has zero weight in the confidence calculation and cannot replace a current observation. PostgreSQL remains the transactional record because incident state, relationships, approvals, and audit history need consistency and durable updates. Qdrant is a retrieval index, not the source of truth.")

add_timing("10 to 12 minutes", "Security and reliability", "Show that safety is implemented at several independent layers.",
"The important security principle is defense in depth. The dashboard is reachable only on Tailscale. The browser never sees the backend API token. The backend exposes no API documentation in production and performs constant time bearer token comparison. Model output is treated as untrusted data: it is schema validated, policy checked, redacted, bounded by steps and time, and prevented from repeating the same tool arguments indefinitely. The gateway has its own authentication, tool and target allowlists, command construction without a shell, process group timeouts, output limits, secret redaction, and URL address pinning to reduce server side request forgery and DNS rebinding risk. Containers drop Linux capabilities, use no new privileges, and expose internal services only on loopback. The honest caveat is that gateway membership in the Docker group is effectively host root authority, so the gateway is in the trusted computing base even though callers are tightly constrained.")

add_timing("12 to 15 minutes", "Testing and measured results", "Separate platform correctness from model intelligence.",
"I deliberately separated deterministic system tests from model evaluation. The deterministic eight incident suite injects a scripted provider and mock gateway into the production Agent. It passed all eight fixtures with an average of 2.875 diagnostic calls and no unsafe or repeated executions, which validates orchestration, policies, evidence ownership, and state handling. The wider suite recorded 161 passing Python tests, nine frontend tests, and 19 of 19 live read only gateway operations. The small RAG benchmark retrieved the intended runbook in the top four for all 11 authored queries. Those numbers do not establish model accuracy. In fact, qwen2.5 3B produced valid structured JSON but achieved zero of eight root cause accuracy and repeated completed diagnostics until the safety limit stopped it. A Gemini integration smoke passed one synthetic Redis incident in 22.4611 seconds, but one case is not enough for production acceptance, and a later deployed generation was blocked by free tier quota. This distinction is one of the main lessons from the project: format compliance, safe orchestration, and correct diagnosis are separate properties.")

add_timing("15 to 17 minutes", "Tradeoffs and current limits", "Demonstrate judgment instead of claiming universal choices.",
"I chose a custom bounded Python loop rather than a broad agent framework because the required decision types and safety invariants are small and explicit. I chose polling in the UI because incident updates are low frequency and one investigation runs at a time; WebSockets would add connection and reconnection complexity without changing the core workflow. I chose PostgreSQL for transactional incident state and Qdrant for vector similarity rather than forcing one datastore to serve both jobs. I kept Ollama as the default for privacy, but the CPU only machine makes small local models slow and, in the measured case, inaccurate. Gemini improves capability but introduces cloud data handling, quota, latency, and cost. The system currently permits writes only to an isolated demo container. It also verifies configured health checks rather than an actual user transaction, so a green verification can still miss a deeper application failure.")

add_timing("17 to 19 minutes", "Improvements and close", "Finish with a concrete engineering roadmap.",
"My next step would be to complete identical eight case benchmarks for the candidate reasoning models and define an acceptance threshold before enabling any production target. I would add an end to end synthetic transaction for CodeDuel submissions, queue and dependency specific health checks, metrics for queue depth and investigation latency, and alerts for gateway or database failures. I would also add high availability only if the use case justified it: multiple stateless backends behind a private load balancer, shared PostgreSQL and Qdrant, and a worker queue for investigations. The main takeaway is that an operational agent becomes trustworthy through enforceable boundaries and measured behavior, not through a persuasive prompt. The model can decide what to inspect next, but deterministic code owns authority, evidence, and state transitions.")

page_break()

# diagrams
add_heading("Whiteboard architecture", 1)
add_body("Draw the following from left to right. Mark the browser and gateway boundaries before discussing individual technologies.")
for line in [
    "Authorized browser on Tailscale",
    "            | signed session cookie",
    "            v",
    "Next.js dashboard and fixed route proxy",
    "            | backend bearer token stays server side",
    "            v",
    "FastAPI incident controller and bounded agent",
    "      |             |              |",
    "      v             v              v",
    "PostgreSQL     LLM provider     Local RAG",
    "evidence       Ollama or        Ollama embeddings",
    "and state      opt in Gemini    plus Qdrant",
    "      \\             |              /",
    "       \\            v             /",
    "        +---- validated decision --+",
    "                       | typed tool request",
    "                       v",
    "          Private host diagnostic gateway",
    "                       | allowlisted execution",
    "                       v",
    "       Linux  Docker  systemd  HTTP  DNS  network",
]:
    doc.add_paragraph(line, style="Architecture")

add_heading("Investigation state flow", 2)
for line in [
    "OPEN -> INVESTIGATING -> DIAGNOSED -> WAITING FOR APPROVAL",
    "             |                |                 |",
    "             v                v                 v",
    "          FAILED       NEED USER INPUT      VERIFYING",
    "                                                  |",
    "                                   checks pass -> RESOLVED",
    "                                   checks fail -> OPEN or waiting",
]:
    doc.add_paragraph(line, style="Architecture")
add_body("State transitions are persisted. A backend restart marks an in progress investigation or verification as failed and never replays a write whose outcome may be uncertain.")

add_heading("End to end diagnostic flow", 2)
add_numbered([
    "The operator creates an incident with a title, description, service, and severity.",
    "FastAPI validates the request, redacts sensitive values, stores the incident, and writes an audit event.",
    "The investigate endpoint atomically changes OPEN or FAILED to INVESTIGATING and starts an asynchronous task.",
    "The agent loads the typed tool registry and optionally retrieves local runbook and incident context.",
    "The LLM returns one schema constrained decision.",
    "The backend validates the tool, risk class, arguments, loop budget, and duplicate signature.",
    "The gateway authenticates the backend, repeats policy checks, executes one bounded diagnostic, and redacts output.",
    "The backend stores the observation, interpretation, duration, and hypothesis links.",
    "The loop repeats until a diagnosis, user input request, stop, policy limit, runtime limit, or error.",
    "A diagnosis is accepted only when its cited observation IDs belong to the incident and include a successful diagnostic.",
])

add_heading("End to end remediation flow", 2)
add_numbered([
    "The model proposes a supported low risk action after an evidence backed diagnosis.",
    "The backend persists the exact tool, arguments, reason, expiry, and PENDING status.",
    "The operator approves that exact action through an authenticated request.",
    "The service revalidates evidence, tool policy, and administrator owned verification checks.",
    "An atomic database update marks the action APPROVED and records dispatch before the external side effect.",
    "The backend creates a short lived HMAC signature over the action ID, tool, canonical arguments, and expiry.",
    "The gateway verifies the signature and consumes the action ID in its SQLite ledger before execution.",
    "The write runs once. An uncertain result is surfaced for inspection and is not automatically retried.",
    "Configured read only dependency and service checks run after the action.",
    "Only complete verification marks the action verified and the incident resolved; resolved evidence may be indexed for future retrieval.",
])

page_break()

# Architecture components
add_heading("Component responsibilities", 1)
add_table(
    ["Component", "Responsibility", "Why it is separate"],
    [
        ("Next.js frontend", "Operator sign in, dashboard, incident history, progress, hypotheses, approvals, and server overview", "Keeps browser concerns and the backend token out of client code"),
        ("FastAPI backend", "API, incident state, agent orchestration, evidence validation, approval, verification, and audit", "Central deterministic policy and transactional control plane"),
        ("LLM provider", "Returns one structured next decision or report", "Reasoning is replaceable and remains untrusted"),
        ("PostgreSQL", "Durable incidents, observations, hypotheses, actions, audits, and evaluations", "Provides transactions, relationships, and restart survival"),
        ("Ollama embeddings", "Produces local vectors for runbook and incident text", "Keeps retrieval data local even when Gemini reasoning is enabled"),
        ("Qdrant", "Top K vector similarity search", "Specialized retrieval index with cosine distance"),
        ("Diagnostic gateway", "Executes typed host diagnostics and a narrow write vocabulary", "Keeps privileged host interaction outside the model and backend container"),
        ("Topology configuration", "Defines services, dependencies, targets, and health checks", "Administrator owned policy separates deploy facts from model suggestions"),
        ("Runbooks", "Server specific troubleshooting guidance", "Adds local operational context without granting authority"),
    ],
    widths=[1.35, 3.15, 2.5],
    font_size=8.9,
)

add_heading("Three trust boundaries to point out", 2)
add_bullets([
    ("Browser to frontend  ", "The browser gets a signed session, while the backend credential stays in the Next.js server."),
    ("Model to controller  ", "The model proposes a typed decision; local validation and policy decide whether it is accepted."),
    ("Controller to host  ", "The backend requests one narrow operation; the gateway independently authenticates, validates, executes, and redacts it."),
])

page_break()

add_heading("Technology choices and alternatives", 1)
add_table(
    ["Choice", "Reason in this project", "Alternative and tradeoff"],
    [
        ("FastAPI", "Async HTTP, Pydantic validation, simple dependency based authentication, and a Python agent codebase", "Express would be viable but would split core orchestration from the Python evaluation and model tooling"),
        ("Next.js", "Server side session handling and a controlled backend proxy alongside the React UI", "A static React client would need a different secure route to the backend token"),
        ("PostgreSQL", "Transactional state changes, foreign keys, unique incident step numbers, and relational audit history", "MongoDB offers flexible documents but provides less benefit for these strongly related records"),
        ("Qdrant", "Purpose built cosine vector search and metadata payloads", "pgvector could reduce service count, but Qdrant keeps retrieval operations specialized"),
        ("Ollama", "Private local inference and embeddings with no cloud dependency in default mode", "Cloud models may reason better but introduce data transfer, quota, cost, and provider availability"),
        ("Gemini option", "Stronger observed reasoning in an initial integration smoke while preserving local storage and embeddings", "Local models preserve privacy but were slow and weak on the measured CPU only hardware"),
        ("Custom agent loop", "Small decision vocabulary and explicit safety invariants are easy to inspect", "A general agent framework could accelerate features but add abstraction and a larger trusted surface"),
        ("Polling", "Simple for low frequency updates and one concurrent investigation", "WebSockets reduce update latency but require connection lifecycle, fan out, and reconnect handling"),
        ("Docker Compose", "Fits a single home server and makes resource and network boundaries explicit", "Kubernetes adds scheduling and resilience but is excessive for the present scale"),
    ],
    widths=[1.25, 3.05, 2.7],
    font_size=8.7,
)

# Base topics
add_heading("Technical foundations", 1)

add_heading("Agents and tool calling", 2)
add_body("A chatbot mainly generates a response. An agent participates in a loop: observe the current state, choose an action, execute through a tool, store the result, and decide again. The Home Lab Operator is agentic because the next diagnostic depends on prior results. It is bounded because the model chooses only among declared decision types and tools, while deterministic code limits steps, runtime, concurrency, repetitions, evidence, and writes.")
add_heading("Structured output", 3)
add_body("Structured output asks the model for data that conforms to a schema. It reduces parsing ambiguity but does not make the decision correct. This project validates the response twice conceptually: the provider enforces or requests JSON structure, and local Pydantic and JSON Schema checks enforce the actual application contract. A bounded repair retry handles formatting errors. The qwen2.5 result demonstrates the key distinction: every response can be valid JSON while the diagnostic reasoning remains poor.")

add_heading("Finite state machines", 2)
add_body("A finite state machine represents a workflow as named states and permitted transitions. Incident and action statuses prevent contradictory operations, such as approving an action twice or starting two investigations on the same incident. Atomic conditional database updates make the check and transition one operation, reducing race conditions between concurrent requests.")
add_bullets([
    ("State invariant  ", "Only OPEN or FAILED incidents can be claimed for investigation."),
    ("Action invariant  ", "Only a nonexpired PENDING action with no execution timestamp can be approved."),
    ("Recovery invariant  ", "An incident becomes RESOLVED only after all configured checks match."),
])

add_heading("Asynchronous I O and concurrency", 2)
add_body("Asynchronous I O lets one process wait for network operations without blocking the event loop. The API returns 202 Accepted after scheduling the investigation, so the HTTP request does not remain open for minutes of model and diagnostic work. A semaphore and application level task tracking bound concurrency. The deployment uses one backend worker and one concurrent investigation by default, which simplifies in memory coordination but limits horizontal scaling until task ownership moves to a durable distributed queue.")

add_heading("RAG embeddings and vector search", 2)
add_body("Retrieval augmented generation adds selected external context to the model prompt. An embedding converts text into a numeric vector whose geometry represents semantic similarity. Qdrant compares a query vector with stored vectors using cosine similarity, returns the top K items above a threshold, and includes their source metadata. Chunking matters because an entire long runbook may mix unrelated procedures, while fragments that are too small lose context. The project groups sections into chunks below a size budget and keeps different embedding models in different collections.")
add_bullets([
    ("RAG helps with  ", "local terminology, service topology, known checks, and prior verified incidents."),
    ("RAG does not prove  ", "that an old incident explains the current symptom."),
    ("Defense against stale context  ", "require current observations and give historical context zero confidence weight."),
])

add_heading("Evidence and confidence", 2)
add_body("The database links each hypothesis to supporting and contradicting observation IDs. Diagnosis citations must refer to observations from the same incident, which prevents a model from inventing IDs or borrowing unrelated evidence. Confidence is treated as a model estimate and then capped using successful, distinct diagnostic families. This is a heuristic guardrail, not statistical calibration: a 0.8 value does not mean that 80 percent of similarly scored diagnoses are correct.")

add_heading("Database foundations", 1)
add_table(
    ["Table", "Important fields", "Relationships and access pattern"],
    [
        ("incidents", "id, title, description, service, status, severity, root cause, confidence, report, agent state, timestamps", "Parent record. List by newest; fetch one with all related evidence and actions."),
        ("observations", "incident id, step number, tool, arguments, raw and normalized results, interpretation, duration, phase", "Many per incident. Unique incident and step pair preserves order."),
        ("hypotheses", "incident id, description, confidence, status, supporting and contradicting IDs", "Many per incident. Links to observations are validated by application logic."),
        ("actions", "incident id, tool, arguments, reason, risk, approval status, expiry, result, verification status", "Many per incident. Approval checks status and execution timestamp before an atomic claim."),
        ("audit events", "incident id, event type, redacted payload, created time", "Append oriented trace for investigation, approval, execution, and verification."),
        ("evaluation runs", "provider, metrics, per scenario results, created time", "Stores benchmark identity and measured behavior."),
    ],
    widths=[1.2, 3.2, 2.6],
    font_size=8.7,
)
add_heading("Indexes and consistency", 2)
add_bullets([
    "Primary keys are UUID strings, which can be generated without a central sequence and are safe to expose as opaque identifiers.",
    "Incident status is indexed because the application filters active or recoverable workflow states.",
    "Foreign keys such as incident id are indexed to load related records efficiently.",
    "The unique incident id and step number constraint prevents duplicate observation positions.",
    "Approval uses a conditional update on ID, PENDING status, and a null execution timestamp so two requests cannot both claim the action.",
])
add_heading("SQL versus NoSQL answer", 2)
add_answer("I chose PostgreSQL because the core data is relational and stateful: observations, hypotheses, actions, and audits all belong to an incident, and approval transitions need atomicity. JSON columns still let me store tool specific payloads without creating a table for every diagnostic shape. A document database could store the incident aggregate, but transactional conditional updates, foreign keys, and familiar indexing made PostgreSQL a better default. Qdrant is separate because similarity search has a different access pattern from transactional state.")

page_break()

add_heading("API foundations", 1)
add_table(
    ["Endpoint", "Purpose", "Key behavior"],
    [
        ("GET health and healthz", "Backend liveness", "Checks a database query and returns 503 if unavailable"),
        ("GET api health", "Component status", "Checks gateway, Qdrant, selected model provider, and database"),
        ("GET and POST api incidents", "List or create incidents", "Pagination on list; strict validation and redaction on create"),
        ("GET api incidents id", "Incident detail", "Returns observations, hypotheses, actions, and audit events"),
        ("POST api incidents id investigate", "Start agent work", "Atomic claim, conflict checks, 202 response, background task"),
        ("POST api incidents id verify", "Run configured recovery checks", "Requires an evidence backed diagnosis"),
        ("POST api actions id approve or reject", "Human decision", "Exact action, expiry, replay guard, and persisted audit"),
        ("GET api topology and tools", "Explain configured services and capabilities", "Returns redacted topology and risk labeled tool registry"),
        ("POST api runbooks ingest", "Build local retrieval index", "Requires RAG and returns indexed chunk count"),
        ("GET api evaluations", "Recent benchmark records", "Returns the latest 20 runs"),
    ],
    widths=[2.2, 1.65, 3.15],
    font_size=8.4,
)
add_heading("HTTP concepts to explain", 2)
add_bullets([
    ("202 Accepted  ", "The investigation has been accepted for asynchronous processing, not completed."),
    ("401 Unauthorized  ", "Authentication credentials are absent or invalid."),
    ("404 Not Found  ", "The incident, action, or proxy route does not exist."),
    ("409 Conflict  ", "The request conflicts with the current workflow state, such as a duplicate investigation or stale approval."),
    ("503 Service Unavailable  ", "A required dependency or configured capability is unavailable."),
])

add_heading("Security foundations", 1)
add_heading("Authentication authorization and session security", 2)
add_body("Authentication proves who is calling; authorization decides what that identity may do. The browser authenticates to the frontend and receives a signed, expiring session cookie. The server side proxy uses the backend bearer token, so the token is not stored in browser JavaScript. Cross origin mutation checks reduce cross site request forgery risk. Backend and gateway authentication are separate boundaries.")

add_heading("Least privilege and defense in depth", 2)
add_body("Least privilege grants only the authority required for a task. The model receives tool descriptions, not shell access. The backend container has no Docker socket. The gateway exposes only typed operations and configured targets. Each layer repeats checks because a bug or compromise in one layer should not automatically grant broader power. The gateway remains sensitive because Docker group access can control the host through containers; therefore its code, configuration, credentials, and service account are part of the trusted computing base.")

add_heading("HMAC approvals and replay protection", 2)
add_body("A hash based message authentication code proves that a message was produced by a party holding a shared secret and that its signed fields were not changed. The backend signs the action ID, tool name, canonical JSON arguments, and expiry. Canonicalization matters because both sides must hash the same byte sequence. The gateway compares signatures in constant time and consumes each action ID once in SQLite. The signature gives integrity and authenticity; the expiry and ledger give freshness and replay resistance.")

add_heading("Input validation and command safety", 2)
add_body("JSON Schema restricts tool argument names, types, and values. Target allowlists prevent a model from selecting arbitrary containers, services, or URLs. Host commands are built as argument arrays and launched with shell disabled, which avoids shell metacharacter interpretation. Processes run in their own group so a timeout can terminate the full subprocess tree. Output byte limits prevent an unexpectedly large command response from exhausting memory or flooding model context.")

add_heading("Server side request forgery and DNS rebinding", 2)
add_body("Server side request forgery occurs when an attacker makes a server request an unintended network destination. The gateway validates the URL scheme and resolved address scope, rejects mixed or disallowed address answers, and pins the numeric address used for the connection. Pinning closes the gap in which a hostname could resolve to an allowed address during validation and a forbidden address during the actual connection. Redirects are not followed automatically.")

add_heading("Secrets and privacy", 2)
add_body("Secrets live in environment files excluded from Git. Redaction covers sensitive key names, bearer values, database URLs, private keys, cookies, and common credential formats before data reaches logs, storage, the UI, or a cloud model. Local Ollama keeps reasoning and embeddings on the server. When Gemini is enabled, bounded redacted context goes to Google for reasoning, while embeddings and persisted data stay local. That is a deliberate privacy and capability tradeoff, not a zero data transfer design.")

add_heading("Reliability and distributed systems foundations", 1)
add_heading("Timeouts retries and uncertain outcomes", 2)
add_body("Read operations can often be retried because they do not change state. Write retries are dangerous: a timeout may mean the remote side completed the action but the response was lost. This project records the write claim before dispatch and never automatically retries an uncertain write. The operator must inspect current state. The one use gateway ledger also rejects a repeated approval.")

add_heading("Idempotency", 2)
add_body("An idempotent operation has the same externally visible result when repeated. A health check is naturally safe to repeat. A restart may be operationally repeatable but is not harmless, so the system treats the approval as exactly once rather than assuming idempotency. The action ID acts as an idempotency key at the gateway ledger.")

add_heading("Horizontal and vertical scaling", 2)
add_body("Vertical scaling adds CPU or memory to one machine. Horizontal scaling adds instances. The current system favors vertical simplicity: one FastAPI worker and one active investigation. Multiple API instances would require moving task ownership, locks, and progress from process memory to a durable queue or database lease. Model inference, gateway throughput, PostgreSQL connections, Qdrant search, and the number of diagnostic workers would need independent limits.")
add_heading("Plausible scaled design", 3)
for line in [
    "Private load balancer",
    "        v",
    "Multiple stateless frontend and API instances",
    "        | create durable investigation job",
    "        v",
    "Shared queue with leases and deduplication",
    "        v",
    "Bounded investigation workers -> model provider",
    "        |",
    "        +-> PostgreSQL source of truth",
    "        +-> Qdrant retrieval",
    "        +-> per host diagnostic gateways",
]:
    doc.add_paragraph(line, style="Architecture")
add_body("A queue improves durability and backpressure, but writes should still use exact approval IDs, per incident serialization, and reconciliation after uncertain outcomes.")

add_heading("Polling versus WebSockets", 2)
add_answer("Polling was appropriate because the dashboard has a small number of private users, updates arrive at human scale, and only one investigation runs at a time. It is stateless and easy to recover after refresh. WebSockets or server sent events would reduce latency and request overhead for many concurrent live timelines, but they add connection state, authentication refresh, reconnect semantics, and multi instance fan out. I would switch when measured update volume or user experience justified it.")

add_heading("Observability", 2)
add_body("Logs show individual events; metrics aggregate behavior over time; traces connect work across components. The project already stores redacted audit events, tool duration, model latency, token usage, decisions, observations, and evaluation results. A production extension should export request latency, investigation duration, tool error rate, queue depth, model retry rate, diagnosis acceptance, approval outcomes, and verification failures to a monitoring system with correlation by incident ID.")

# decisions
add_heading("Design decisions to defend", 1)

decisions = [
    ("Why separate the gateway from the backend", "The backend handles untrusted model output and web requests. Giving it a Docker socket would turn a web or prompt handling flaw into host control. A separate gateway narrows the interface to typed operations, applies target policy near execution, and keeps privileged host access out of the application container. The gateway is still highly trusted, but its exposed vocabulary and attack surface are smaller."),
    ("Why no general shell tool", "A shell makes validation extremely difficult because commands can compose, redirect, expand variables, spawn children, and reach unexpected files or networks. Typed tools make arguments enumerable, schema validatable, auditable, and target restricted. The cost is reduced flexibility and more code for each new diagnostic."),
    ("Why asynchronous investigations", "Model calls and host diagnostics can take seconds or minutes. Holding the request open creates timeouts and poor recovery behavior. Returning 202 and persisting progress lets the UI poll, lets the workflow survive browser refreshes, and makes state transitions explicit."),
    ("Why PostgreSQL and Qdrant", "PostgreSQL owns transactional workflow state and relationships. Qdrant performs vector nearest neighbor retrieval. Using two stores adds operational overhead, but it keeps each workload aligned with the database built for it and avoids treating a retrieval index as authoritative state."),
    ("Why local embeddings with optional cloud reasoning", "Runbooks and history remain in a local retrieval pipeline regardless of the reasoning provider. This preserves privacy for stored knowledge and avoids re embedding when the reasoning provider changes. Cloud reasoning still receives selected redacted context, so the privacy boundary must be stated accurately."),
    ("Why evidence citations", "Without observation IDs, a fluent report can hide whether the conclusion came from current diagnostics, historical context, or invention. Ownership checks make the report traceable and prevent cross incident citation. They do not automatically prove causal correctness, so operator review still matters."),
    ("Why confidence ceilings", "Models tend to express unsupported certainty. The backend caps confidence using distinct successful evidence families and contradictions. The ceiling encourages conservative presentation, but it is a heuristic and should not be described as calibrated probability."),
    ("Why exact approval instead of approve all", "The risk depends on the tool, target, and arguments. Exact approval prevents the model from changing the action after consent and prevents one approval from authorizing future retries. It creates more operator friction, which is acceptable for rare infrastructure writes."),
    ("Why verify after remediation", "Command success only proves that the command returned successfully. It does not prove that the container is healthy, its dependency is reachable, or the user facing service recovered. Verification checks the configured outcome before closing the incident."),
]
for title, answer in decisions:
    add_heading(title, 2)
    add_answer(answer)

# challenges
add_heading("Strong challenge stories", 1)
add_body("Choose three that you personally handled. Use Problem, Diagnosis, Root cause, Solution, Result, and Learning. The details below are grounded in the repository; add your personal debugging steps where indicated.")

add_heading("Challenge 1  Valid JSON but poor reasoning", 2)
add_bullets([
    ("Problem  ", "The local qwen2.5 3B model produced schema valid decisions but did not finish the eight synthetic incidents correctly."),
    ("Diagnosis  ", "Benchmark reports showed zero of eight root causes, one of eight top three accuracy, and 24 rejected duplicate attempts."),
    ("Root cause  ", "Output structure was reliable, but the small CPU model repeatedly selected diagnostics it had already completed instead of synthesizing the evidence."),
    ("Solution  ", "The controller rejected identical tool and argument signatures, stopped after repeated policy failures, exposed completed diagnostic targets in the decision grammar, and requested a concise evidence assessment before the next choice."),
    ("Result  ", "The system failed safely with no unsafe actions or invalid JSON. Model acceptance remained blocked instead of being inferred from orchestration tests."),
    ("Learning  ", "Structured output, tool correctness, and diagnostic reasoning require separate metrics."),
])
add_answer("Interview version: The surprising failure was that the model followed the JSON contract perfectly but still behaved badly. I found that by looking beyond parse success and measuring root cause accuracy and duplicate diagnostic attempts. I added deterministic repeat rejection and a bounded failure threshold, then changed the decision context to make completed targets explicit. The system did not magically become accurate, but it became measurably safe and honest about failure. That taught me to evaluate agent behavior, not just response format.")

add_heading("Challenge 2  Safe writes across a network boundary", 2)
add_bullets([
    ("Problem  ", "An approved restart must run once, even if requests race, time out, or are replayed."),
    ("Diagnosis  ", "A simple approved boolean is insufficient because it can be reused and does not bind consent to exact arguments."),
    ("Root cause  ", "Distributed writes have an ambiguity window between durable local state and the external side effect."),
    ("Solution  ", "Atomically claim the database action before dispatch, sign the exact request with a short lived HMAC, and consume its action ID in a gateway ledger before execution. Never auto retry an uncertain write."),
    ("Result  ", "The live demo rejected unsigned writes and replays, executed the approved start once, verified recovery, and indexed the resolved incident."),
    ("Learning  ", "Exactly once execution cannot be assumed from HTTP success; it needs durable identity, deduplication, and explicit reconciliation."),
])

add_heading("Challenge 3  Gemini structured schema compatibility", 2)
add_bullets([
    ("Problem  ", "The Gemini provider initially failed when given the full nested decision schema and dynamic observation ID constraints."),
    ("Diagnosis  ", "Direct integration tests isolated provider schema limitations rather than treating the failure as model reasoning."),
    ("Root cause  ", "The provider supported a narrower subset of JSON Schema than the local application contract."),
    ("Solution  ", "Generate a provider compatible schema, keep full Pydantic validation in the backend, and allow one bounded repair retry."),
    ("Result  ", "A direct structured smoke completed in 6.7394 seconds and the Redis production loop fixture passed in 22.4611 seconds."),
    ("Learning  ", "Provider level constraints improve reliability, but local validation must remain authoritative and portable."),
])

add_heading("Challenge 4  Safe HTTP diagnostics", 2)
add_bullets([
    ("Problem  ", "An HTTP check tool could become an SSRF primitive that reaches arbitrary internal or metadata addresses."),
    ("Diagnosis  ", "Validating only the hostname string is vulnerable to alternate address forms, mixed DNS answers, and DNS rebinding."),
    ("Root cause  ", "The resolved address can differ between policy validation and connection establishment."),
    ("Solution  ", "Resolve and validate all addresses, enforce target scope, pin the selected numeric address into the socket, preserve the hostname for TLS, bound the entire request, and avoid redirects."),
    ("Result  ", "Gateway tests cover network scope, rebinding, deadlines, and bounded output."),
    ("Learning  ", "Network tools must validate the destination at the moment of connection, not only at input parsing time."),
])

# failures
add_heading("Failure scenarios", 1)
add_table(
    ["Failure", "Current behavior", "Production improvement"],
    [
        ("Model unavailable", "Investigation records a failure and does not fabricate a diagnosis", "Provider health alerts, backoff for read only inference, and an operator selected fallback"),
        ("Gemini quota or 429", "No diagnostic decision is executed from the failed request", "Quota monitoring, budget controls, and a validated local fallback"),
        ("Ollama is slow", "Step and total runtime bounds eventually stop work", "Smaller validated model, hardware acceleration, prompt caching, or cloud opt in"),
        ("PostgreSQL unavailable", "Health returns 503 and durable workflow cannot proceed", "Backups, restore rehearsal, monitoring, and optional replica if availability warrants"),
        ("Qdrant unavailable", "Retrieval failure is recorded; investigation may continue without RAG", "Retry reads, rebuild runbooks, preserve coordinated vector backups"),
        ("Gateway unavailable", "Tool call fails and is stored as transport failure, not target failure", "Gateway health alert and explicit operator diagnosis"),
        ("Backend restarts", "INVESTIGATING or VERIFYING incidents become FAILED", "Durable work queue and leases for controlled resumption of read work"),
        ("Write response times out", "Outcome becomes unknown and no automatic retry occurs", "Reconcile target state using read only checks before any new approval"),
        ("Verification fails", "Incident stays open or returns to an actionable state", "Richer service specific and user journey checks"),
        ("Many incidents arrive", "Concurrency limit returns conflict when the provider is busy", "Durable queue, backpressure, prioritization, and horizontally scaled workers"),
        ("Compromised gateway", "Allowlist limits callers but Docker group authority remains severe", "Stronger host isolation, rootless per target control, separate gateways, and OS policy hardening"),
        ("Stale runbook", "It can guide tool selection but cannot satisfy current evidence rules", "Version, review date, ownership, and retrieval feedback for runbooks"),
    ],
    widths=[1.35, 2.85, 2.8],
    font_size=8.5,
)
add_heading("Good failure answer pattern", 2)
add_answer("First I would distinguish a control plane failure from evidence that the monitored service is down. I would preserve the incident and the last durable state, avoid retrying any uncertain write, and use independent read only checks to establish current state. Then I would recover the failed dependency and resume only through an allowed transition. If the current implementation does not support that recovery safely, I would say so and require operator intervention.")

# performance/testing
add_heading("Performance and testing", 1)
add_heading("Likely bottlenecks", 2)
add_table(
    ["Area", "Why it can dominate", "How to measure and improve"],
    [
        ("Local inference", "CPU only generation takes seconds per step and multiple steps per incident", "First token time, tokens per second, total model latency; tune context, model, threads, or hardware"),
        ("Diagnostic chain", "Sequential evidence gathering accumulates network and command latency", "Per tool duration; stop when evidence is sufficient and parallelize only independent safe reads"),
        ("Context growth", "Every observation increases prompt size and evaluation cost", "Prompt characters and tokens; compact results and omit completed finite targets"),
        ("Database", "Repeated incident detail loads can grow with observations and audits", "Query latency and row counts; indexes, selective loading, pagination, and connection pooling"),
        ("Polling", "Many clients could create repeated detail reads", "Requests per second; adaptive intervals, ETags, server sent events, or cached summaries"),
        ("Retrieval", "Embedding generation is usually more expensive than vector lookup", "Embedding latency, query latency, recall; cache repeated queries and tune chunking"),
    ],
    widths=[1.3, 2.85, 2.85],
    font_size=8.6,
)

add_heading("Testing pyramid for this system", 2)
add_bullets([
    ("Unit tests  ", "redaction, schema validation, confidence ceilings, result matching, session signing, and route policy."),
    ("Integration tests  ", "FastAPI with a test database, provider adapters, gateway approval signatures, migrations, and RAG protocol."),
    ("Orchestration regression  ", "production Agent with a scripted provider and synthetic gateway fixtures."),
    ("Real model evaluation  ", "same fixtures and scoring with actual Ollama or Gemini decisions."),
    ("Live read only checks  ", "deployed gateway operations and private port exposure."),
    ("Controlled write acceptance  ", "isolated demo target for approval, replay rejection, recovery, and history indexing."),
])
add_heading("How to explain the benchmark honestly", 2)
add_answer("The scripted eight of eight result tells me that the controller enforces the intended workflow when it receives good decisions. It does not tell me that an LLM will produce those decisions. The qwen2.5 zero of eight result directly measures that gap. The Gemini one case smoke proves integration on one fixture, not general diagnostic accuracy. I would require a larger, identical evaluation and explicit thresholds before changing the production write policy.")

add_heading("Additional tests worth adding", 2)
add_bullets([
    "Property based tests for schema and target validation with unusual Unicode, numeric, and nested inputs.",
    "Concurrency tests that race approval, rejection, expiry, and duplicate investigation requests.",
    "Crash tests around the database claim and gateway dispatch boundary.",
    "Prompt injection fixtures inside logs and runbooks to confirm that retrieved text cannot widen tool authority.",
    "End to end browser tests for authentication expiry, CSRF rejection, approval confirmation, and incident refresh.",
    "A real synthetic CodeDuel submission that validates API, Redis, worker, judge, database, and response path.",
])

# Q bank
add_heading("Interview question bank", 1)

questions = [
    ("What makes this an agent rather than a chatbot", "It repeatedly chooses the next diagnostic based on observations, invokes tools, stores results, updates hypotheses, and stops on a diagnosis or bounded terminal condition. The model does not act freely; deterministic code owns the loop and authority."),
    ("Could prompt injection in logs make it run a command", "Logs and runbooks are untrusted context. The model can only return one schema constrained decision using a declared tool. Both backend and gateway validate tool names, risk labels, arguments, and targets, and there is no shell tool. Injection can still influence which permitted read is chosen, so evaluation and context labeling remain important."),
    ("Why is the gateway safer than mounting the Docker socket", "A Docker socket exposes an extremely broad control API. The gateway reduces the callable interface to specific operations and targets, adds authentication, time and output limits, redaction, and one time approval verification. It is a reduction in attack surface, not proof that the gateway itself is harmless."),
    ("How do you prevent hallucinated evidence", "The diagnosis must cite observation IDs that exist in the current incident and include a successful diagnostic. The backend validates ownership. That prevents fabricated citations, although it cannot prove the model interpreted valid evidence correctly."),
    ("Why not let the model set confidence", "It can propose confidence, but the backend caps it according to distinct successful evidence families and contradictions. The cap reduces unsupported certainty. It remains a heuristic, so the UI labels it as an estimate."),
    ("What happens when a tool call fails", "The failure is stored as an observation. A transport or permission failure is not treated as proof that the target itself failed. The model may choose another allowed check, or the loop ends with a visible failure or request for user input."),
    ("How do you stop infinite loops", "The loop limits total steps, runtime, model and tool time, context size, and identical tool argument signatures. Repeated policy failures cause the investigation to stop rather than repeatedly asking the model forever."),
    ("How would you add a new monitored service", "Add its service definition, dependencies, and health checks to topology configuration, then separately add each permitted gateway target. Service metadata does not itself grant execution permission. Tests validate the new configuration before deployment."),
    ("How would you add a new tool", "Define a narrow operation and JSON Schema, implement it without a general shell, assign a risk level, add backend and gateway allowlist handling, constrain targets and output, write negative security tests, then expose it to the model. A write also needs approval and recovery policy."),
    ("Why use a vector database", "Runbook queries are semantic and may not share exact keywords with the stored procedure. Embeddings support nearest neighbor retrieval. Qdrant handles that access pattern, while PostgreSQL remains authoritative for workflow state."),
    ("What if retrieved context is wrong", "It may lead the model toward an unhelpful check, but it cannot satisfy diagnosis evidence rules. Current observations remain required. I would add runbook ownership, review dates, retrieval evaluation, and feedback to manage stale content."),
    ("Why use a database JSON column", "Tool results and reports vary by operation, so JSON preserves their structure without a new relational table per shape. Stable relationships and workflow fields remain typed columns for constraints and indexes."),
    ("Is HMAC encryption", "No. HMAC provides message integrity and authentication using a shared secret. It does not hide the request. Network confidentiality still comes from the private network and transport controls."),
    ("Can you guarantee exactly once execution", "Not in the strongest distributed systems sense. The durable claim and gateway ledger prevent known duplicates, but a crash at a boundary can leave an uncertain outcome. The safe policy is no automatic retry and explicit state reconciliation."),
    ("What happens if two users approve together", "A conditional atomic update lets only one request claim a still pending, unexecuted action. The other receives a conflict. The gateway ledger independently rejects reuse of the same action ID."),
    ("Why is a successful restart not enough", "The command can succeed while the application is still unhealthy or a dependency remains down. The system runs administrator defined target and dependency checks and only resolves the incident if all expected results match."),
    ("Why one concurrent investigation", "The deployment is a consumer CPU server and local inference is expensive. One investigation keeps resource use predictable and simplifies task coordination. A durable queue and worker leases would be needed before increasing concurrency across processes."),
    ("Why not Kubernetes", "The current deployment is one private home server. Compose gives resource limits, startup dependencies, volumes, and network bindings with much less operational overhead. Kubernetes becomes relevant if scheduling across hosts, automated failover, or many independently scaled services becomes a real requirement."),
    ("How does the browser reach the backend", "The browser calls the Next.js server. After password authentication it holds a signed session cookie. The Next.js proxy sends the backend bearer token on approved paths. FastAPI listens only on loopback, so it is not directly reachable on the Tailscale address."),
    ("How do you handle secrets in model context", "Input and outputs pass through key and pattern based redaction, strings and lists are bounded, and environment secrets are never intentionally included. With Gemini, selected redacted context leaves the server, so provider mode is an explicit privacy choice."),
    ("What is your biggest limitation", "Reasoning quality is not yet accepted across the full benchmark. The local model failed all eight root causes, and Gemini has only one passing synthetic scenario plus a quota blocked deployment check. Production writes therefore remain disabled except for an isolated demo target."),
    ("What would you do with one more month", "Complete comparable model evaluations, add a full CodeDuel synthetic transaction, improve operational metrics and alerts, rehearse restore, and tighten gateway isolation. I would enable a production write target only after model accuracy and target specific verification meet explicit thresholds."),
    ("What did you learn", "The main lesson was to separate language model capability from system safety. Schema compliance is not reasoning accuracy, a successful command is not recovery, and historical similarity is not current evidence. Those distinctions shaped the architecture and evaluation."),
]

for question, answer in questions:
    add_heading(question, 2)
    add_answer(answer)

# Fast follow up drills
add_heading("Rapid follow up drills", 1)
add_table(
    ["Prompt", "Answer in one line"],
    [
        ("Authentication versus authorization", "Authentication identifies the operator; authorization constrains the action they may perform."),
        ("Hash versus HMAC", "A hash detects changes; HMAC also authenticates the message using a secret."),
        ("Embedding", "A dense numeric representation used here to compare semantic similarity between incident text and runbooks."),
        ("Cosine similarity", "The angle based similarity between two vectors, largely independent of their magnitude."),
        ("Top K", "Return the K nearest stored vectors before applying any additional score threshold."),
        ("Backpressure", "Limit or queue incoming work when workers are saturated instead of allowing unbounded concurrency."),
        ("Race condition", "Behavior depends on timing between concurrent operations; atomic conditional updates remove key approval races."),
        ("Idempotency key", "A unique operation identifier used to recognize and reject duplicate execution attempts."),
        ("SSRF", "A server is induced to request an unintended destination; address validation and connection pinning reduce it."),
        ("DNS rebinding", "A hostname changes its resolved address between validation and use; pinning the validated IP closes that gap."),
        ("RAG", "Retrieve relevant external text and add it to the model context before generation."),
        ("Hallucination", "A plausible model claim unsupported by the system's available evidence."),
        ("Calibration", "Whether stated probabilities match observed frequencies; this project's confidence is not calibrated."),
        ("Horizontal scaling", "Add instances; it requires shared coordination rather than relying on process memory."),
        ("Vertical scaling", "Give one instance more CPU, memory, or accelerator capacity."),
        ("Liveness versus readiness", "Liveness says a process is running; readiness says it can serve its intended work."),
        ("Audit log", "An append oriented record of important actions and decisions for reconstruction and review."),
        ("Trust boundary", "A point where data or authority crosses between components with different security assumptions."),
    ],
    widths=[2.0, 5.0],
    font_size=8.8,
)

add_heading("Questions to ask the interviewer", 1)
add_bullets([
    "In your production systems, where do you draw the boundary between automated diagnosis and automated remediation?",
    "How does your team evaluate agent or automation quality separately from platform reliability?",
    "Which failure modes have been hardest to reproduce in staging, and how do you capture evidence during incidents?",
    "Do your services use a shared control plane for operational actions, or does each service own its own remediation path?",
    "What would make this project discussion more relevant to the systems your team operates?",
])

# honesty/checklist
add_heading("Personalization checklist", 1)
add_body("Complete this page before the interview. It contains the only facts the repository cannot determine for you.")
add_table(
    ["Item to confirm", "Your final answer"],
    [
        ("Was this solo or team work", "____________________________________________"),
        ("Your exact ownership", "____________________________________________\n____________________________________________"),
        ("Time period and hours", "____________________________________________"),
        ("Why you personally chose this project", "____________________________________________\n____________________________________________"),
        ("Hardest bug you personally diagnosed", "____________________________________________\n____________________________________________"),
        ("A decision you changed after evidence", "____________________________________________\n____________________________________________"),
        ("Current live demo status on interview day", "____________________________________________"),
        ("Any metrics updated after 13 September 2026", "____________________________________________"),
        ("Resume bullet exact wording", "____________________________________________\n____________________________________________"),
    ],
    widths=[2.55, 4.45],
    font_size=9.2,
)

add_heading("Claims to avoid", 2)
add_bullets([
    "Do not say the agent is production ready. The full real model acceptance is incomplete.",
    "Do not present scripted 8 of 8 as LLM accuracy. It tests deterministic orchestration.",
    "Do not say confidence is a calibrated probability. It is a model estimate with a deterministic ceiling.",
    "Do not say the gateway is unprivileged. Its Docker group membership is effectively host root authority.",
    "Do not say Gemini keeps all data local. Selected redacted reasoning context goes to the provider.",
    "Do not say restart success proves recovery. Only the configured checks determine the current status, and those checks have known gaps.",
    "Do not claim the precise cause of the earlier Atlas failure. The logs showed server selection and TLS symptoms, but the ultimate cause was not established.",
])

add_heading("Final rehearsal checklist", 2)
add_bullets([
    "Give the 30 second pitch without looking at notes.",
    "Draw the architecture in under 90 seconds and mark trust boundaries.",
    "Explain the diagnostic flow and approval flow without skipping persistence.",
    "Tell three challenge stories with your personal actions and measured results.",
    "State the qwen2.5 and Gemini results with the correct limitations.",
    "Answer why no shell, why PostgreSQL plus Qdrant, why polling, and why verification.",
    "Say what is incomplete without becoming defensive or vague.",
    "End with the engineering lesson and a concrete next step.",
])

add_heading("Source basis", 1)
add_body("This guide is based on the repository and its README, architecture, security, deployment, evaluation, inventory, source, Compose files, tests, runbooks, and benchmark records. Measurements are current to project records dated 13 September 2026; recheck live deployment status before a later interview.")


# Footer with page number field
for sec in doc.sections:
    footer = sec.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    r = p.add_run("AI Home Lab Operator Interview Guide   |   ")
    r.font.name = "Aptos"
    r.font.size = Pt(8)
    r.font.color.rgb = MUTED
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = "PAGE"
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    r._r.append(fld_char1)
    r._r.append(instr_text)
    r._r.append(fld_char2)

# Keep tables and headings readable; set document metadata.
doc.core_properties.title = "AI Home Lab Operator Interview Guide"
doc.core_properties.subject = "Interview preparation for the HomeAiAgent project"
doc.core_properties.author = "Parth Mudgal"
doc.core_properties.keywords = "AI agent, home lab, FastAPI, Next.js, RAG, Qdrant, PostgreSQL, security, interview"
doc.core_properties.comments = "Prepared from the HomeAiAgent repository"

doc.save(OUT)
print(OUT)
