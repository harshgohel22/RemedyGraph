const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(await readApiError(response));
  }
  return response.json() as Promise<T>;
}

async function readApiError(response: Response): Promise<string> {
  const text = await response.text();
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) {
      return parsed.detail
        .map((row) =>
          typeof row === "object" && row && "msg" in row ? String((row as { msg: unknown }).msg) : JSON.stringify(row),
        )
        .join("; ");
    }
    if (parsed.detail != null) return JSON.stringify(parsed.detail);
  } catch {
    /* FastAPI 500 can be an HTML traceback. */
  }
  const compact = text.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  if (/UNIQUE constraint/i.test(compact)) {
    return "Leftover demo rows collided. Restart the API and click Run again.";
  }
  return compact.slice(0, 280) || `${response.status} ${response.statusText}`;
}

export type DemoScenario = {
  scenario_id: string;
  title: string;
  expected_decision: string;
  summary: string;
};

export type CompiledClaim = {
  claim_id: string;
  customer_id: string;
  channel: string;
  order_reference: string | null;
  product_reference: string | null;
  unit_reference: string | null;
  incident_type: string | null;
  incident_description: string;
  requested_remedy: string | null;
  unknown_fields: string[];
};

export type RetrievalHit = {
  candidate_id: string;
  channel: string;
  body: string;
  overlap_score: number;
  shared_tokens: string[];
  remedies: Array<{
    remedy_type: string;
    status: string;
    entitlement_consumption_minor: number;
  }>;
};

export type LinkAssessment = {
  relation: string;
  confidence: number;
  evidence_for: string[];
  evidence_against: string[];
  requires_review: boolean;
};

export type DemoRun = {
  scenario_id: string;
  title: string;
  expected_decision: string;
  merchant_id: string;
  customer_id: string;
  support_message_id: string;
  channel: string;
  message_body: string;
  claim: CompiledClaim;
  retrieval: { hits: RetrievalHit[] };
  link: {
    primary: LinkAssessment;
    assessments: LinkAssessment[];
  };
  execution: {
    executed: boolean;
    blocked_reason: string | null;
    refund: {
      refund_id: string;
      razorpay_refund_id: string | null;
      status: string;
      amount_minor: number;
    } | null;
    simulated: {
      remedy_type: string;
      status: string;
      amount_minor: number;
    } | null;
    evaluation: {
      incident_id: string;
      remaining_minor: number;
      decision: {
        decision: string;
        reason_codes: string[];
        allowed_entitlement_minor: number;
        settled_entitlement_minor: number;
        reserved_entitlement_minor: number;
        remaining_before_minor: number;
        remaining_after_minor: number;
        proposed_consumption_minor: number;
        avoidable_overcompensation_minor: number;
        max_safe_amount_minor: number;
      };
    };
  };
  ledger: {
    incident_id: string;
    allowed_entitlement_minor: number;
    settled_entitlement_minor: number;
    reserved_entitlement_minor: number;
    remaining_minor: number;
  } | null;
  audit: Array<{ id: string; event_type: string; created_at: string }>;
};

export type HeldOutReport = {
  case_count: number;
  prevent_precision: number | null;
  prevent_recall: number | null;
  same_precision: number | null;
  same_recall: number | null;
  decision_accuracy: number;
  intervention_recall: number | null;
  false_positive_rate: number | null;
  review_rate: number;
  automation_coverage: number;
  false_positive_cost_minor: number;
  missed_loss_minor: number;
  prevented_overcompensation_minor: number;
  review_count: number;
  documented_miss_ids: string[];
  documented_miss_confirmed: boolean;
  outcomes: Array<{
    case_id: string;
    family: string;
    gold_decision: string;
    predicted_decision: string;
    gold_relation: string;
    predicted_relation: string;
    prevent_fp: boolean;
    unsafe_miss: boolean;
    documented_miss: boolean;
    notes: string;
  }>;
};
