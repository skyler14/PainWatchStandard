const { onRequest } = require("firebase-functions/v2/https");
const { defineSecret } = require("firebase-functions/params");
const admin = require("firebase-admin");

admin.initializeApp();

const PROMPTOPINION_API_KEY = defineSecret("PROMPTOPINION_API_KEY");
const PROMPTOPINION_FHIR_BASE_URL = defineSecret("PROMPTOPINION_FHIR_BASE_URL");
const PAIN_MCP_API_KEY = defineSecret("PAIN_MCP_API_KEY");

const FHIR_EXTENSION = "ai.promptopinion/fhir-context";
const TOOL_NAMES = {
  start: "start_questionnaire",
  get: "get_questionnaire",
  submit: "submit_questionnaire_answers",
  continue: "continue_dialogue",
};

const GPM_ITEMS = [
  { id: "vigorous_activity", prompt: "pain with vigorous activities such as running, lifting, or strenuous sports", type: "yes_no" },
  { id: "moderate_activity", prompt: "pain with moderate activities such as pushing a vacuum, bowling, or golf", type: "yes_no" },
  { id: "groceries", prompt: "pain with lifting or carrying groceries", type: "yes_no" },
  { id: "stairs_flight", prompt: "pain climbing more than one flight of stairs", type: "yes_no" },
  { id: "few_steps", prompt: "pain climbing only a few steps", type: "yes_no" },
  { id: "walk_block_plus", prompt: "pain walking more than one block", type: "yes_no" },
  { id: "walk_block_or_less", prompt: "pain walking one block or less", type: "yes_no" },
  { id: "bathing_dressing", prompt: "pain with bathing or dressing", type: "yes_no" },
  { id: "reduced_time", prompt: "cutting down time spent on work or activities because of pain", type: "yes_no" },
  { id: "accomplish_less", prompt: "accomplishing less than wanted because of pain", type: "yes_no" },
  { id: "limited_activities", prompt: "limiting the kind of work or activities because of pain", type: "yes_no" },
  { id: "extra_effort", prompt: "needing extra effort for work or activities because of pain", type: "yes_no" },
  { id: "sleep_trouble", prompt: "trouble sleeping because of pain", type: "yes_no" },
  { id: "religious_activity", prompt: "pain preventing religious activities", type: "yes_no" },
  { id: "social_recreation", prompt: "pain preventing social or recreational activities", type: "yes_no" },
  { id: "transportation", prompt: "pain preventing travel or standard transportation", type: "yes_no" },
  { id: "fatigue", prompt: "pain making the patient feel fatigued or tired", type: "yes_no" },
  { id: "help_needed", prompt: "relying on family or friends for help because of pain", type: "yes_no" },
  { id: "pain_today_0_10", prompt: "pain severity today from zero to ten", type: "score_0_10" },
  { id: "pain_week_average_0_10", prompt: "average pain severity over the last seven days from zero to ten", type: "score_0_10" },
  { id: "never_goes_away", prompt: "pain that never completely goes away", type: "yes_no" },
  { id: "daily_pain", prompt: "pain every day", type: "yes_no" },
  { id: "several_times_week", prompt: "pain several times a week", type: "yes_no" },
  { id: "sad_depressed", prompt: "sadness or depression caused by pain over the last seven days", type: "yes_no" },
];

const GPM_CONTEXT =
  "Geriatric Pain Measure context: 24 fields. Eighteen functional/impact yes-no items, two 0-10 severity scores, three chronicity yes-no items, and one mood yes-no item. Score one point for each yes plus the two numeric 0-10 responses. Total range 0-42; adjusted score is total * 2.38 on a 0-100 scale. Adjusted <30 is mild, 30-69 moderate, >70 severe.";

const DOCTOR_A_GROUP_ID = "grp_doctor_a";
const DOCTOR_B_GROUP_ID = "grp_doctor_b";
const TEST_PATIENT_ID = "pat_test";

const registry = {
  doctors: [
    {
      id: "usr_doctor_a",
      groupId: DOCTOR_A_GROUP_ID,
      groupName: "Doctor A",
      name: "Doctor A",
      role: "Geriatric pain clinician",
      patientIds: [TEST_PATIENT_ID],
    },
    {
      id: "usr_doctor_b",
      groupId: DOCTOR_B_GROUP_ID,
      groupName: "Doctor B",
      name: "Doctor B",
      role: "Orthopedic reviewer",
      patientIds: [],
    },
  ],
  patients: [
    {
      id: TEST_PATIENT_ID,
      fhirPatientId: "pain-watch-pat-test",
      name: "Test Patient",
      age: 72,
      assignedGroupIds: [DOCTOR_A_GROUP_ID],
    },
  ],
};

const seedIncident = {
  id: "inc_watch_2026_05_11_001",
  patientId: TEST_PATIENT_ID,
  startedAt: "2026-05-11T09:42:18-07:00",
  durationMinutes: 8,
  sourceDevice: "PainThermometer Watch PoC",
  activation: {
    positiveWindows: 7,
    windowCount: 10,
    triggerScore: 0.78,
  },
  survey: {
    id: "survey_gpm_001",
    status: "completed",
    finalGpmScore: 26,
    adjustedGpmScore: 31,
    adjustmentReason:
      "Conversation added sleep interruption and help-needed context that was not captured in the first numeric answers.",
    questions: [
      {
        id: "what_happened",
        question: "What happened around when the pain started?",
        answer: "I stood up from the kitchen chair and felt my left knee tighten sharply.",
        confidence: 0.94,
      },
      {
        id: "location",
        question: "Where did you feel it most?",
        answer: "Left knee, mostly around the inside edge.",
        confidence: 0.91,
      },
      {
        id: "quality",
        question: "What did it feel like?",
        answer: "Sharp at first, then dull and throbbing.",
        confidence: 0.86,
      },
      {
        id: "gpm_today_0_10",
        question: "On a zero to ten scale, how bad is it today?",
        answer: "Six out of ten during the incident, four after resting.",
        confidence: 0.82,
      },
      {
        id: "sleep_trouble",
        question: "Has it been interfering with sleep?",
        answer: "Yes, I woke up twice last night when turning over.",
        confidence: 0.79,
      },
    ],
  },
  biometrics: [
    {
      metric: "Heart rate",
      sensor: "watch.hr",
      value: "104 bpm",
      zScore: 2.1,
      interpretation: "Elevated from session baseline",
    },
    {
      metric: "Respiratory rate",
      sensor: "watch.respiration",
      value: "22 rpm",
      zScore: 1.6,
      interpretation: "Moderately elevated",
    },
    {
      metric: "Wrist temperature",
      sensor: "watch.temperature",
      value: "+0.6 C",
      zScore: 1.2,
      interpretation: "Mild deviation",
    },
    {
      metric: "Motion magnitude",
      sensor: "watch.acc",
      value: "0.31 g",
      zScore: 2.7,
      interpretation: "Abrupt standing transition",
    },
    {
      metric: "SpO2",
      sensor: "watch.spo2",
      value: "No sample",
      zScore: 0,
      interpretation: "Dropout in incident window",
    },
  ],
  scores: [
    {
      name: "Pain likelihood",
      score: 78,
      scale: "0-100",
      severity: "high",
      note: "7 of 10 activation window crossed",
    },
    {
      name: "GPM raw",
      score: 26,
      scale: "0-42",
      severity: "moderate",
      note: "Completed survey total",
    },
    {
      name: "GPM adjusted",
      score: 31,
      scale: "0-100",
      severity: "moderate",
      note: "Adjusted after interview testimony",
    },
    {
      name: "Stress likelihood",
      score: 44,
      scale: "0-100",
      severity: "low",
      note: "Secondary signal, not primary incident driver",
    },
  ],
  chat: [
    {
      id: "msg_1",
      speaker: "assistant",
      time: "09:43",
      text: "I noticed a pain signal. What happened around when the pain started?",
    },
    {
      id: "msg_2",
      speaker: "patient",
      time: "09:44",
      text: "I stood up from the kitchen chair and my left knee tightened sharply.",
    },
    {
      id: "msg_3",
      speaker: "assistant",
      time: "09:44",
      text: "Where did you feel it most?",
    },
    {
      id: "msg_4",
      speaker: "patient",
      time: "09:45",
      text: "Inside edge of the left knee. It was sharp first, then a dull throb.",
    },
    {
      id: "msg_5",
      speaker: "assistant",
      time: "09:46",
      text: "Has it been interfering with sleep or making you need help?",
    },
    {
      id: "msg_6",
      speaker: "patient",
      time: "09:47",
      text: "Yes, sleep was bad last night. I also asked my daughter to help with groceries.",
    },
  ],
  summaries: [
    "Incident likely reflects a left-knee pain flare during sit-to-stand transition. Watch signal showed high pain likelihood with elevated HR and motion deviation.",
    "Survey adjustment increased because the interview added sleep disruption and help-needed impact, moving the session from borderline mild/moderate to moderate impact.",
  ],
};

function jsonRpc(id, result) {
  return { jsonrpc: "2.0", id: id ?? null, result };
}

function jsonRpcError(id, code, message) {
  return { jsonrpc: "2.0", id: id ?? null, error: { code, message } };
}

function sendJson(res, status, body) {
  res.status(status).set("Content-Type", "application/json").send(JSON.stringify(body));
}

function secretValue(secret) {
  try {
    return secret.value();
  } catch {
    return "";
  }
}

function authorizedByApiKey(req) {
  const expected = secretValue(PAIN_MCP_API_KEY);
  if (!expected) return true;
  const apiKey = req.get("x-api-key") || "";
  const bearer = req.get("authorization") || "";
  return apiKey === expected || bearer === `Bearer ${expected}`;
}

function groupCanReadPatient(groupId, patientId) {
  const patient = registry.patients.find((candidate) => candidate.id === patientId);
  return Boolean(patient?.assignedGroupIds.includes(groupId));
}

function buildGroupsPayload() {
  return registry.doctors.map((doctor) => ({
    id: doctor.groupId,
    name: doctor.groupName,
    clinician: {
      id: doctor.id,
      name: doctor.name,
      role: doctor.role,
    },
    patients: registry.patients
      .filter((patient) => doctor.patientIds.includes(patient.id))
      .map((patient) => ({
        id: patient.id,
        name: patient.name,
        age: patient.age,
        incidents: patient.id === TEST_PATIENT_ID ? [seedIncident] : [],
      })),
  }));
}

function fhirContext(req) {
  return {
    fhir_server_url: req.get("x-fhir-server-url") ?? null,
    fhir_access_token_present: Boolean(req.get("x-fhir-access-token")),
    patient_id: req.get("x-patient-id") ?? null,
  };
}

function nowIso() {
  return new Date().toISOString();
}

function stableSessionId(prefix = "pain-session") {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function completionFromAnswers(answers = {}) {
  const required = ["pain_location", "pain_intensity", "pain_duration", "trigger", "functional_impact"];
  const filled = required.filter((key) => {
    const value = answers[key];
    return value !== undefined && value !== null && String(value).trim() !== "";
  });
  return Math.min(1, filled.length / required.length);
}

function missingFields(answers = {}) {
  const answered = new Set(
    Object.entries(answers)
      .filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "")
      .map(([key]) => key),
  );
  return [
    "pain_location",
    "trigger",
    ...GPM_ITEMS.map((item) => item.id),
  ].filter((key) => !answered.has(key));
}

function nextQuestion(args = {}) {
  const answers = args.answers || {};
  const missing = missingFields(answers);
  if (missing.length === 0) {
    return "I have enough detail for the pain summary. Do you want to submit this session now?";
  }
  if (missing.includes("pain_location") && missing.includes("trigger")) {
    return "What happened, and where did you feel the pain most clearly?";
  }
  const nextItems = GPM_ITEMS.filter((item) => missing.includes(item.id)).slice(0, 3);
  if (nextItems.length === 0) {
    return "Can you tell me what triggered the pain and where it was strongest?";
  }
  return `To fill in the pain scale, tell me about ${nextItems.map((item) => item.prompt).join("; ")}.`;
}

function normalizeVitals(args = {}) {
  const incoming = args.vitals || args.buffer || args.score_history || [];
  return Array.isArray(incoming) ? incoming.slice(-100) : [];
}

function summarizeVitals(vitals) {
  const sensorCounts = new Map();
  for (const point of vitals) {
    const readings = point.readings || point.sensors || point.sensor_values || point;
    if (!readings || typeof readings !== "object") continue;
    for (const key of Object.keys(readings)) {
      if (["id", "captured_at", "timestamp", "time_text"].includes(key)) continue;
      sensorCounts.set(key, (sensorCounts.get(key) || 0) + 1);
    }
  }
  return {
    sample_count: vitals.length,
    max_samples: 100,
    sensors_present: Array.from(sensorCounts.entries()).map(([sensor, count]) => ({
      sensor,
      count,
      coverage_0_1: vitals.length ? count / vitals.length : 0,
    })),
  };
}

function inferAnswersFromResponse(responseText = "", existingAnswers = {}) {
  const text = String(responseText || "").toLowerCase();
  const inferred = { ...existingAnswers };
  if (!text.trim()) return inferred;

  inferred.free_response = responseText;
  if (!inferred.trigger) inferred.trigger = responseText;

  const locations = ["knee", "hip", "back", "shoulder", "neck", "hand", "wrist", "ankle", "foot", "leg", "arm", "head"];
  const location = locations.find((candidate) => text.includes(candidate));
  if (location && !inferred.pain_location) inferred.pain_location = location;

  const scoreMatch = text.match(/\b(10|[0-9])\b/);
  if (scoreMatch && !inferred.pain_today_0_10) inferred.pain_today_0_10 = scoreMatch[1];

  const keywordMap = [
    ["sleep_trouble", ["sleep", "slept", "woke", "night"]],
    ["help_needed", ["help", "daughter", "son", "family", "friend"]],
    ["groceries", ["grocer", "shopping", "bags"]],
    ["stairs_flight", ["stairs", "steps"]],
    ["walk_block_plus", ["walk", "walking"]],
    ["bathing_dressing", ["bath", "dress", "clothes"]],
    ["fatigue", ["tired", "fatigue", "exhausted"]],
    ["sad_depressed", ["sad", "depressed", "down"]],
    ["daily_pain", ["daily", "every day"]],
    ["never_goes_away", ["never goes away", "constant", "always"]],
  ];

  for (const [field, keywords] of keywordMap) {
    if (!inferred[field] && keywords.some((keyword) => text.includes(keyword))) {
      inferred[field] = "yes";
    }
  }

  return inferred;
}

function questionnairePayload(req, args = {}) {
  const answers = args.answers || {};
  const vitals = normalizeVitals(args);
  const requiredCount = GPM_ITEMS.length + 2;
  const completion = Math.min(1, Math.max(0, (requiredCount - missingFields(answers).length) / requiredCount));
  const painScore = Number(args.pain_score ?? args.score ?? 0.78);
  return {
    session_id: args.session_id || stableSessionId(),
    local_session_id: args.local_session_id || null,
    incident_id: args.incident_id || null,
    question: nextQuestion(args),
    completion_0_1: completion,
    can_submit: completion >= 0.8,
    missing_fields: missingFields(answers),
    gpm_context: GPM_CONTEXT,
    gpm_items: GPM_ITEMS,
    vitals_window: summarizeVitals(vitals),
    vitals: vitals,
    revised_scores: {
      score_name: "firebase_questionnaire_pain",
      pain_likelihood_0_1: painScore,
      pain_score_0_100: Math.round(painScore * 100),
      pain_detected: painScore >= 0.65,
      confidence_0_1: Math.max(0.35, Math.min(0.95, 0.55 + completion * 0.4)),
      quality_0_1: 0.82,
      stress_likelihood_0_1: 0.44,
      baseline_departure_0_1: Math.min(1, Math.max(0, painScore - 0.2)),
      model_version: "firebase-mcp-scaffold-v0",
    },
    prompt_opinion_context: fhirContext(req),
    generated_at: nowIso(),
  };
}

function toolsList() {
  return {
    tools: [
      {
        name: TOOL_NAMES.start,
        description: "Start a geriatric pain follow-up dialogue from a watch pain trigger and score buffer.",
        inputSchema: {
          type: "object",
          properties: {
            incident_id: { type: "string" },
            local_session_id: { type: "string" },
            pain_score: { type: "number" },
            score_history: { type: "array", items: { type: "object" } },
            buffer: {
              type: "array",
              maxItems: 100,
              items: { type: "object" },
              description: "Up to the past 100 watch vitals/sensor samples before the pain trigger.",
            },
            vitals: {
              type: "array",
              maxItems: 100,
              items: { type: "object" },
              description: "Alias for the up-to-100 historical vitals buffer.",
            },
          },
        },
      },
      {
        name: TOOL_NAMES.get,
        description: "Return the current questionnaire state for a pain follow-up session.",
        inputSchema: {
          type: "object",
          properties: { session_id: { type: "string" } },
        },
      },
      {
        name: TOOL_NAMES.continue,
        description: "Accept free testimony and return the next question plus completion status.",
        inputSchema: {
          type: "object",
          properties: {
            session_id: { type: "string" },
            response_text: { type: "string" },
            answers: { type: "object" },
            vitals: {
              type: "array",
              maxItems: 100,
              items: { type: "object" },
            },
          },
        },
      },
      {
        name: TOOL_NAMES.submit,
        description: "Submit the completed pain questionnaire dialogue.",
        inputSchema: {
          type: "object",
          properties: {
            session_id: { type: "string" },
            transcript: { type: "array", items: { type: "object" } },
            answers: { type: "object" },
          },
        },
      },
    ],
  };
}

function toolResult(req, name, args) {
  let payload;
  const enrichedArgs =
    name === TOOL_NAMES.continue
      ? {
          ...args,
          answers: inferAnswersFromResponse(args.response_text || args.response || "", args.answers || {}),
        }
      : args;
  if (name === TOOL_NAMES.submit) {
    payload = {
      ...questionnairePayload(req, enrichedArgs),
      submitted: true,
      summary: "Pain follow-up submitted with available quantitative scores and qualitative testimony.",
    };
  } else if ([TOOL_NAMES.start, TOOL_NAMES.get, TOOL_NAMES.continue].includes(name)) {
    payload = questionnairePayload(req, enrichedArgs);
  } else {
    return null;
  }

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(payload),
      },
    ],
    structuredContent: payload,
  };
}

function handleRpc(req, message) {
  const method = message.method;
  const id = message.id;

  if (method === "initialize") {
    return jsonRpc(id, {
      protocolVersion: message.params?.protocolVersion || "2025-06-18",
      capabilities: {
        tools: {},
        extensions: {
          [FHIR_EXTENSION]: {
            scopes: [
              { name: "patient/Patient.rs", required: false },
              { name: "patient/Observation.rs", required: false },
              { name: "patient/Observation.cu", required: false },
              { name: "patient/QuestionnaireResponse.rs", required: false },
              { name: "patient/QuestionnaireResponse.cu", required: false },
            ],
          },
        },
      },
      serverInfo: {
        name: "PainThermometer Questionnaire MCP",
        version: "0.1.0",
      },
      instructions:
        "Administers a short chronic-pain follow-up when a watch session reports sustained pain activation.",
    });
  }

  if (method === "tools/list") {
    return jsonRpc(id, toolsList());
  }

  if (method === "tools/call") {
    const name = message.params?.name;
    const args = message.params?.arguments || {};
    const result = toolResult(req, name, args);
    if (!result) {
      return jsonRpcError(id, -32602, `Unknown tool: ${name}`);
    }
    return jsonRpc(id, result);
  }

  if (method === "ping" || method === "notifications/initialized") {
    return id === undefined ? null : jsonRpc(id, {});
  }

  return jsonRpcError(id, -32601, `Unsupported method: ${method}`);
}

exports.mcp = onRequest(
  {
    region: "us-central1",
    timeoutSeconds: 60,
    cors: true,
    secrets: [PROMPTOPINION_API_KEY, PROMPTOPINION_FHIR_BASE_URL, PAIN_MCP_API_KEY],
  },
  async (req, res) => {
    if (!authorizedByApiKey(req)) {
      return sendJson(res, 401, { error: "unauthorized" });
    }

    if (req.method === "GET") {
      return sendJson(res, 200, {
        ok: true,
        endpoint: "/mcp",
        server: "PainThermometer Questionnaire MCP",
      });
    }

    if (req.method !== "POST") {
      return sendJson(res, 405, { error: "method_not_allowed" });
    }

    const body = typeof req.body === "string" ? JSON.parse(req.body) : req.body;
    const messages = Array.isArray(body) ? body : [body];
    const responses = messages.map((message) => handleRpc(req, message)).filter(Boolean);

    if (Array.isArray(body)) {
      return sendJson(res, 200, responses);
    }
    return sendJson(res, 200, responses[0] || {});
  },
);

exports.registry = onRequest(
  {
    region: "us-central1",
    timeoutSeconds: 30,
    cors: true,
    secrets: [PROMPTOPINION_API_KEY, PROMPTOPINION_FHIR_BASE_URL, PAIN_MCP_API_KEY],
  },
  async (req, res) => {
    if (req.method !== "GET") {
      return sendJson(res, 405, { error: "method_not_allowed" });
    }

    return sendJson(res, 200, {
      workspace: {
        fhirConfigured: Boolean(PROMPTOPINION_API_KEY.value() && PROMPTOPINION_FHIR_BASE_URL.value()),
      },
      groups: buildGroupsPayload(),
    });
  },
);

exports.authorizePatientAccess = onRequest(
  {
    region: "us-central1",
    timeoutSeconds: 30,
    cors: true,
    secrets: [PROMPTOPINION_API_KEY, PROMPTOPINION_FHIR_BASE_URL, PAIN_MCP_API_KEY],
  },
  async (req, res) => {
    if (req.method !== "POST") {
      return sendJson(res, 405, { error: "method_not_allowed" });
    }

    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    const groupId = body.clinician_group_id;
    const patientId = body.patient_id;
    const allowed = groupCanReadPatient(groupId, patientId);
    const requestPrefix = allowed ? "firebase_authz_req_a" : "firebase_authz_req_denied";

    return sendJson(res, allowed ? 200 : 403, {
      allowed,
      reason: allowed
        ? undefined
        : `permission_denied: clinician group ${groupId || "unknown"} is not assigned to patient ${patientId || "unknown"}`,
      requestId: `${requestPrefix}_${Date.now().toString(36)}`,
      checkedAt: nowIso(),
      source: "prompt_opinion_fhir",
      fhirPatientId: registry.patients.find((patient) => patient.id === patientId)?.fhirPatientId || patientId,
      policy: "registered_fhir_patient_scope",
    });
  },
);

exports.createPatient = onRequest(
  {
    region: "us-central1",
    timeoutSeconds: 30,
    cors: true,
    secrets: [PROMPTOPINION_API_KEY, PROMPTOPINION_FHIR_BASE_URL, PAIN_MCP_API_KEY],
  },
  async (req, res) => {
    if (!authorizedByApiKey(req)) {
      return sendJson(res, 401, { error: "unauthorized" });
    }

    if (req.method !== "POST") {
      return sendJson(res, 405, { error: "method_not_allowed" });
    }

    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    const patient = body.patient || {};
    const patientId = patient.id || TEST_PATIENT_ID;
    const knownPatient = registry.patients.find((candidate) => candidate.id === patientId);
    return sendJson(res, 200, {
      accepted: true,
      patient_id: patientId,
      fhir_patient_id: knownPatient?.fhirPatientId || `pain-watch-${String(patientId).replace(/_/g, "-")}`,
      doctor_group_id: DOCTOR_A_GROUP_ID,
      doctor_group_name: "Doctor A",
      generated_at: nowIso(),
    });
  },
);

exports.painTrigger = onRequest(
  {
    region: "us-central1",
    timeoutSeconds: 60,
    cors: true,
    secrets: [PROMPTOPINION_API_KEY, PROMPTOPINION_FHIR_BASE_URL, PAIN_MCP_API_KEY],
  },
  async (req, res) => {
    if (!authorizedByApiKey(req)) {
      return sendJson(res, 401, { error: "unauthorized" });
    }

    if (req.method !== "POST") {
      return sendJson(res, 405, { error: "method_not_allowed" });
    }

    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    const triggerScore = Number(body.score?.pain ?? body.activation?.triggerScore ?? 0.78);
    const payload = questionnairePayload(req, {
      incident_id: body.incident_id || stableSessionId("incident"),
      local_session_id: body.local_session_id,
      pain_score: triggerScore,
      deviation: body.score?.deviation ?? 0.12,
      buffer: body.buffer,
      score_history: body.score_history,
    });

    return sendJson(res, 200, {
      accepted: true,
      questionnaire_session_id: payload.session_id,
      question: {
        id: "pain_followup_opening",
        text: payload.question,
        input_type: "voice_text",
        target_fields: payload.missing_fields,
      },
      completion_0_1: payload.completion_0_1,
      can_submit: payload.can_submit,
      missing_fields: payload.missing_fields,
      revised_scores: payload.revised_scores,
      doctor_group_id: DOCTOR_A_GROUP_ID,
      patient_id: body.patient?.id || TEST_PATIENT_ID,
    });
  },
);

exports.continueQuestionnaire = onRequest(
  {
    region: "us-central1",
    timeoutSeconds: 60,
    cors: true,
    secrets: [PROMPTOPINION_API_KEY, PROMPTOPINION_FHIR_BASE_URL, PAIN_MCP_API_KEY],
  },
  async (req, res) => {
    if (!authorizedByApiKey(req)) {
      return sendJson(res, 401, { error: "unauthorized" });
    }

    if (req.method !== "POST") {
      return sendJson(res, 405, { error: "method_not_allowed" });
    }

    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    const answers = inferAnswersFromResponse(body.response, body.answers || {});
    const payload = questionnairePayload(req, {
      session_id: body.session_id,
      local_session_id: body.local_session_id,
      answers,
      pain_score: body.pain_score,
    });

    return sendJson(res, 200, {
      accepted: true,
      questionnaire_session_id: payload.session_id,
      question: {
        id: "pain_followup_next",
        text: payload.question,
        input_type: "voice_text",
        target_fields: payload.missing_fields,
      },
      completion_0_1: payload.completion_0_1,
      can_submit: payload.can_submit,
      missing_fields: payload.missing_fields,
      revised_scores: payload.revised_scores,
    });
  },
);

exports.submitQuestionnaire = onRequest(
  {
    region: "us-central1",
    timeoutSeconds: 60,
    cors: true,
    secrets: [PROMPTOPINION_API_KEY, PROMPTOPINION_FHIR_BASE_URL, PAIN_MCP_API_KEY],
  },
  async (req, res) => {
    if (!authorizedByApiKey(req)) {
      return sendJson(res, 401, { error: "unauthorized" });
    }

    if (req.method !== "POST") {
      return sendJson(res, 405, { error: "method_not_allowed" });
    }

    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    return sendJson(res, 200, {
      accepted: true,
      completed: true,
      completion_0_1: 1,
      questionnaire_session_id: body.session_id || stableSessionId(),
      submitted: true,
      summary: "Pain follow-up submitted with available quantitative scores and qualitative testimony.",
      generated_at: nowIso(),
    });
  },
);
