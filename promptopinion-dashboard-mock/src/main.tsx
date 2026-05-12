import React from "react";
import ReactDOM from "react-dom/client";
import { Accordion, Button, Card, Chip, Table, TextArea, TextField } from "@heroui/react";
import {
  Activity,
  ChevronDown,
  ClipboardList,
  FileText,
  Info,
  MessageSquareText,
  RefreshCw,
  Search,
  ShieldAlert,
  Users,
} from "lucide-react";
import "./styles.css";

type Severity = "low" | "moderate" | "high";

type Group = {
  id: string;
  name: string;
  clinician: Clinician;
  patients: Patient[];
};

type AccessDecision = {
  allowed: boolean;
  reason?: string;
  requestId: string;
  checkedAt: string;
  source: "prompt_opinion_fhir" | "local_mock_fallback";
  fhirPatientId?: string;
  policy?: string;
};

type Clinician = {
  id: string;
  name: string;
  role: string;
};

type Patient = {
  id: string;
  fhirPatientId?: string;
  name: string;
  age: number;
  sessions?: PainIncident[];
  incidents: PainIncident[];
};

type PainIncident = {
  id: string;
  sessionId?: string;
  sessionType?: string;
  patientId?: string;
  clinicianGroupId?: string;
  startedAt: string;
  durationMinutes: number;
  sourceDevice: string;
  activation: {
    positiveWindows: number;
    windowCount: number;
    triggerScore: number;
  };
  survey: CompletedSurvey;
  biometrics: BiometricMetric[];
  scores: ScoreMetric[];
  chat: ChatMessage[];
  summaries: string[];
};

type CompletedSurvey = {
  id: string;
  status: "completed";
  finalGpmScore: number;
  adjustedGpmScore: number;
  adjustmentReason: string;
  questions: SurveyQuestion[];
};

type SurveyQuestion = {
  id: string;
  question: string;
  answer: string;
  confidence: number;
};

type BiometricMetric = {
  metric: string;
  sensor: string;
  value: string;
  zScore: number;
  interpretation: string;
};

type ScoreMetric = {
  name: string;
  score: number;
  scale: string;
  severity: Severity;
  note: string;
};

type ChatMessage = {
  id: string;
  speaker: "patient" | "assistant";
  time: string;
  text: string;
};

type RegistryPayload = {
  workspace?: {
    fhirConfigured?: boolean;
  };
  groups?: Group[];
};

type PatientSummary = {
  patient_id: string;
  patient_name?: string;
  summary: string;
  incident_count?: number;
  high_pain_incident_count?: number;
  max_adjusted_gpm_score?: number | null;
  latest_incident_at?: string | null;
};

const doctorAGroup: Group = {
  id: "grp_doctor_a",
  name: "Doctor A",
  clinician: {
    id: "usr_doctor_a",
    name: "Doctor A",
    role: "Geriatric pain clinician",
  },
  patients: [
    {
      id: "pat_test",
      name: "Test Patient",
      age: 72,
      incidents: [
        {
          id: "inc_watch_2026_05_11_001",
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
        },
      ],
    },
  ],
};

const doctorBGroup: Group = {
  id: "grp_doctor_b",
  name: "Doctor B",
  clinician: {
    id: "usr_doctor_b",
    name: "Doctor B",
    role: "Orthopedic reviewer",
  },
  patients: [],
};

const defaultGroups = [doctorAGroup, doctorBGroup];

const authzConfig = {
  endpoint: "/api/promptopinion/authorize-patient-access",
  registryEndpoint: "/api/registry",
  patientSummaryEndpoint: "/api/patient-summary",
  workspaceId: import.meta.env.VITE_PROMPTOPINION_WORKSPACE_ID,
};

async function fetchRegistry(): Promise<{ groups: Group[]; live: boolean; fhirConfigured: boolean }> {
  const response = await fetch(authzConfig.registryEndpoint);
  if (!response.ok) {
    throw new Error("registry_unavailable");
  }
  const body = (await response.json()) as RegistryPayload;
  return {
    groups: body.groups?.length ? body.groups : defaultGroups,
    live: true,
    fhirConfigured: body.workspace?.fhirConfigured === true,
  };
}

async function fetchPatientSummary(groupId: string, patientId: string): Promise<PatientSummary> {
  const params = new URLSearchParams({
    clinician_group_id: groupId,
    patient_id: patientId,
  });
  const response = await fetch(`${authzConfig.patientSummaryEndpoint}?${params.toString()}`);
  if (!response.ok) {
    throw new Error("summary_unavailable");
  }
  return (await response.json()) as PatientSummary;
}

async function checkPatientAccess(groupId: string, patientId: string): Promise<AccessDecision> {
  try {
    const response = await fetch(authzConfig.endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        workspace_id: authzConfig.workspaceId,
        clinician_group_id: groupId,
        patient_id: patientId,
        requested_scope: "patient.read",
        fhir_resource: `Patient/${patientId}`,
      }),
    });

    const body = (await response.json()) as Partial<AccessDecision>;
    return {
      allowed: response.ok && body.allowed === true,
      reason: body.reason ?? (response.ok ? undefined : "permission_denied"),
      requestId: body.requestId ?? response.headers.get("x-request-id") ?? "authz_req_unknown",
      checkedAt: body.checkedAt ?? new Date().toISOString(),
      source: "prompt_opinion_fhir",
      fhirPatientId: body.fhirPatientId ?? patientId,
      policy: body.policy ?? "registered_fhir_patient_scope",
    };
  } catch {
    return localMockAccessDecision(groupId, patientId);
  }
}

function localMockAccessDecision(groupId: string, patientId: string): AccessDecision {
  const allowed = groupId === "grp_doctor_a" && patientId === "pat_test";
  return {
    allowed,
    reason: allowed
      ? undefined
      : "permission_denied: clinician group is not assigned to patient pat_test",
    requestId: allowed ? "mock_authz_req_a_204" : "mock_authz_req_b_403",
    checkedAt: new Date("2026-05-11T16:51:04Z").toISOString(),
    source: "local_mock_fallback",
    fhirPatientId: patientId,
    policy: "registered_fhir_patient_scope",
  };
}

function App() {
  const [groups, setGroups] = React.useState<Group[]>(defaultGroups);
  const [registryLive, setRegistryLive] = React.useState(false);
  const [fhirConfigured, setFhirConfigured] = React.useState(false);
  const [selectedGroupId, setSelectedGroupId] = React.useState(
    () => localStorage.getItem("painDashboard.selectedGroupId") || doctorAGroup.id,
  );
  const [selectedPatientId, setSelectedPatientId] = React.useState(
    () => localStorage.getItem("painDashboard.selectedPatientId") || doctorAGroup.patients[0].id,
  );
  const doctorA = groups.find((group) => group.id === doctorAGroup.id) ?? doctorAGroup;
  const selectedGroup = groups.find((candidate) => candidate.id === selectedGroupId) ?? doctorA;
  const visiblePatients = selectedGroup.patients.length ? selectedGroup.patients : doctorA.patients;
  const patient =
    visiblePatients.find((candidate) => candidate.id === selectedPatientId) ??
    visiblePatients[0] ??
    doctorAGroup.patients[0];
  const patientSessions = patient.sessions?.length ? patient.sessions : patient.incidents;
  const incident = patientSessions[0] ?? doctorAGroup.patients[0].incidents[0];
  const [accessDecision, setAccessDecision] = React.useState<AccessDecision | null>(null);
  const [isCheckingAccess, setIsCheckingAccess] = React.useState(true);
  const [summaryIndex, setSummaryIndex] = React.useState(0);
  const [serviceSummary, setServiceSummary] = React.useState<PatientSummary | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = React.useState(false);
  const [showAuthzInfo, setShowAuthzInfo] = React.useState(false);

  React.useEffect(() => {
    let isCurrent = true;
    fetchRegistry()
      .then((registry) => {
        if (!isCurrent) return;
        setGroups(registry.groups);
        setRegistryLive(registry.live);
        setFhirConfigured(registry.fhirConfigured);
      })
      .catch(() => {
        if (!isCurrent) return;
        setGroups(defaultGroups);
        setRegistryLive(false);
        setFhirConfigured(false);
      });
    return () => {
      isCurrent = false;
    };
  }, []);

  React.useEffect(() => {
    if (!groups.some((group) => group.id === selectedGroupId)) {
      setSelectedGroupId(doctorAGroup.id);
      return;
    }
    const group = groups.find((candidate) => candidate.id === selectedGroupId);
    const patientExists = group?.patients.some((candidate) => candidate.id === selectedPatientId);
    if (!patientExists && group?.patients[0]) {
      setSelectedPatientId(group.patients[0].id);
    }
  }, [groups, selectedGroupId, selectedPatientId]);

  React.useEffect(() => {
    localStorage.setItem("painDashboard.selectedGroupId", selectedGroup.id);
    localStorage.setItem("painDashboard.selectedPatientId", patient.id);
  }, [selectedGroup.id, patient.id]);

  React.useEffect(() => {
    let isCurrent = true;
    setIsCheckingAccess(true);
    checkPatientAccess(selectedGroup.id, patient.id).then((decision) => {
      if (!isCurrent) return;
      setAccessDecision(decision);
      setIsCheckingAccess(false);
    });
    return () => {
      isCurrent = false;
    };
  }, [selectedGroup.id, patient.id]);

  React.useEffect(() => {
    setServiceSummary(null);
    setSummaryIndex(0);
  }, [patient.id]);

  const visibleAccessDecision =
    accessDecision ??
    ({
      allowed: false,
      reason: "authorization_check_pending",
      requestId: "pending",
      checkedAt: new Date().toISOString(),
      source: "prompt_opinion_fhir",
      fhirPatientId: patient.id,
      policy: "registered_fhir_patient_scope",
    } satisfies AccessDecision);

  const requestSummary = async () => {
    setIsLoadingSummary(true);
    try {
      const summary = await fetchPatientSummary(selectedGroup.id, patient.id);
      setServiceSummary(summary);
    } catch {
      setSummaryIndex((current) => (current + 1) % incident.summaries.length);
    } finally {
      setIsLoadingSummary(false);
    }
  };

  return (
    <main className="min-h-screen bg-[var(--app-bg)] text-slate-950">
      <header className="border-b border-slate-200 bg-white/92">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-md bg-slate-950 text-white">
              <Activity size={20} />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-normal text-slate-500">
                PainThermometer clinical review
              </p>
              <h1 className="text-xl font-semibold leading-tight">{selectedGroup.name}</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Chip color={fhirConfigured ? "success" : "warning"} size="sm" variant="soft">
              <Chip.Label>{fhirConfigured ? "FHIR context available" : "FHIR context pending"}</Chip.Label>
            </Chip>
            <Chip color={registryLive ? "success" : "warning"} size="sm" variant="soft">
              <Chip.Label>{registryLive ? "Live Firebase" : "Offline fallback"}</Chip.Label>
            </Chip>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1440px] grid-cols-1 gap-5 px-6 py-5 lg:grid-cols-[minmax(0,1fr)_minmax(380px,0.8fr)]">
        <section className="flex min-w-0 flex-col gap-5">
          <GroupAccessSwitcher
            groups={groups}
            selectedGroup={selectedGroup}
            accessDecision={visibleAccessDecision}
            isCheckingAccess={isCheckingAccess}
            showAuthzInfo={showAuthzInfo}
            onSelectGroup={(groupId) => {
              setSelectedGroupId(groupId);
              const nextGroup = groups.find((group) => group.id === groupId);
              if (nextGroup?.patients[0]) {
                setSelectedPatientId(nextGroup.patients[0].id);
              }
              setShowAuthzInfo(false);
            }}
            selectedPatient={patient}
            patients={visiblePatients}
            onSelectPatient={setSelectedPatientId}
            onToggleInfo={() => setShowAuthzInfo((value) => !value)}
          />
          {!isCheckingAccess && visibleAccessDecision.allowed ? (
            <>
              <PatientOverview group={selectedGroup} patient={patient} incident={incident} />
              <IncidentCharts incident={incident} />
              <Tables incident={incident} />
            </>
          ) : (
            <AccessDenied
              group={selectedGroup}
              patient={patient}
              accessDecision={visibleAccessDecision}
              isCheckingAccess={isCheckingAccess}
            />
          )}
        </section>
        <aside className="min-w-0">
          {!isCheckingAccess && visibleAccessDecision.allowed ? (
            <ConversationPanel
              incident={incident}
              summary={serviceSummary?.summary ?? incident.summaries[summaryIndex]}
              isLoadingSummary={isLoadingSummary}
              onRequestSummary={requestSummary}
            />
          ) : (
            <RestrictedConversation group={selectedGroup} patient={patient} />
          )}
        </aside>
      </div>
    </main>
  );
}

function GroupAccessSwitcher({
  groups,
  selectedGroup,
  selectedPatient,
  patients,
  accessDecision,
  isCheckingAccess,
  showAuthzInfo,
  onSelectGroup,
  onSelectPatient,
  onToggleInfo,
}: {
  groups: Group[];
  selectedGroup: Group;
  selectedPatient: Patient;
  patients: Patient[];
  accessDecision: AccessDecision;
  isCheckingAccess: boolean;
  showAuthzInfo: boolean;
  onSelectGroup: (groupId: string) => void;
  onSelectPatient: (patientId: string) => void;
  onToggleInfo: () => void;
}) {
  return (
    <Card variant="default" className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <Card.Content className="flex flex-col gap-4 py-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-normal text-slate-500">Clinician group</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {groups.map((group) => (
              <Button
                key={group.id}
                size="sm"
                variant={group.id === selectedGroup.id ? "primary" : "secondary"}
                onPress={() => onSelectGroup(group.id)}
              >
                {group.name}
              </Button>
            ))}
          </div>
          <label className="mt-4 block text-xs font-medium uppercase tracking-normal text-slate-500" htmlFor="patient-picker">
            Patient
          </label>
          <select
            id="patient-picker"
            className="mt-2 h-9 rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900"
            value={selectedPatient.id}
            onChange={(event) => onSelectPatient(event.target.value)}
          >
            {patients.map((patient) => (
              <option key={patient.id} value={patient.id}>
                {patient.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <Chip color={accessDecision.allowed ? "success" : "danger"} size="sm" variant="soft">
            <Chip.Label>
              {isCheckingAccess
                ? "Checking FHIR access"
                : accessDecision.allowed
                  ? "Patient access granted"
                  : "Patient access denied"}
            </Chip.Label>
          </Chip>
          <Button isIconOnly aria-label="Show backend permission response" size="sm" variant="tertiary" onPress={onToggleInfo}>
            <Info size={16} />
          </Button>
        </div>
      </Card.Content>
      {showAuthzInfo ? (
        <Card.Footer className="border-t border-slate-200 bg-slate-50 text-xs text-slate-600">
          <code>
            authz source={accessDecision.source} · request={accessDecision.requestId} ·
            policy={accessDecision.policy} · fhir={accessDecision.fhirPatientId} ·
            allowed={String(accessDecision.allowed)}
            {accessDecision.reason ? ` · ${accessDecision.reason}` : ""} ·
            checked={accessDecision.checkedAt}
          </code>
        </Card.Footer>
      ) : null}
    </Card>
  );
}

function AccessDenied({
  group,
  patient,
  accessDecision,
  isCheckingAccess,
}: {
  group: Group;
  patient: Patient;
  accessDecision: AccessDecision;
  isCheckingAccess: boolean;
}) {
  return (
    <Card variant="default" className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <Card.Content className="grid min-h-[420px] place-items-center p-10 text-center">
        <div className="max-w-md">
          <div className="mx-auto mb-4 grid size-12 place-items-center rounded-md bg-rose-50 text-rose-700">
            <ShieldAlert size={24} />
          </div>
          <h2 className="text-lg font-semibold">
            {isCheckingAccess ? "Checking patient access" : `${group.name} does not have access to ${patient.name}`}
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            {isCheckingAccess
              ? "The app is asking the Prompt Opinion registered FHIR/auth layer whether this clinician group can read the patient."
              : "The backend permission check rejected this patient lookup. The clinical incident, survey, biometrics, scores, and transcript stay hidden for this group."}
          </p>
          <p className="mt-4 font-mono text-xs text-slate-500">request {accessDecision.requestId}</p>
        </div>
      </Card.Content>
    </Card>
  );
}

function RestrictedConversation({ group, patient }: { group: Group; patient: Patient }) {
  return (
    <div className="sticky top-4 grid min-h-[720px] place-items-center rounded-lg border border-slate-200 bg-white p-8 text-center shadow-sm">
      <div>
        <MessageSquareText className="mx-auto mb-4 text-slate-400" size={32} />
        <h2 className="text-base font-semibold">Interview unavailable</h2>
        <p className="mt-2 text-sm text-slate-600">
          {group.name} cannot view {patient.name}'s conversation log or request summaries.
        </p>
      </div>
    </div>
  );
}

function PatientOverview({
  group,
  patient,
  incident,
}: {
  group: Group;
  patient: Patient;
  incident: PainIncident;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[260px_minmax(0,1fr)]">
      <Card variant="default" className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <Card.Header>
          <Card.Title className="flex items-center gap-2 text-sm">
            <Users size={16} />
            Care Group
          </Card.Title>
          <Card.Description>{group.clinician.role}</Card.Description>
        </Card.Header>
        <Card.Content className="space-y-4">
          <div>
            <p className="text-xs text-slate-500">Signed in as</p>
            <p className="font-medium">{group.clinician.name}</p>
          </div>
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <p className="text-xs font-medium uppercase tracking-normal text-slate-500">Patients</p>
            <p className="mt-2 text-sm font-semibold">{patient.name}</p>
            <p className="text-xs text-slate-500">
              Age {patient.age} · {(patient.sessions?.length ?? patient.incidents.length)} session
            </p>
          </div>
        </Card.Content>
      </Card>

      <Card variant="default" className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <Card.Header className="flex-row items-start justify-between gap-3">
          <div>
            <Card.Title className="text-base">{patient.name}</Card.Title>
            <Card.Description>
              Session {incident.sessionId ?? incident.id} · {new Date(incident.startedAt).toLocaleString()}
            </Card.Description>
          </div>
          <Chip color="danger" size="sm" variant="soft">
            <Chip.Label>Pain detected {incident.activation.positiveWindows}/{incident.activation.windowCount}</Chip.Label>
          </Chip>
        </Card.Header>
        <Card.Content>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricTile label="Trigger score" value={`${Math.round(incident.activation.triggerScore * 100)}%`} />
            <MetricTile label="Duration" value={`${incident.durationMinutes}m`} />
            <MetricTile label="GPM raw" value={`${incident.survey.finalGpmScore}/42`} />
            <MetricTile label="Adjusted" value={`${incident.survey.adjustedGpmScore}/100`} />
          </div>
          <p className="mt-4 text-sm text-slate-600">{incident.survey.adjustmentReason}</p>
        </Card.Content>
      </Card>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function IncidentCharts({ incident }: { incident: PainIncident }) {
  const scorePoints = incident.scores.map((score, index) => ({
    x: 24 + index * 76,
    y: 112 - Math.min(100, score.score) * 0.86,
    label: score.name,
  }));

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card variant="default" className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <Card.Header>
          <Card.Title className="flex items-center gap-2 text-sm">
            <Activity size={16} />
            Incident Signal
          </Card.Title>
          <Card.Description>From the latest 100-sample watch buffer.</Card.Description>
        </Card.Header>
        <Card.Content>
          <svg className="h-36 w-full overflow-visible" viewBox="0 0 300 128" role="img" aria-label="Incident signal chart">
            <line x1="16" x2="292" y1="100" y2="100" className="stroke-slate-200" />
            <line x1="16" x2="292" y1="40" y2="40" className="stroke-rose-200" strokeDasharray="4 4" />
            <polyline
              fill="none"
              points="16,96 42,92 68,90 94,74 120,50 146,42 172,44 198,58 224,64 250,62 276,70 292,76"
              className="stroke-rose-600"
              strokeWidth="3"
            />
            <polyline
              fill="none"
              points="16,82 42,78 68,80 94,72 120,68 146,66 172,70 198,76 224,79 250,83 276,82 292,86"
              className="stroke-sky-600"
              strokeWidth="2"
            />
          </svg>
          <div className="flex items-center gap-4 text-xs text-slate-600">
            <span className="inline-flex items-center gap-1"><span className="size-2 rounded-full bg-rose-600" /> Pain likelihood</span>
            <span className="inline-flex items-center gap-1"><span className="size-2 rounded-full bg-sky-600" /> Baseline departure</span>
          </div>
        </Card.Content>
      </Card>

      <Card variant="default" className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <Card.Header>
          <Card.Title className="flex items-center gap-2 text-sm">
            <ClipboardList size={16} />
            Score Profile
          </Card.Title>
          <Card.Description>Actual returned scores displayed on native scales.</Card.Description>
        </Card.Header>
        <Card.Content>
          <svg className="h-36 w-full overflow-visible" viewBox="0 0 300 128" role="img" aria-label="Score profile chart">
            <line x1="16" x2="292" y1="112" y2="112" className="stroke-slate-200" />
            <polyline
              fill="none"
              points={scorePoints.map((point) => `${point.x},${point.y}`).join(" ")}
              className="stroke-emerald-600"
              strokeWidth="3"
            />
            {scorePoints.map((point) => (
              <circle key={point.label} cx={point.x} cy={point.y} r="4" className="fill-emerald-600" />
            ))}
          </svg>
          <p className="text-xs text-slate-600">
            Pain and survey adjustments stay separate so clinicians can distinguish sensor inference from testimony.
          </p>
        </Card.Content>
      </Card>
    </div>
  );
}

function Tables({ incident }: { incident: PainIncident }) {
  return (
    <Accordion allowsMultipleExpanded defaultExpandedKeys={new Set(["biometrics", "scores", "survey"])} variant="surface">
      <Accordion.Item id="biometrics">
        <Accordion.Heading>
          <Accordion.Trigger>
            Biometrics by z-score
            <Accordion.Indicator>
              <ChevronDown size={16} />
            </Accordion.Indicator>
          </Accordion.Trigger>
        </Accordion.Heading>
        <Accordion.Panel>
          <Accordion.Body>
            <BiometricTable metrics={incident.biometrics} />
          </Accordion.Body>
        </Accordion.Panel>
      </Accordion.Item>

      <Accordion.Item id="scores">
        <Accordion.Heading>
          <Accordion.Trigger>
            Inferred and survey scores
            <Accordion.Indicator>
              <ChevronDown size={16} />
            </Accordion.Indicator>
          </Accordion.Trigger>
        </Accordion.Heading>
        <Accordion.Panel>
          <Accordion.Body>
            <ScoreTable scores={incident.scores} />
          </Accordion.Body>
        </Accordion.Panel>
      </Accordion.Item>

      <Accordion.Item id="survey">
        <Accordion.Heading>
          <Accordion.Trigger>
            Completed survey
            <Accordion.Indicator>
              <ChevronDown size={16} />
            </Accordion.Indicator>
          </Accordion.Trigger>
        </Accordion.Heading>
        <Accordion.Panel>
          <Accordion.Body>
            <SurveyList survey={incident.survey} />
          </Accordion.Body>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}

function BiometricTable({ metrics }: { metrics: BiometricMetric[] }) {
  return (
    <Table variant="secondary">
      <Table.ScrollContainer>
        <Table.Content aria-label="Biometric z-score table" className="min-w-[720px]">
          <Table.Header>
            <Table.Column isRowHeader>Metric</Table.Column>
            <Table.Column>Sensor</Table.Column>
            <Table.Column>Value</Table.Column>
            <Table.Column>Z-score</Table.Column>
            <Table.Column>Interpretation</Table.Column>
          </Table.Header>
          <Table.Body>
            {metrics.map((metric) => (
              <Table.Row key={metric.metric} id={metric.metric}>
                <Table.Cell>{metric.metric}</Table.Cell>
                <Table.Cell className="font-mono text-xs">{metric.sensor}</Table.Cell>
                <Table.Cell>{metric.value}</Table.Cell>
                <Table.Cell>
                  <Chip color={zScoreColor(metric.zScore)} size="sm" variant="soft">
                    <Chip.Label>{metric.zScore.toFixed(1)}</Chip.Label>
                  </Chip>
                </Table.Cell>
                <Table.Cell>{metric.interpretation}</Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table.Content>
      </Table.ScrollContainer>
    </Table>
  );
}

function ScoreTable({ scores }: { scores: ScoreMetric[] }) {
  return (
    <Table variant="secondary">
      <Table.ScrollContainer>
        <Table.Content aria-label="Score table" className="min-w-[720px]">
          <Table.Header>
            <Table.Column isRowHeader>Score</Table.Column>
            <Table.Column>Value</Table.Column>
            <Table.Column>Scale</Table.Column>
            <Table.Column>Band</Table.Column>
            <Table.Column>Note</Table.Column>
          </Table.Header>
          <Table.Body>
            {scores.map((score) => (
              <Table.Row key={score.name} id={score.name}>
                <Table.Cell>{score.name}</Table.Cell>
                <Table.Cell>{score.score}</Table.Cell>
                <Table.Cell>{score.scale}</Table.Cell>
                <Table.Cell>
                  <Chip color={severityColor(score.severity)} size="sm" variant="soft">
                    <Chip.Label>{score.severity}</Chip.Label>
                  </Chip>
                </Table.Cell>
                <Table.Cell>{score.note}</Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table.Content>
      </Table.ScrollContainer>
    </Table>
  );
}

function SurveyList({ survey }: { survey: CompletedSurvey }) {
  return (
    <div className="space-y-3">
      {survey.questions.map((question) => (
        <div key={question.id} className="rounded-md border border-slate-200 bg-white p-3">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm font-medium">{question.question}</p>
            <span className="shrink-0 text-xs text-slate-500">{Math.round(question.confidence * 100)}%</span>
          </div>
          <p className="mt-2 text-sm text-slate-600">{question.answer}</p>
        </div>
      ))}
    </div>
  );
}

function ConversationPanel({
  incident,
  summary,
  isLoadingSummary,
  onRequestSummary,
}: {
  incident: PainIncident;
  summary: string;
  isLoadingSummary: boolean;
  onRequestSummary: () => void;
}) {
  return (
    <div className="sticky top-4 flex max-h-[calc(100vh-2rem)] min-h-[720px] flex-col rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold">
              <MessageSquareText size={18} />
              Interview Log
            </h2>
            <p className="text-sm text-slate-500">Completed session for {incident.sessionId ?? incident.id}</p>
          </div>
          <Chip color="success" size="sm" variant="soft">
            <Chip.Label>Completed</Chip.Label>
          </Chip>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="space-y-3">
          {incident.chat.map((message) => (
            <div
              key={message.id}
              className={`max-w-[86%] rounded-lg px-3 py-2 text-sm ${
                message.speaker === "assistant"
                  ? "bg-slate-100 text-slate-800"
                  : "ml-auto bg-slate-950 text-white"
              }`}
            >
              <div className="mb-1 flex items-center justify-between gap-3 text-[11px] opacity-75">
                <span>{message.speaker === "assistant" ? "Pain interview agent" : "Test Patient"}</span>
                <span>{message.time}</span>
              </div>
              <p>{message.text}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-slate-200 p-4">
        <div className="mb-3 rounded-md border border-emerald-200 bg-emerald-50 p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-emerald-950">
            <FileText size={16} />
            Service summary
          </div>
          <p className="text-sm text-emerald-900">{summary}</p>
        </div>
        <div className="flex gap-2">
          <Button className="shrink-0" variant="secondary" isDisabled={isLoadingSummary} onPress={onRequestSummary}>
            <RefreshCw size={16} />
            {isLoadingSummary ? "Summarizing" : "Summarize"}
          </Button>
          <TextField fullWidth name="summary-prompt">
            <TextArea placeholder="Ask for a narrower session summary..." rows={1} />
          </TextField>
          <Button isIconOnly aria-label="Search conversation" variant="tertiary">
            <Search size={16} />
          </Button>
        </div>
      </div>
    </div>
  );
}

function zScoreColor(zScore: number): "success" | "warning" | "danger" {
  if (Math.abs(zScore) >= 2) return "danger";
  if (Math.abs(zScore) >= 1) return "warning";
  return "success";
}

function severityColor(severity: Severity): "success" | "warning" | "danger" {
  if (severity === "high") return "danger";
  if (severity === "moderate") return "warning";
  return "success";
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
