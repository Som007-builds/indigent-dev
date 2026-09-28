/**
 * DEAD CODE — DO NOT IMPORT.
 *
 * Nothing in the application references this module (verified by grep across
 * app/, components/ and lib/ on 2026-09-27). It previously exported two objects that
 * were actively harmful and which have now been deleted:
 *
 *   - `defaultSovereigntyMetrics` — asserted `isAirGapped: true` with invented
 *     counters (184 local requests, 42 firewall rules) and a fabricated blocked
 *     packet to 104.244.42.1. It seeded the global header, which therefore showed a
 *     green pulsing AIR-GAPPED badge before the backend had ever been contacted.
 *   - `mockModelRegistry` — four models branded "OpenAI on Groq LPU" and friends,
 *     substituted whenever /api/models returned an empty list or any error.
 *
 * What remains are four static scenario fixtures. They are canned task transcripts
 * with invented engineering values (3.8 mm wall thickness, 4.5 mm threshold,
 * "SOP-ENG-042 Section 4.2"). They are retained only as reference material and must
 * not be wired into a demo path: a mock toggle is explicitly forbidden in
 * Frontend-fix.md ("Do not do"). Delete this file once the fixtures have served
 * their purpose.
 *
 * OWNER DECISION 2026-09-28: keep this file. It is deliberately retained as a
 * design/demo fixture, so the "do not import" warning above stays -- but it is a
 * choice, not an oversight, and it is no longer treated as a candidate for deletion
 * in the Frontend-fix.md cleanup items.
 *
 * What this means concretely: every number in this file is invented, and none of it
 * came from the backend. `taskType` on the fixtures is `TaskType | null` because G7
 * defines exactly three task types; `scenario3_SovereigntyProof.taskType` was
 * "sovereignty_proof", which is a `scenarioKey` -- a UI demo-scenario label -- and was
 * being carried in a field the backend populates. It is null here for the same reason
 * it is null in `workbench-context.tsx` at INTAKE: not classified.
 */

import { TaskState } from "@/types/workbench"
import { pidDiagramsList } from "@/lib/pid-data"


export const scenario1_Inspection: TaskState = {
  taskId: "task-insp-001",
  scenarioKey: "inspection_report",
  scenarioTitle: "Pipe Safety & Thickness Inspection Check",
  userPrompt: "Please check this ultrasonic measurement scan for crude oil pipe line L-2041. Compare it against our official company safety rules (SOPs) and prepare an official approval note and calculation sheet for my signature.",
  taskType: "inspection",
  currentState: "APPROVAL",
  requiresApproval: true,
  approvalStatus: "pending",
  createdAt: "Today at 08:20 PM",
  updatedAt: "Today at 08:20 PM",
  routing: {
    modelId: "general-reasoning",
    modelName: "DeepSeek-R1 Distill Llama (70B)",
    role: "reasoning",
    reason: "SOP Verification & Deterministic Compliance Reasoning (UT Scan Attached)",
    isResident: true,
    contextLength: "128,000 tokens",
    vramUsageGb: 40.5,
  },
  steps: [
    {
      stepId: "step-1",
      state: "INTAKE",
      title: "Reading the Uploaded Scan",
      description: "Successfully read 2 scanned pages from `MRPL_UT_Thickness_L2041_Scan.pdf` using private on-device scanner.",
      durationMs: 420,
      status: "passed",
      timestamp: "08:20 PM",
    },
    {
      stepId: "step-2",
      state: "TOOL",
      title: "Extracted Key Pipe Information",
      description: "Found the key measurement on the scan: Pipe Line L-2041 has an elbow wall thickness of 3.8 mm (original was 9.5 mm).",
      durationMs: 840,
      status: "passed",
      timestamp: "08:20 PM",
    },
    {
      stepId: "step-3",
      state: "RETRIEVE",
      title: "Matched Official Company Safety Rules (SOP-ENG-042)",
      description: "Found the relevant rule in Section 4.2 (Page 17) of the refinery safety guidelines: The absolute minimum safe wall thickness for this line is 4.5 mm.",
      durationMs: 310,
      status: "passed",
      timestamp: "08:20 PM",
    },
    {
      stepId: "step-4",
      state: "TOOL",
      title: "Calculated Safety Margin Check",
      description: "Calculation Check: Measured 3.8 mm is LESS than the required safe limit of 4.5 mm (0.7 mm below minimum). The pipe has thinned too much and must be replaced.",
      durationMs: 45,
      status: "passed",
      timestamp: "08:20 PM",
    },
    {
      stepId: "step-5",
      state: "ARTIFACT",
      title: "Prepared Ready-to-Sign Word & Excel Documents",
      description: "Created `approval_note_L2041.docx` (Official Note) and `calculation_sheet_L2041.xlsx` (Step-by-step arithmetic proof) for your review.",
      durationMs: 650,
      status: "passed",
      timestamp: "08:20 PM",
    },
    {
      stepId: "step-6",
      state: "APPROVAL",
      title: "Waiting for Your Sign-off",
      description: "Everything is ready. The assistant has paused and is waiting for the authorized officer to click Approve or Request Changes.",
      durationMs: 0,
      status: "running",
      timestamp: "08:20 PM",
    },
  ],
  citations: [
    {
      id: "cit-1",
      source: "SOP-ENG-042",
      title: "Refinery Piping Safety & Retirement Thickness Standards",
      section: "Section 4.2",
      page: 17,
      snippet: "For hydrocarbon overhead pipes, the minimum allowable safe wall thickness is 4.5 mm. Any measurement below 4.5 mm requires immediate replacement to prevent leaks.",
      confidence: 0.98,
      matchedClause: "Rule 4.2.1 - Safe Operating Limit",
      toleranceRequired: "Minimum Safe Limit: 4.5 mm (Current Reading: 3.8 mm — 0.7 mm Too Thin)",
    },
    {
      id: "cit-2",
      source: "MRPL Safety Policy 2024",
      title: "Standard Procedure for Pipe Inspection Findings",
      section: "Section 7.1",
      page: 34,
      snippet: "When a pipe wall measurement falls below allowable safety limits, an official replacement notice must be generated and signed by the responsible engineer.",
      confidence: 0.92,
      matchedClause: "Immediate Action Requirement",
      toleranceRequired: "Replacement Notice Required",
    },
  ],
  artifacts: [
    {
      id: "art-1",
      filename: "approval_note_L2041.docx",
      fileType: "docx",
      fileSizeFormatted: "48 KB",
      downloadUrl: "/api/artifacts/art-1",
      validationStatus: "validated",
      validationMessage: "Ready for printing or signature. Includes summary, safety rule reference, and signature line.",
      summary: "Official company note explaining why this pipe failed safety limits and recommending prompt replacement.",
      generatedAt: "Today at 08:20 PM",
    },
    {
      id: "art-2",
      filename: "calculation_sheet_L2041.xlsx",
      fileType: "xlsx",
      fileSizeFormatted: "26 KB",
      downloadUrl: "/api/artifacts/art-2",
      validationStatus: "validated",
      validationMessage: "Standard Excel spreadsheet with clear step-by-step numbers and formulas.",
      summary: "Step-by-step arithmetic check spreadsheet proving the 3.8 mm vs 4.5 mm safety threshold calculation.",
      generatedAt: "Today at 08:20 PM",
    },
  ],
  approvalData: {
    recommendation: "REPLACE PIPE SPOOL — FAILED MINIMUM SAFETY THICKNESS",
    rationale: "The measured pipe wall thickness is 3.8 mm. This is below the mandatory safety threshold of 4.5 mm set by company rule SOP-ENG-042 Section 4.2. To ensure complete safety and prevent leaks, this section should be replaced.",
    standardRef: "Company Safety Manual: SOP-ENG-042 (Section 4.2, Page 17)",
    measuredValue: "3.8 mm (Too Thin)",
    thresholdValue: "4.5 mm (Minimum Required)",
    complianceStatus: "REJECT",
    deliverablesPending: ["Official Note (Word Doc)", "Math Check (Excel Sheet)"],
    reviewerRoleRequired: "Senior Plant / Safety Engineer",
  },
}

export const scenario2_CodeRepair: TaskState = {
  taskId: "task-code-002",
  scenarioKey: "sandbox_repair",
  scenarioTitle: "Engineering Flow Formula & Automatic Error Check",
  userPrompt: "Create a simple calculation program to verify orifice flow rates according to standard formulas, and make sure it automatically checks for errors.",
  taskType: "coding",
  currentState: "COMPLETE",
  requiresApproval: false,
  approvalStatus: "approved",
  createdAt: "Today at 07:40 PM",
  updatedAt: "Today at 07:40 PM",
  routing: {
    modelId: "coding",
    modelName: "Qwen 2.5 Coder (72B)",
    role: "coding",
    reason: "Sandboxed Python Execution & Mathematical Flow Verification",
    isResident: true,
    contextLength: "128,000 tokens",
    vramUsageGb: 41.2,
  },
  steps: [
    {
      stepId: "step-1",
      state: "INTAKE",
      title: "Understood Flow Calculation Request",
      description: "Prepared formula to calculate liquid flow through an orifice meter according to ISO standard guidelines.",
      durationMs: 180,
      status: "passed",
      timestamp: "07:40 PM",
    },
    {
      stepId: "step-2",
      state: "TOOL",
      title: "Wrote Calculation Code & Test Cases",
      description: "Generated 140 lines of verified calculation code along with 6 automated checks to test common and extreme values.",
      durationMs: 950,
      status: "passed",
      timestamp: "07:40 PM",
    },
    {
      stepId: "step-3",
      state: "TOOL",
      title: "Tested Calculations in Private Sandbox",
      description: "Ran the calculation test. An edge case was caught: when pipe and orifice sizes are equal, the formula produced an error.",
      durationMs: 1200,
      status: "failed",
      timestamp: "07:40 PM",
    },
    {
      stepId: "step-4",
      state: "REPAIR",
      title: "AI Automatically Corrected the Formula",
      description: "The AI assistant diagnosed the issue and added a protective rule to prevent division by zero, then re-tested the code.",
      durationMs: 740,
      status: "repaired",
      timestamp: "07:40 PM",
    },
    {
      stepId: "step-5",
      state: "VERIFY",
      title: "All 6 Verification Checks Passed",
      description: "Re-ran all tests in the private sandbox. All 6 mathematical tests passed with 100% accuracy.",
      durationMs: 890,
      status: "passed",
      timestamp: "07:40 PM",
    },
    {
      stepId: "step-6",
      state: "COMPLETE",
      title: "Ready for Download",
      description: "Calculation module is fully verified and packaged for your engineering team.",
      durationMs: 50,
      status: "passed",
      timestamp: "07:40 PM",
    },
  ],
  citations: [],
  artifacts: [
    {
      id: "art-code-1",
      filename: "orifice_calc.py",
      fileType: "py",
      fileSizeFormatted: "8.4 KB",
      downloadUrl: "/api/artifacts/art-code-1",
      validationStatus: "validated",
      validationMessage: "Passed all 6 automated mathematical checks with zero errors.",
      summary: "Verified program that calculates pipe flow rates and checks for invalid input numbers.",
      generatedAt: "Today at 07:40 PM",
    },
  ],
}

export const scenario3_SovereigntyProof: TaskState = {
  taskId: "task-sec-003",
  scenarioKey: "sovereignty_proof",
  scenarioTitle: "Privacy & Offline Security Verification Test",
  userPrompt: "Demonstrate that no data can ever leave this computer by testing our built-in security shield against an attempted outside connection.",
  // Not a task type. G7 enumerates three (inspection, coding, pid_analysis) and this
  // fixture never went through CLASSIFY, so the honest value is null. "sovereignty_proof"
  // is a scenarioKey, one layer up, and does not belong in a task-type field.
  taskType: null,
  currentState: "COMPLETE",
  requiresApproval: false,
  approvalStatus: "approved",
  createdAt: "Today at 08:10 PM",
  updatedAt: "Today at 08:10 PM",
  routing: {
    modelId: "general-reasoning",
    modelName: "DeepSeek-R1 Distill Llama (70B)",
    role: "reasoning",
    reason: "Offline Security Diagnostics & Egress Verification Monitor",
    isResident: true,
    contextLength: "128,000 tokens",
    vramUsageGb: 40.5,
  },
  steps: [
    {
      stepId: "step-1",
      state: "INTAKE",
      title: "Started Offline Privacy Test",
      description: "Activated security monitor to observe any outgoing communication attempts.",
      durationMs: 80,
      status: "passed",
      timestamp: "08:10 PM",
    },
    {
      stepId: "step-2",
      state: "TOOL",
      title: "Simulated an Outside Connection Attempt",
      description: "Deliberately attempted to send a request to a public cloud website from inside the sandbox.",
      durationMs: 2005,
      status: "passed",
      timestamp: "08:10 PM",
    },
    {
      stepId: "step-3",
      state: "VERIFY",
      title: "Security Shield Blocked the Request Instantly",
      description: "The built-in firewall immediately dropped the outgoing packet. Zero bytes were sent outside. Full privacy verified.",
      durationMs: 120,
      status: "passed",
      timestamp: "08:10 PM",
    },
  ],
  citations: [],
  artifacts: [
    {
      id: "art-sec-1",
      filename: "privacy_security_receipt.json",
      fileType: "json",
      fileSizeFormatted: "4.1 KB",
      downloadUrl: "/api/artifacts/art-sec-1",
      validationStatus: "validated",
      validationMessage: "Confirmed: 0 bytes left this computer during the entire test.",
      summary: "Security certificate proving that all operations took place 100% locally and privately.",
      generatedAt: "Today at 08:10 PM",
    },
  ],
}

export const scenario4_PIDAnalysis: TaskState = {
  taskId: "task-pid-004",
  scenarioKey: "pid_analysis",
  scenarioTitle: "Plant Flow Diagram (P&ID) Visual Explanation",
  userPrompt: "Look at the attached plant diagram for our crude distillation column C-101. Identify the tanks, pumps, and valves, and explain in simple words how the oil flows through the system.",
  taskType: "pid_analysis",
  currentState: "COMPLETE",
  requiresApproval: false,
  approvalStatus: "approved",
  createdAt: "Today at 07:15 PM",
  updatedAt: "Today at 07:16 PM",
  routing: {
    modelId: "vision",
    modelName: "Qwen 2.5-VL (72B)",
    role: "vision",
    reason: "ISA-5.1 P&ID Topology Parsing & High-Resolution Tag Tracing",
    isResident: true,
    contextLength: "64,000 tokens",
    vramUsageGb: 42.5,
  },
  steps: [
    {
      stepId: "step-1",
      state: "INTAKE",
      title: "Loaded Plant Diagram & Blueprint",
      description: "Loaded high-clarity plant drawing `MRPL_PID_C101_Distillation.png` and ISA-5.1 symbol set.",
      durationMs: 310,
      status: "passed",
      timestamp: "07:15 PM",
    },
    {
      stepId: "step-2",
      state: "TOOL",
      title: "Extracted Equipment Tags & Bounding Boxes",
      description: "Located 9 key components: Surge Drum (V-102), Feed Pump (P-101A), Pressure Sensor (PT-301), Charge Valve (FCV-101), Distillation Column (C-101), Condenser (E-101), Reflux Drum (V-103), Reflux Pump (P-102), and Reflux Valve (FCV-102).",
      durationMs: 820,
      status: "passed",
      timestamp: "07:15 PM",
    },
    {
      stepId: "step-3",
      state: "TOOL",
      title: "Traced Piping Connectivity & Flow Loops",
      description: "Mapped process headers: 14\" crude charge line, 20\" overhead vapor line, 8\" reflux return, and instrument signal loop 301.",
      durationMs: 1140,
      status: "passed",
      timestamp: "07:15 PM",
    },
    {
      stepId: "step-4",
      state: "VERIFY",
      title: "Generated Process Flow Summary & Graph JSON",
      description: "Constructed structured connectivity graph and plain English sequence for engineering review.",
      durationMs: 1450,
      status: "passed",
      timestamp: "07:15 PM",
    },
  ],
  citations: [],
  artifacts: [
    {
      id: "art-pid-1",
      filename: "plant_equipment_map.json",
      fileType: "json",
      fileSizeFormatted: "14 KB",
      downloadUrl: "/api/artifacts/art-pid-1",
      validationStatus: "validated",
      validationMessage: "Identified 9 equipment tags and 9 connecting process lines.",
      summary: "Structured JSON connectivity map of all vessels, valves, and pumps on the P&ID diagram.",
      generatedAt: "Today at 07:15 PM",
    },
  ],
  pidGraph: pidDiagramsList[0],
}

export const mockScenariosMap: Record<string, TaskState> = {
  inspection_report: scenario1_Inspection,
  sandbox_repair: scenario2_CodeRepair,
  sovereignty_proof: scenario3_SovereigntyProof,
  pid_analysis: scenario4_PIDAnalysis,
}
