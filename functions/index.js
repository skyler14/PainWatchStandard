const { onRequest } = require("firebase-functions/v2/https");
const { defineSecret } = require("firebase-functions/params");
const admin = require("firebase-admin");

admin.initializeApp();
const db = admin.firestore();

const PROMPTOPINION_API_KEY = defineSecret("PROMPTOPINION_API_KEY");
const PROMPTOPINION_FHIR_BASE_URL = defineSecret("PROMPTOPINION_FHIR_BASE_URL");
const PAIN_MCP_API_KEY = defineSecret("PAIN_MCP_API_KEY");

const FHIR_EXTENSION = "ai.promptopinion/fhir-context";
const TOOL_NAMES = {
  start: "start_questionnaire",
  get: "get_questionnaire",
  submit: "submit_questionnaire_answers",
  continue: "continue_dialogue",
  listPatients: "list_patients",
  summarizePatientHistory: "summarize_patient_history",
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

const seedSession = {
  ...seedIncident,
  sessionId: seedIncident.id,
  sessionType: "pain_incident",
  patientId: TEST_PATIENT_ID,
  clinicianGroupId: DOCTOR_A_GROUP_ID,
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

function cleanForFirestore(value) {
  if (Array.isArray(value)) {
    return value.map(cleanForFirestore);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([, entryValue]) => entryValue !== undefined)
        .map(([key, entryValue]) => [key, cleanForFirestore(entryValue)]),
    );
  }
  return value;
}

function safeId(value, prefix = "id") {
  return String(value || `${prefix}-${Date.now().toString(36)}`)
    .trim()
    .replace(/[^A-Za-z0-9.-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 120) || `${prefix}-${Date.now().toString(36)}`;
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

function normalizeDoctorGroupId(value) {
  if (!value) return DOCTOR_A_GROUP_ID;
  const normalized = String(value).toLowerCase().replaceAll("-", "_");
  if (normalized === "doctor_a" || normalized === "grp_doctor_a" || normalized === "doctora") {
    return DOCTOR_A_GROUP_ID;
  }
  if (normalized === "doctor_b" || normalized === "grp_doctor_b" || normalized === "doctorb") {
    return DOCTOR_B_GROUP_ID;
  }
  return String(value);
}

async function loadPatientsFromFirestore() {
  const snapshot = await db.collection("patients").orderBy("createdAt", "desc").get();
  return snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
}

async function loadSessionsForPatient(patientId) {
  const snapshot = await db
    .collection("patients")
    .doc(patientId)
    .collection("sessions")
    .orderBy("startedAt", "desc")
    .limit(50)
    .get();
  return snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
}

async function loadPatient(patientId) {
  try {
    const snapshot = await db.collection("patients").doc(patientId).get();
    return snapshot.exists ? { id: snapshot.id, ...snapshot.data() } : null;
  } catch (error) {
    console.warn("patient_firestore_doc_read_failed", error.message);
    return null;
  }
}

async function loadAllPatients() {
  try {
    const patients = await loadPatientsFromFirestore();
    if (patients.length) return patients;
    await ensureSeedData();
    const seededPatients = await loadPatientsFromFirestore();
    if (seededPatients.length) return seededPatients;
  } catch (error) {
    console.warn("patient_firestore_read_failed", error.message);
  }
  return registry.patients;
}

async function groupCanReadPatient(groupId, patientId) {
  const patients = await loadAllPatients();
  const patient = patients.find((candidate) => candidate.id === patientId);
  return Boolean(patient?.assignedGroupIds.includes(groupId));
}

async function buildGroupsPayload() {
  const patients = await loadAllPatients();
  const patientsWithSessions = await Promise.all(
    patients.map(async (patient) => {
      let sessions = [];
      try {
        sessions = await loadSessionsForPatient(patient.id);
      } catch (error) {
        console.warn("session_firestore_read_failed", error.message);
      }
      if (!sessions.length && patient.id === TEST_PATIENT_ID) {
        sessions = [seedSession];
      }
      return {
        ...patient,
        sessions,
        incidents: sessions,
      };
    }),
  );

  return registry.doctors.map((doctor) => ({
    id: doctor.groupId,
    name: doctor.groupName,
    clinician: {
      id: doctor.id,
      name: doctor.name,
      role: doctor.role,
    },
    patients: patientsWithSessions
      .filter((patient) => patient.assignedGroupIds?.includes(doctor.groupId))
      .map((patient) => ({
        id: patient.id,
        fhirPatientId: patient.fhirPatientId,
        name: patient.name,
        age: patient.age ?? null,
        assignedGroupIds: patient.assignedGroupIds,
        sessions: patient.sessions,
        incidents: patient.incidents,
      })),
  }));
}

async function patientHistory(patientId) {
  const patients = await loadAllPatients();
  const patient = patients.find((candidate) => candidate.id === patientId);
  if (!patient) return null;
  let sessions = [];
  try {
    sessions = await loadSessionsForPatient(patientId);
  } catch (error) {
    console.warn("history_session_read_failed", error.message);
  }
  if (!sessions.length && patient.id === TEST_PATIENT_ID) {
    sessions = [seedSession];
  }
  return {
    ...patient,
    sessions,
    incidents: sessions,
  };
}

async function summarizePatient(patientId) {
  const patient = await patientHistory(patientId);
  if (!patient) {
    return {
      patient_id: patientId,
      summary: "No patient record was found for this clinician context.",
      incidents: [],
    };
  }
  const sessions = patient.sessions || [];
  const highPainCount = sessions.filter((session) => session.activation?.triggerScore >= 0.65).length;
  const adjustedScores = sessions
    .map((session) => session.survey?.adjustedGpmScore)
    .filter((score) => typeof score === "number");
  const maxAdjusted = adjustedScores.length ? Math.max(...adjustedScores) : null;
  return {
    patient_id: patient.id,
    fhir_patient_id: patient.fhirPatientId,
    patient_name: patient.name,
    session_count: sessions.length,
    incident_count: sessions.length,
    high_pain_incident_count: highPainCount,
    max_adjusted_gpm_score: maxAdjusted,
    latest_session_at: sessions[0]?.startedAt ?? null,
    latest_incident_at: sessions[0]?.startedAt ?? null,
    summary:
      sessions.length === 0
        ? `${patient.name} has no recorded PainThermometer incidents yet.`
        : `${patient.name} has ${sessions.length} recorded PainThermometer session. The latest event crossed the sustained pain threshold at ${Math.round((sessions[0].activation?.triggerScore || 0) * 100)}% with adjusted GPM ${sessions[0].survey?.adjustedGpmScore ?? "unknown"}. Interview notes emphasize ${sessions[0].survey?.adjustmentReason || "limited follow-up context"}`,
    sessions,
    incidents: sessions,
  };
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
      {
        name: TOOL_NAMES.listPatients,
        description: "List patients visible to a clinician group for use in Prompt Opinion chat patient pickers.",
        inputSchema: {
          type: "object",
          properties: {
            clinician_group_id: { type: "string", description: "Clinician group id, for example grp_doctor_a." },
          },
        },
      },
      {
        name: TOOL_NAMES.summarizePatientHistory,
        description: "Summarize all known PainThermometer incidents, scores, surveys, and transcript notes for a visible patient.",
        inputSchema: {
          type: "object",
          required: ["patient_id"],
          properties: {
            clinician_group_id: { type: "string", description: "Clinician group id, for example grp_doctor_a." },
            patient_id: { type: "string", description: "Patient id returned by list_patients." },
          },
        },
      },
    ],
  };
}

async function visiblePatientsForGroup(groupId) {
  const patients = await loadAllPatients();
  const visible = [];
  for (const patient of patients) {
    if (!groupId || (await groupCanReadPatient(groupId, patient.id))) {
      visible.push(patient);
    }
  }
  return visible.map((patient) => ({
      id: patient.id,
      fhir_patient_id: patient.fhirPatientId,
      name: patient.name,
      age: patient.age ?? null,
      session_count: patient.sessionCount ?? (patient.id === TEST_PATIENT_ID ? 1 : 0),
      incident_count: patient.sessionCount ?? (patient.id === TEST_PATIENT_ID ? 1 : 0),
    }));
}

async function ensureSeedData() {
  const patientRef = db.collection("patients").doc(TEST_PATIENT_ID);
  const patientSnapshot = await patientRef.get();
  if (!patientSnapshot.exists) {
    await patientRef.set(
      cleanForFirestore({
        ...registry.patients[0],
        createdAt: "2026-05-11T09:00:00-07:00",
        updatedAt: nowIso(),
        source: "seed",
        sessionCount: 1,
      }),
      { merge: true },
    );
  }

  const sessionRef = patientRef.collection("sessions").doc(seedSession.sessionId);
  const sessionSnapshot = await sessionRef.get();
  if (!sessionSnapshot.exists) {
    await sessionRef.set(cleanForFirestore(seedSession), { merge: true });
  }
}

function patientFromWatchPayload(body) {
  const incoming = body.patient || {};
  const id = safeId(incoming.id || body.patient_id || TEST_PATIENT_ID, "patient");
  const firstName = incoming.first_name || incoming.firstName || incoming.given || "Watch";
  const lastName = incoming.last_name || incoming.lastName || incoming.family || "Patient";
  const name = incoming.display_name || incoming.displayName || `${firstName} ${lastName}`.trim();
  const doctorGroupId = normalizeDoctorGroupId(
    body.doctor_group_id || body.doctorGroupID || incoming.doctor_group_id || incoming.doctorGroupID,
  );
  return {
    id,
    fhirPatientId: safeId(`pain-watch-${id}`, "fhir-patient"),
    name,
    firstName,
    lastName,
    age: incoming.age ?? null,
    createdAt: incoming.created_at || incoming.createdAt || body.created_at || nowIso(),
    updatedAt: nowIso(),
    source: body.source || "PainThermometerWatchApp",
    assignedGroupIds: [doctorGroupId],
    primaryGroupId: doctorGroupId,
    deviceIds: body.device_id ? [String(body.device_id)] : [],
    sessionCount: 0,
  };
}

function fhirPatientResource(patient) {
  return {
    resourceType: "Patient",
    active: true,
    identifier: [
      {
        system: "https://pain-thermometer-po.web.app/patient-id",
        value: patient.id,
      },
    ],
    name: [
      {
        use: "usual",
        text: patient.name,
        given: patient.firstName ? [patient.firstName] : undefined,
        family: patient.lastName || undefined,
      },
    ],
    meta: {
      tag: [
        {
          system: "https://pain-thermometer-po.web.app",
          code: "painthermometer",
          display: "PainThermometer",
        },
      ],
    },
  };
}

function fhirPatientReference(patientId, fhirPatientId) {
  return {
    reference: `Patient/${fhirPatientId || patientId}`,
    identifier: {
      system: "https://pain-thermometer-po.web.app/patient-id",
      value: patientId,
    },
  };
}

function fhirLocalIdentifier(type, value) {
  return {
    system: `https://pain-thermometer-po.web.app/${type}`,
    value,
  };
}

function fhirPainEncounterResource(patientId, fhirPatientId, session) {
  return {
    resourceType: "Encounter",
    status: "in-progress",
    class: {
      system: "http://terminology.hl7.org/CodeSystem/v3-ActCode",
      code: "AMB",
      display: "ambulatory",
    },
    identifier: [fhirLocalIdentifier("pain-session-id", session.sessionId)],
    subject: fhirPatientReference(patientId, fhirPatientId),
    period: {
      start: session.startedAt,
    },
    type: [
      {
        coding: [
          {
            system: "https://pain-thermometer-po.web.app/session-type",
            code: "watch-pain-incident",
            display: "PainThermometer watch pain incident",
          },
        ],
        text: "PainThermometer watch pain incident",
      },
    ],
  };
}

function fhirObservationResource(patientId, fhirPatientId, encounterId, session, options) {
  const value = Number(options.value);
  return {
    resourceType: "Observation",
    status: "preliminary",
    identifier: [fhirLocalIdentifier(options.identifierType || "observation-id", `${session.sessionId}-${options.code}`)],
    category: [
      {
        coding: [
          {
            system: "http://terminology.hl7.org/CodeSystem/observation-category",
            code: options.category || "survey",
            display: options.categoryDisplay || "Survey",
          },
        ],
      },
    ],
    code: {
      coding: [
        {
          system: options.system || "https://pain-thermometer-po.web.app/observation-code",
          code: options.code,
          display: options.display,
        },
      ],
      text: options.display,
    },
    subject: fhirPatientReference(patientId, fhirPatientId),
    encounter: encounterId ? { reference: `Encounter/${encounterId}` } : undefined,
    effectiveDateTime: session.startedAt,
    valueQuantity: Number.isFinite(value)
      ? {
          value,
          unit: options.unit || "1",
          system: options.unitSystem || "http://unitsofmeasure.org",
          code: options.unitCode || "1",
        }
      : undefined,
    note: options.note ? [{ text: options.note }] : undefined,
  };
}

function fhirQuestionnaireResponseResource(patientId, fhirPatientId, encounterId, session) {
  return {
    resourceType: "QuestionnaireResponse",
    status: session.survey?.status === "completed" ? "completed" : "in-progress",
    subject: fhirPatientReference(patientId, fhirPatientId),
    authored: session.startedAt,
    item: [
      {
        linkId: "opening_prompt",
        text: "Initial conversational pain follow-up prompt",
        answer: [{ valueString: session.chat?.[0]?.text || "What happened, and where did you feel the pain most clearly?" }],
      },
    ],
  };
}

function fhirDocumentReferenceResource(patientId, fhirPatientId, encounterId, session) {
  const summary = (session.summaries || []).join("\n");
  return {
    resourceType: "DocumentReference",
    status: "current",
    identifier: [fhirLocalIdentifier("pain-session-summary-id", session.sessionId)],
    subject: fhirPatientReference(patientId, fhirPatientId),
    context: encounterId ? { encounter: [{ reference: `Encounter/${encounterId}` }] } : undefined,
    date: nowIso(),
    type: {
      coding: [
        {
          system: "https://pain-thermometer-po.web.app/document-type",
          code: "pain-session-summary",
          display: "PainThermometer session summary",
        },
      ],
      text: "PainThermometer session summary",
    },
    content: [
      {
        attachment: {
          contentType: "text/plain",
          data: Buffer.from(summary || "PainThermometer session started.").toString("base64"),
          title: `PainThermometer session ${session.sessionId}`,
        },
      },
    ],
  };
}

async function persistPainSessionToFhir(patientId, fhirPatientId, session) {
  const result = {
    ok: false,
    encounterId: null,
    observationIds: [],
    questionnaireResponseId: null,
    documentReferenceId: null,
    errors: [],
  };
  try {
    const encounter = await fhirPost("Encounter", fhirPainEncounterResource(patientId, fhirPatientId, session));
    if (encounter.ok) {
      result.encounterId = encounter.id;
    } else {
      result.errors.push({ resource: "Encounter", status: encounter.status, error: encounter.error });
    }

    const triggerScore = Number(session.activation?.triggerScore ?? 0);
    const observations = [
      fhirObservationResource(patientId, fhirPatientId, result.encounterId, session, {
        code: "pain-likelihood",
        display: "Pain likelihood",
        value: Math.round(triggerScore * 100),
        unit: "%",
        unitCode: "%",
        note: "PainThermometer watch model trigger score.",
      }),
      fhirObservationResource(patientId, fhirPatientId, result.encounterId, session, {
        code: "activation-positive-windows",
        display: "Pain activation positive windows",
        value: session.activation?.positiveWindows ?? 0,
        category: "exam",
        categoryDisplay: "Exam",
        note: `Positive windows out of ${session.activation?.windowCount ?? 10}.`,
      }),
      ...((session.vitalsWindow?.sensors_present || []).slice(0, 12).map((sensor) =>
        fhirObservationResource(patientId, fhirPatientId, result.encounterId, session, {
          code: `sensor-coverage-${sensor.sensor}`,
          display: `${sensor.sensor} coverage`,
          value: Math.round((sensor.coverage_0_1 || 0) * 100),
          unit: "%",
          unitCode: "%",
          category: "vital-signs",
          categoryDisplay: "Vital Signs",
          identifierType: "sensor-coverage-id",
          note: `${sensor.count} samples in the trigger buffer.`,
        }),
      )),
    ];

    for (const observation of observations) {
      const posted = await fhirPost("Observation", observation);
      if (posted.ok) {
        result.observationIds.push(posted.id);
      } else {
        result.errors.push({ resource: "Observation", status: posted.status, error: posted.error });
      }
    }

    const questionnaire = await fhirPost(
      "QuestionnaireResponse",
      fhirQuestionnaireResponseResource(patientId, fhirPatientId, result.encounterId, session),
    );
    if (questionnaire.ok) {
      result.questionnaireResponseId = questionnaire.id;
    } else {
      result.errors.push({ resource: "QuestionnaireResponse", status: questionnaire.status, error: questionnaire.error });
    }

    const document = await fhirPost(
      "DocumentReference",
      fhirDocumentReferenceResource(patientId, fhirPatientId, result.encounterId, session),
    );
    if (document.ok) {
      result.documentReferenceId = document.id;
    } else {
      result.errors.push({ resource: "DocumentReference", status: document.status, error: document.error });
    }

    result.ok = Boolean(
      result.encounterId || result.observationIds.length || result.questionnaireResponseId || result.documentReferenceId,
    );
  } catch (error) {
    result.errors.push({ resource: "FHIR", error: error.message });
  }
  return result;
}

async function fhirPost(resourceType, resource) {
  const baseUrl = secretValue(PROMPTOPINION_FHIR_BASE_URL).replace(/\/$/, "");
  const apiKey = secretValue(PROMPTOPINION_API_KEY);
  if (!baseUrl || !apiKey) return { ok: false, skipped: true };
  const response = await fetch(`${baseUrl}/${encodeURIComponent(resourceType)}`, {
    method: "POST",
    headers: {
      Accept: "application/fhir+json",
      "Content-Type": "application/fhir+json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(cleanForFirestore(resource)),
  });
  const text = await response.text();
  let parsed = {};
  try {
    parsed = text ? JSON.parse(text) : {};
  } catch {
    parsed = {};
  }
  return {
    ok: response.ok,
    status: response.status,
    id: response.ok ? parsed.id : undefined,
    resource: response.ok ? parsed : undefined,
    error: response.ok ? undefined : text.slice(0, 240),
  };
}

async function fhirPut(resourceType, resourceId, resource) {
  const baseUrl = secretValue(PROMPTOPINION_FHIR_BASE_URL).replace(/\/$/, "");
  const apiKey = secretValue(PROMPTOPINION_API_KEY);
  if (!baseUrl || !apiKey) return { ok: false, skipped: true };
  const response = await fetch(`${baseUrl}/${encodeURIComponent(resourceType)}/${encodeURIComponent(resourceId)}`, {
    method: "PUT",
    headers: {
      Accept: "application/fhir+json",
      "Content-Type": "application/fhir+json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(cleanForFirestore(resource)),
  });
  const text = await response.text();
  return {
    ok: response.ok,
    status: response.status,
    id: response.ok ? resourceId : undefined,
    error: response.ok ? undefined : text.slice(0, 240),
  };
}

async function persistPatient(patient) {
  let firestore = { ok: false };
  let fhir = { ok: false };
  try {
    fhir = await fhirPost("Patient", fhirPatientResource(patient));
    if (fhir.id) {
      patient.fhirPatientId = fhir.id;
    }
  } catch (error) {
    fhir = { ok: false, error: error.message };
    console.error("patient_fhir_write_failed", error);
  }
  try {
    const cleanPatient = cleanForFirestore(patient);
    await db.collection("patients").doc(patient.id).set(cleanPatient, { merge: true });
    await db.collection("users").doc(patient.id).set(
      cleanForFirestore({
        id: patient.id,
        type: "patient",
        displayName: patient.name,
        firstName: patient.firstName,
        lastName: patient.lastName,
        fhirPatientId: patient.fhirPatientId,
        assignedGroupIds: patient.assignedGroupIds,
        primaryGroupId: patient.primaryGroupId || patient.assignedGroupIds?.[0] || DOCTOR_A_GROUP_ID,
        source: patient.source,
        createdAt: patient.createdAt,
        updatedAt: nowIso(),
      }),
      { merge: true },
    );
    firestore = { ok: true };
  } catch (error) {
    firestore = { ok: false, error: error.message };
    console.error("patient_firestore_write_failed", error);
  }
  return { firestore, fhir };
}

function scoreValue(body) {
  return Number(
    body.score?.pain_likelihood_0_1 ??
      body.score?.painLikelihood01 ??
      (body.score?.pain_score_0_100 !== undefined ? body.score.pain_score_0_100 / 100 : undefined) ??
      body.activation?.triggerScore ??
      0.78,
  );
}

function sessionFromPainTrigger(body, payload, patientId) {
  const triggerScore = scoreValue(body);
  const startedAt = body.triggered_at || body.triggeredAt || nowIso();
  const clinicianGroupId = normalizeDoctorGroupId(body.doctor_group_id || body.doctorGroupID);
  return {
    id: payload.session_id,
    sessionId: payload.session_id,
    sessionType: "pain_incident",
    patientId,
    clinicianGroupId,
    startedAt,
    durationMinutes: 0,
    sourceDevice: body.source || "PainThermometer Watch PoC",
    activation: {
      positiveWindows: body.activation_positive_count ?? body.activationPositiveCount ?? null,
      windowCount: body.activation_window_count ?? body.activationWindowCount ?? null,
      triggerScore,
    },
    survey: {
      id: `survey_${payload.session_id}`,
      status: "in_progress",
      finalGpmScore: 0,
      adjustedGpmScore: 0,
      adjustmentReason: "Questionnaire has started from a sustained watch pain trigger.",
      questions: [],
    },
    biometrics: summarizeVitals(normalizeVitals(body)).sensors_present.map((sensor) => ({
      metric: sensor.sensor,
      sensor: sensor.sensor,
      value: `${sensor.count} samples`,
      zScore: 0,
      interpretation: `${Math.round(sensor.coverage_0_1 * 100)}% coverage in trigger buffer`,
    })),
    scores: [
      {
        name: "Pain likelihood",
        score: Math.round(triggerScore * 100),
        scale: "0-100",
        severity: triggerScore >= 0.65 ? "high" : "moderate",
        note: "Watch model trigger score",
      },
    ],
    chat: [
      {
        id: "msg_opening",
        speaker: "assistant",
        time: new Date(startedAt).toISOString().slice(11, 16),
        text: payload.question,
      },
    ],
    summaries: [
      `PainThermometer opened a questionnaire after a sustained watch trigger with score ${Math.round(triggerScore * 100)}%.`,
    ],
    vitalsWindow: payload.vitals_window,
    vitals: payload.vitals,
    scoreHistory: body.score_history || [],
    createdAt: nowIso(),
    updatedAt: nowIso(),
  };
}

async function persistPainSession(patientId, session, fhirResult = null) {
  try {
    const sessionWithFhir = fhirResult
      ? {
          ...session,
          fhirResources: {
            encounterId: fhirResult.encounterId,
            observationIds: fhirResult.observationIds,
            questionnaireResponseId: fhirResult.questionnaireResponseId,
            documentReferenceId: fhirResult.documentReferenceId,
          },
          fhirWritten: fhirResult.ok,
        }
      : session;
    const patientRef = db.collection("patients").doc(patientId);
    const sessionRef = patientRef.collection("sessions").doc(session.sessionId);
    await db.runTransaction(async (transaction) => {
      const sessionSnapshot = await transaction.get(sessionRef);
      transaction.set(sessionRef, cleanForFirestore(sessionWithFhir), { merge: true });
      transaction.set(db.collection("pain_sessions").doc(session.sessionId), cleanForFirestore(sessionWithFhir), { merge: true });
      transaction.set(
        patientRef,
        {
          id: patientId,
          updatedAt: nowIso(),
          assignedGroupIds: [session.clinicianGroupId || DOCTOR_A_GROUP_ID],
          latestSessionAt: session.startedAt,
          sessionCount: admin.firestore.FieldValue.increment(sessionSnapshot.exists ? 0 : 1),
        },
        { merge: true },
      );
    });
    return { ok: true };
  } catch (error) {
    console.error("session_firestore_write_failed", error);
    return { ok: false, error: error.message };
  }
}

async function toolResult(req, name, args) {
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
  } else if (name === TOOL_NAMES.listPatients) {
    const groupId = args.clinician_group_id || args.group_id || DOCTOR_A_GROUP_ID;
    payload = {
      clinician_group_id: groupId,
      patients: await visiblePatientsForGroup(groupId),
      generated_at: nowIso(),
      prompt_opinion_context: fhirContext(req),
    };
  } else if (name === TOOL_NAMES.summarizePatientHistory) {
    const groupId = args.clinician_group_id || args.group_id || DOCTOR_A_GROUP_ID;
    const patientId = args.patient_id || fhirContext(req).patient_id || TEST_PATIENT_ID;
    if (!(await groupCanReadPatient(groupId, patientId))) {
      payload = {
        clinician_group_id: groupId,
        patient_id: patientId,
        allowed: false,
        summary: "This clinician group is not assigned to the requested patient.",
        generated_at: nowIso(),
      };
    } else {
      payload = {
        allowed: true,
        clinician_group_id: groupId,
        ...(await summarizePatient(patientId)),
        generated_at: nowIso(),
        prompt_opinion_context: fhirContext(req),
      };
    }
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

async function handleRpc(req, message) {
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
    const result = await toolResult(req, name, args);
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
    const responses = (await Promise.all(messages.map((message) => handleRpc(req, message)))).filter(Boolean);

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
        firestoreConfigured: true,
      },
      groups: await buildGroupsPayload(),
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
    const allowed = await groupCanReadPatient(groupId, patientId);
    const requestPrefix = allowed ? "firebase_authz_req_a" : "firebase_authz_req_denied";

    return sendJson(res, allowed ? 200 : 403, {
      allowed,
      reason: allowed
        ? undefined
        : `permission_denied: clinician group ${groupId || "unknown"} is not assigned to patient ${patientId || "unknown"}`,
      requestId: `${requestPrefix}_${Date.now().toString(36)}`,
      checkedAt: nowIso(),
      source: "prompt_opinion_fhir",
      fhirPatientId: (await patientHistory(patientId))?.fhirPatientId || patientId,
      policy: "registered_fhir_patient_scope",
    });
  },
);

exports.patientSummary = onRequest(
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

    const groupId = req.query.clinician_group_id || DOCTOR_A_GROUP_ID;
    const patientId = req.query.patient_id || TEST_PATIENT_ID;
    if (!(await groupCanReadPatient(groupId, patientId))) {
      return sendJson(res, 403, {
        allowed: false,
        clinician_group_id: groupId,
        patient_id: patientId,
        summary: "This clinician group is not assigned to the requested patient.",
      });
    }

    return sendJson(res, 200, {
      allowed: true,
      clinician_group_id: groupId,
      ...(await summarizePatient(patientId)),
      generated_at: nowIso(),
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
    const patient = patientFromWatchPayload(body);
    const persistResult = await persistPatient(patient);
    return sendJson(res, 200, {
      accepted: persistResult.firestore.ok || persistResult.fhir.ok,
      patient_id: patient.id,
      fhir_patient_id: patient.fhirPatientId,
      firestore_written: persistResult.firestore.ok,
      fhir_written: persistResult.fhir.ok,
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
    const triggerScore = scoreValue(body);
    const payload = questionnairePayload(req, {
      incident_id: body.incident_id || stableSessionId("incident"),
      local_session_id: body.local_session_id,
      pain_score: triggerScore,
      deviation: body.score?.deviation ?? 0.12,
      buffer: body.buffer,
      score_history: body.score_history,
    });
    const patient = body.patient ? patientFromWatchPayload(body) : null;
    let patientPersistResult = null;
    if (patient) {
      patientPersistResult = await persistPatient(patient);
    }
    const patientId = patient?.id || body.patient_id || TEST_PATIENT_ID;
    const session = sessionFromPainTrigger(body, payload, patientId);
    const storedPatient = patient || (await loadPatient(patientId)) || {};
    const fhirResult = await persistPainSessionToFhir(patientId, storedPatient.fhirPatientId, session);
    const sessionPersistResult = await persistPainSession(patientId, session, fhirResult);

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
      patient_id: patientId,
      firestore_written: sessionPersistResult.ok,
      patient_firestore_written: patientPersistResult?.firestore?.ok,
      fhir_written: fhirResult.ok,
      fhir_resources: {
        encounter_id: fhirResult.encounterId,
        observation_ids: fhirResult.observationIds,
        questionnaire_response_id: fhirResult.questionnaireResponseId,
        document_reference_id: fhirResult.documentReferenceId,
      },
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
