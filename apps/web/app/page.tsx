"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  type CompiledClaim,
  type DemoRun,
  type DemoScenario,
  type HeldOutReport,
} from "@/lib/api";

type Screen = "intake" | "investigate" | "decision" | "evaluation";

function rupees(minor: number): string {
  return `₹${(minor / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

function pct(value: number | null | undefined): string {
  if (value == null) return "n/a";
  return `${(value * 100).toFixed(1)}%`;
}

function clock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function labelDecision(value: string): string {
  if (value === "ALLOW") return "ALLOW — pay";
  if (value === "REVIEW") return "REVIEW — do not guess";
  if (value === "PREVENT_DUPLICATE") return "PREVENT — do not pay twice";
  return value;
}

function decisionCopy(run: DemoRun): string {
  const decision = run.execution.evaluation.decision.decision;
  if (decision === "ALLOW") {
    return "This is a new, named failure. Remaining entitlement covers the refund. The ledger reserved first; the fake Razorpay refund settled.";
  }
  if (decision === "REVIEW") {
    return "Two physical units sit on the order. The email does not say which one failed. Policy will not invent a unit id. No money moved.";
  }
  if (decision === "PREVENT_DUPLICATE") {
    return "The WhatsApp replacement already consumed this incident’s cap. The email is the same right-bud failure on another channel. ₹4,999 was not paid twice.";
  }
  return run.execution.blocked_reason ?? "Policy returned without executing.";
}

function auditLabel(eventType: string): string {
  const labels: Record<string, string> = {
    WORLD_INGESTED: "Merchant world loaded",
    ATTEMPT_INGESTED: "Inbound ticket stored",
    CLAIM_COMPILED: "Claim compiled (grounded IDs only)",
    INCIDENT_LINKED: "Incident linked",
    POLICY_EVALUATED: "Policy decided",
    REMEDY_EXECUTED: "Remedy executed",
    REMEDY_EXECUTION_BLOCKED: "Execution blocked",
    REMEDY_SIMULATED: "Non-cash remedy simulated",
    REFUND_REQUESTED: "Refund requested",
    REFUND_SETTLED: "Refund settled",
    WEBHOOK_RECEIVED: "Webhook received",
    WEBHOOK_DUPLICATE: "Duplicate webhook ignored",
  };
  return labels[eventType] ?? eventType.replaceAll("_", " ").toLowerCase();
}

function Fact({ label, value }: { label: string; value: string | null | undefined }) {
  const missing = value == null || value === "";
  return (
    <span className={missing ? "chip unknown" : "chip"}>
      {label}: <strong>{missing ? "unknown" : value}</strong>
    </span>
  );
}

function ClaimFacts({ claim }: { claim: CompiledClaim }) {
  return (
    <div className="meta">
      <Fact label="order" value={claim.order_reference} />
      <Fact label="unit" value={claim.unit_reference} />
      <Fact label="product" value={claim.product_reference} />
      <Fact label="type" value={claim.incident_type} />
      {claim.unknown_fields.length > 0 ? (
        <span className="chip unknown">left unknown: {claim.unknown_fields.join(", ")}</span>
      ) : null}
    </div>
  );
}

function EntitlementBar({
  allowed,
  settled,
  reserved,
}: {
  allowed: number;
  settled: number;
  reserved: number;
}) {
  const remaining = Math.max(0, allowed - settled - reserved);
  const denom = allowed > 0 ? allowed : 1;
  return (
    <>
      <div className="bar" aria-hidden>
        <span className="settled" style={{ width: `${(settled / denom) * 100}%` }} />
        <span className="reserved" style={{ width: `${(reserved / denom) * 100}%` }} />
        <span className="remaining" style={{ width: `${(remaining / denom) * 100}%` }} />
      </div>
      <div className="legend">
        <span>
          <i className="s" />
          Settled {rupees(settled)}
        </span>
        <span>
          <i className="r" />
          Reserved {rupees(reserved)}
        </span>
        <span>
          <i className="m" />
          Remaining {rupees(remaining)}
        </span>
      </div>
      <p className="muted">Cap {rupees(allowed)}. Invariant: settled + reserved cannot exceed allowed.</p>
    </>
  );
}

export default function HomePage() {
  const [screen, setScreen] = useState<Screen>("intake");
  const [scenarios, setScenarios] = useState<DemoScenario[]>([]);
  const [run, setRun] = useState<DemoRun | null>(null);
  const [report, setReport] = useState<HeldOutReport | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<DemoScenario[]>("/v1/demo/scenarios")
      .then(setScenarios)
      .catch((err: Error) => setError(err.message));
  }, []);

  async function runScenario(scenarioId: string) {
    setBusy(scenarioId);
    setError(null);
    try {
      const result = await api<DemoRun>("/v1/demo/run", {
        method: "POST",
        body: JSON.stringify({ scenario_id: scenarioId }),
      });
      setRun(result);
      setScreen("investigate");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo failed");
    } finally {
      setBusy(null);
    }
  }

  async function loadEval() {
    setBusy("eval");
    setError(null);
    try {
      setReport(await api<HeldOutReport>("/v1/evaluate/heldout"));
      setScreen("evaluation");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setBusy(null);
    }
  }

  const decision = run?.execution.evaluation.decision;
  const hits = run?.retrieval.hits ?? [];
  const miss = useMemo(() => report?.outcomes.find((row) => row.documented_miss), [report]);
  const ledgerAllowed = run?.ledger?.allowed_entitlement_minor ?? decision?.allowed_entitlement_minor ?? 0;
  const ledgerSettled = run?.ledger?.settled_entitlement_minor ?? decision?.settled_entitlement_minor ?? 0;
  const ledgerReserved = run?.ledger?.reserved_entitlement_minor ?? decision?.reserved_entitlement_minor ?? 0;

  return (
    <div className="shell">
      <header className="top">
        <div>
          <div className="brand">
            Remedy<span>Graph</span>
          </div>
          <p className="kicker">AI Risk Manager · Razorpay AI Buildathon</p>
        </div>
        <p className="invariant">
          <strong>One incident, one entitlement.</strong> AI reads messy language. Deterministic
          code owns the rupees — the model never writes the ledger.
        </p>
      </header>

      <nav>
        <button className={screen === "intake" ? "active" : ""} onClick={() => setScreen("intake")}>
          1. Intake
        </button>
        <button
          className={screen === "investigate" ? "active" : ""}
          onClick={() => setScreen("investigate")}
        >
          2. Investigation
        </button>
        <button className={screen === "decision" ? "active" : ""} onClick={() => setScreen("decision")}>
          3. Decision
        </button>
        <button className={screen === "evaluation" ? "active" : ""} onClick={() => void loadEval()}>
          4. Evaluation
        </button>
      </nav>

      {error ? <p className="error">{error}</p> : null}
      {busy ? <p className="busy">Running {busy}…</p> : null}

      {screen === "intake" ? (
        <section>
          <div className="steps">
            <div className="step">
              <b>Compile</b>
              Grounded IDs only
            </div>
            <div className="step">
              <b>Retrieve + link</b>
              SAME / NEW / REVIEW
            </div>
            <div className="step money">
              <b>Policy + ledger</b>
              Money has no weights
            </div>
            <div className="step money">
              <b>Execute</b>
              ALLOW only
            </div>
          </div>
          <p className="muted">
            Asha bought ₹4,999 earbuds. Pitch order: Prevent (duplicate after WhatsApp) → Allow
            (first named failure) → Review (which bud?). You can re-run any card on the same
            database.
          </p>
          <div className="grid">
            {scenarios.map((scenario) => (
              <article className={`card scenario ${scenario.expected_decision}`} key={scenario.scenario_id}>
                <span className={`expected ${scenario.expected_decision}`}>
                  {labelDecision(scenario.expected_decision)}
                </span>
                <h2>{scenario.title}</h2>
                <p>{scenario.summary}</p>
                <div className="actions">
                  <button
                    className="primary"
                    disabled={busy !== null}
                    onClick={() => void runScenario(scenario.scenario_id)}
                  >
                    Run {scenario.scenario_id}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {screen === "investigate" ? (
        <section>
          {!run ? (
            <p className="muted">Run a scenario from Intake first.</p>
          ) : (
            <>
              <div className="grid-2">
                <article className="card">
                  <h2>Incoming {run.channel.toLowerCase()}</h2>
                  <div className="meta">
                    <span className="chip">
                      customer <strong>{run.customer_id}</strong>
                    </span>
                    <span className="chip">
                      merchant <strong>{run.merchant_id}</strong>
                    </span>
                  </div>
                  <p className="quote">{run.message_body}</p>
                </article>
                <article className="card">
                  <h2>Compiled claim</h2>
                  <p className="lead">{run.claim.incident_description}</p>
                  <p className="muted">
                    Identifiers must appear on the message. The compiler will not pick Asha’s only
                    order for her.
                  </p>
                  <ClaimFacts claim={run.claim} />
                </article>
              </div>
              <div className="grid-2" style={{ marginTop: 14 }}>
                <article className="card">
                  <h2>Prior cases</h2>
                  {hits.length === 0 ? (
                    <p>No earlier tickets for this customer. Retrieval has nothing to link.</p>
                  ) : (
                    hits.map((hit) => (
                      <div key={hit.candidate_id} style={{ marginBottom: 12 }}>
                        <p className="lead">
                          {hit.channel} · overlap {hit.overlap_score}
                        </p>
                        <p>{hit.body}</p>
                        {hit.shared_tokens.length > 0 ? (
                          <div className="meta">
                            {hit.shared_tokens.map((token) => (
                              <span className="chip" key={token}>
                                {token}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        {hit.remedies.map((remedy, index) => (
                          <p key={`${hit.candidate_id}-${index}`}>
                            Already {remedy.status.toLowerCase()}: {remedy.remedy_type.replaceAll("_", " ").toLowerCase()}{" "}
                            · consumed {rupees(remedy.entitlement_consumption_minor)}
                          </p>
                        ))}
                      </div>
                    ))
                  )}
                </article>
                <article className="card">
                  <h2>Linkage</h2>
                  <div className={`decision ${run.link.primary.relation === "SAME_INCIDENT" ? "PREVENT_DUPLICATE" : run.link.primary.relation === "UNCERTAIN" ? "REVIEW" : "ALLOW"}`}>
                    {run.link.primary.relation}
                  </div>
                  <p>Confidence {run.link.primary.confidence.toFixed(2)}</p>
                  {run.link.primary.evidence_for.length > 0 ? (
                    <p>For: {run.link.primary.evidence_for.join(" · ")}</p>
                  ) : null}
                  {run.link.primary.evidence_against.length > 0 ? (
                    <p>Against: {run.link.primary.evidence_against.join(" · ")}</p>
                  ) : null}
                  <p className="muted">
                    Relation is an input to policy. It is not a refund authorization.
                  </p>
                  <div className="actions">
                    <button className="primary" onClick={() => setScreen("decision")}>
                      See decision
                    </button>
                  </div>
                </article>
              </div>
            </>
          )}
        </section>
      ) : null}

      {screen === "decision" ? (
        <section>
          {!run || !decision ? (
            <p className="muted">Run a scenario from Intake first.</p>
          ) : (
            <>
              <article className="card">
                <span className={`expected ${decision.decision}`}>{run.title}</span>
                <div className={`decision ${decision.decision}`}>{labelDecision(decision.decision)}</div>
                <p className="lead">{decisionCopy(run)}</p>
                <p className="muted">Reasons: {decision.reason_codes.join(", ") || "none"}</p>
                {run.execution.executed ? (
                  <p>
                    Executed. Refund {run.execution.refund?.status ?? "n/a"}
                    {run.execution.refund
                      ? ` · ${rupees(run.execution.refund.amount_minor)} · ${run.execution.refund.razorpay_refund_id ?? run.execution.refund.refund_id}`
                      : ""}
                  </p>
                ) : (
                  <p>Blocked: {run.execution.blocked_reason ?? "policy did not ALLOW"}</p>
                )}
              </article>
              <div className="grid-2" style={{ marginTop: 14 }}>
                <article className="card">
                  <h3>Entitlement ledger</h3>
                  <EntitlementBar
                    allowed={ledgerAllowed}
                    settled={ledgerSettled}
                    reserved={ledgerReserved}
                  />
                  <p>Proposed now {rupees(decision.proposed_consumption_minor)}</p>
                  <p>Avoidable overcompensation {rupees(decision.avoidable_overcompensation_minor)}</p>
                </article>
                <article className="card">
                  <h3>Audit trail</h3>
                  <ol className="timeline">
                    {run.audit.map((event) => (
                      <li key={event.id}>
                        <span className="dot" />
                        <span>{auditLabel(event.event_type)}</span>
                        <span className="when">{clock(event.created_at)}</span>
                      </li>
                    ))}
                  </ol>
                </article>
              </div>
            </>
          )}
        </section>
      ) : null}

      {screen === "evaluation" ? (
        <section>
          {!report ? (
            <p className="muted">Loading held-out report…</p>
          ) : (
            <>
              <p className="muted">
                {report.case_count} frozen cases. Labels were written from the product rule, not
                from model output. Unsafe miss (gold PREVENT, we ALLOW) is ₹0.
              </p>
              <div className="grid">
                <article className="card">
                  <h3>PREVENT precision</h3>
                  <div className="metric">{pct(report.prevent_precision)}</div>
                  <p>Of our prevents, how many were actually duplicates.</p>
                </article>
                <article className="card">
                  <h3>PREVENT recall</h3>
                  <div className="metric">{pct(report.prevent_recall)}</div>
                  <p>Of true duplicates, how many we blocked or reviewed-closed.</p>
                </article>
                <article className="card">
                  <h3>False-positive cost</h3>
                  <div className="metric PREVENT_DUPLICATE">{rupees(report.false_positive_cost_minor)}</div>
                  <p>Customers we wrongly blocked.</p>
                </article>
                <article className="card">
                  <h3>Missed-loss</h3>
                  <div className="metric ALLOW">{rupees(report.missed_loss_minor)}</div>
                  <p>Unsafe ALLOW. Fail-closed on the documented miss.</p>
                </article>
                <article className="card">
                  <h3>Prevented overpay</h3>
                  <div className="metric small">{rupees(report.prevented_overcompensation_minor)}</div>
                </article>
                <article className="card">
                  <h3>Decision accuracy</h3>
                  <div className="metric small">{pct(report.decision_accuracy)}</div>
                </article>
              </div>
              {miss ? (
                <article className="card" style={{ marginTop: 14 }}>
                  <h3>Documented miss</h3>
                  <p className="lead">
                    {miss.case_id}: gold {miss.gold_decision} / {miss.gold_relation} → predicted{" "}
                    {miss.predicted_decision} / {miss.predicted_relation}
                  </p>
                  <p>
                    “Audio is gone on one side, send my money back.” No shared tokens, no order id.
                    We did not auto-refund. Recall miss, fail-closed.
                  </p>
                  <p className="muted">{miss.notes}</p>
                </article>
              ) : null}
              <article className="card" style={{ marginTop: 14 }}>
                <h3>Per-case outcomes</h3>
                <table>
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>Family</th>
                      <th>Gold</th>
                      <th>Predicted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.outcomes.map((row) => (
                      <tr
                        key={row.case_id}
                        className={row.prevent_fp ? "fp" : row.documented_miss ? "miss" : undefined}
                      >
                        <td>{row.case_id}</td>
                        <td>{row.family}</td>
                        <td>
                          {row.gold_decision} / {row.gold_relation}
                        </td>
                        <td>
                          {row.predicted_decision} / {row.predicted_relation}
                          {row.prevent_fp ? " · FP" : ""}
                          {row.documented_miss ? " · miss" : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </article>
            </>
          )}
        </section>
      ) : null}
    </div>
  );
}
