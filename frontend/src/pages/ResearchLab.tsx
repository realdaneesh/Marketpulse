import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FlaskConical, FileSearch } from "lucide-react";
import {
  researchApi,
  useExperiments,
  useResearchResults,
  useResearchStatus,
  type Experiment,
  type ResearchDiscovery,
} from "../api/research";
import {
  Badge,
  Empty,
  Metric,
  PageHeading,
  Panel,
  QueryState,
  Timestamp,
} from "../components/ui";
import { humanize, number, utc } from "../lib/format";

function decimal(value: number | null | undefined, digits = 3) {
  if (value == null) return "Unavailable";
  return value !== 0 && Math.abs(value) < 10 ** -digits
    ? value.toExponential(3)
    : value.toFixed(digits);
}
function rate(value: number | null | undefined) {
  return value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
}
function Finding({ finding }: { finding: ResearchDiscovery }) {
  const [open, setOpen] = useState(false);
  const evidence = useQuery({
    queryKey: ["research", "evidence", finding.id],
    queryFn: ({ signal }) => researchApi.evidence(finding.id, signal),
    enabled: open,
  });
  return (
    <article className="research-finding">
      <div className="research-title">
        <h3>{humanize(finding.type)}</h3>
        <Badge
          tone={finding.validation === "exploratory" ? "warning" : "positive"}
        >
          {humanize(finding.validation)}
        </Badge>
      </div>
      <p>
        {finding.assets.join(" · ")} · {utc(finding.end)}
      </p>
      <p>{finding.explanation}</p>
      <dl>
        <div>
          <dt>Effect / baseline</dt>
          <dd>
            {decimal(finding.effect)} / {decimal(finding.baseline)}
          </dd>
        </div>
        <div>
          <dt>Support / coverage</dt>
          <dd>
            {number(finding.observations)} / {rate(finding.coverage)}
          </dd>
        </div>
        <div>
          <dt>Statistical readiness</dt>
          <dd>{humanize(finding.statistical_readiness)}</dd>
        </div>
      </dl>
      <details>
        <summary>Uncertainty & limitations</summary>
        <ul>
          {finding.limitations.map((limit) => (
            <li key={limit}>{limit}</li>
          ))}
        </ul>
      </details>
      <button
        className="button small"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <FileSearch size={14} /> {open ? "Hide evidence" : "Inspect evidence"}
      </button>
      {open && (
        <QueryState query={evidence}>
          {(items) => (
            <div className="research-evidence">
              {items.length ? (
                items.map((item) => (
                  <details key={item.id}>
                    <summary>
                      {humanize(item.kind)} · {item.id.slice(0, 12)}
                    </summary>
                    <pre>{JSON.stringify(item.observation, null, 2)}</pre>
                  </details>
                ))
              ) : (
                <p>
                  Evidence is referenced by the frozen experiment and sequence
                  analysis.
                </p>
              )}
            </div>
          )}
        </QueryState>
      )}
    </article>
  );
}
function ExperimentView({ experiment }: { experiment: Experiment }) {
  const [segment, setSegment] = useState("train");
  const [leader, setLeader] = useState("BTCUSDT");
  const [follower, setFollower] = useState("ETHUSDT");
  const results = useResearchResults(experiment.id);
  return (
    <>
      <div className="cross-processing">
        <Metric
          label="Experiment state"
          value={humanize(experiment.state)}
          hint={`${experiment.cursor}/${experiment.total} replay evaluations`}
        />
        <Metric
          label="Replay discrepancies"
          value={String(experiment.discrepancies)}
          hint="Differences retained; production results untouched"
        />
        <Metric
          label="Purging / embargo"
          value={`${experiment.embargo_intervals} intervals`}
          hint="60% train · 20% validation · 20% test"
        />
      </div>
      <Panel
        title="Statistical reliability"
        subtitle="Descriptive evidence and held-out association are separate research stages"
      >
        <div className="research-copy">
          <p>
            {experiment.explanation} No independent event labels support
            precision, recall, F1, accuracy, or false-positive rates.
          </p>
          <p>
            Fixed chronological splits purge the start of validation and test.
            CUSUM resets at gaps and fold boundaries. Sequence inference
            requires sufficient eligible blocks, episodes, controls and
            coverage. Bootstrap intervals and block-permutation results depend
            on stationarity and exchangeability assumptions. BY adjustment
            retains all six ordered hypotheses.
          </p>
          <p>
            <strong>Frozen evidence:</strong>{" "}
            <Timestamp value={experiment.start} /> →{" "}
            <Timestamp value={experiment.end} />
          </p>
          <details>
            <summary>Reproducibility & sensitivity</summary>
            <p>
              Version: {experiment.algorithm_version} · Source:{" "}
              {experiment.source_profile_id}
            </p>
            <p className="mono research-hash">
              Fingerprint: {experiment.fingerprint}
            </p>
            <p>
              Predeclared sensitivity variants use development folds only; no
              threshold tuning on test.
            </p>
            <pre>{JSON.stringify(experiment.sensitivity, null, 2)}</pre>
          </details>
          {experiment.error && (
            <div role="alert" className="notice warning">
              {experiment.error}
            </div>
          )}
        </div>
      </Panel>
      <div className="research-controls">
        <label>
          Evaluation segment
          <select
            aria-label="Evaluation segment"
            value={segment}
            onChange={(e) => setSegment(e.target.value)}
          >
            {["train", "validation", "test", "embargo"].map((fold) => (
              <option key={fold}>{fold}</option>
            ))}
          </select>
        </label>
      </div>
      <QueryState query={results}>
        {(data) => (
          <>
            <Panel
              title="Detector evaluation"
              subtitle="Bounded view: first 200 rows. Frequencies describe unlabeled flags, not detection accuracy."
            >
              {data.metrics.filter((m) => m.segment === segment).length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Detector / asset</th>
                        <th>Eligible / expected</th>
                        <th>Coverage</th>
                        <th>Flags / frequency</th>
                        <th>Episodes</th>
                        <th>Warm-up / other exclusions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.metrics
                        .filter((m) => m.segment === segment)
                        .map((m) => (
                          <tr key={`${m.detector}-${m.entity}`}>
                            <td>
                              {humanize(m.detector)}
                              <small>{m.entity}</small>
                            </td>
                            <td>
                              {m.eligible} / {m.expected_intervals}
                            </td>
                            <td>{rate(m.eligible_coverage)}</td>
                            <td>
                              {m.alerts} / {rate(m.frequency)}
                            </td>
                            <td>
                              {m.episodes}
                              <small>
                                {m.episode_durations_seconds.join(", ") ||
                                  "No durations"}{" "}
                                seconds
                              </small>
                            </td>
                            <td>
                              {m.warmup_excluded} / {m.coverage_excluded}
                              <details>
                                <summary>Scores & overlap</summary>
                                <p>Histogram bins: [0,5), …, [95,100].</p>
                                <p>{m.score_histogram.join(" · ")}</p>
                                <pre>{JSON.stringify(m.overlap, null, 2)}</pre>
                              </details>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No eligible segment evaluations">
                  The embargo or missing source history may consume this
                  segment. No rates are inferred.
                </Empty>
              )}
            </Panel>
            <Panel
              title="Change-point timeline"
              subtitle="Two-sided robust CUSUM · heuristic structural changes, no significance claim"
            >
              {data.changes.filter((c) => c.segment === segment).length ? (
                <div className="regime-timeline">
                  {data.changes
                    .filter((c) => c.segment === segment)
                    .map((c) => (
                      <details key={c.id}>
                        <summary>
                          <strong>
                            {c.entity} · {humanize(c.feature)}
                          </strong>
                          <Timestamp value={c.end} />
                          <Badge tone="warning">Exploratory</Badge>
                        </summary>
                        <p>{c.explanation}</p>
                        <p>
                          {humanize(c.direction)} · effect {decimal(c.effect)} ·
                          scale {decimal(c.scale, 6)} · cumulative score{" "}
                          {decimal(c.cumulative_score)} / {c.threshold}
                        </p>
                        <p>
                          Production alert in preceding lag window:{" "}
                          {c.production_alert_nearby
                            ? "Observed"
                            : "None observed"}
                        </p>
                      </details>
                    ))}
                </div>
              ) : (
                <Empty title="No supported change points">
                  Warm-up, minimum effects and gap resets are preserved.
                </Empty>
              )}
            </Panel>
            <Panel
              title="Cross-asset sequence explorer"
              subtitle="Leader onset at t; follower onset in (t, t + lag]. Simultaneous events are separate."
            >
              <div className="research-controls">
                {[
                  ["Leader", leader, setLeader],
                  ["Follower", follower, setFollower],
                ].map(([label, value, setter]) => (
                  <label key={String(label)}>
                    {String(label)}
                    <select
                      aria-label={String(label)}
                      value={String(value)}
                      onChange={(e) =>
                        (setter as (v: string) => void)(e.target.value)
                      }
                    >
                      {["BTCUSDT", "ETHUSDT", "SOLUSDT"].map((asset) => (
                        <option key={asset}>{asset}</option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              {leader === follower ? (
                <Empty title="Choose different assets" />
              ) : (
                data.sequences
                  .filter(
                    (s) =>
                      s.segment === segment &&
                      s.leader === leader &&
                      s.follower === follower,
                  )
                  .map((s) => (
                    <div
                      className="research-copy"
                      key={`${s.segment}-${s.leader}-${s.follower}`}
                    >
                      <Badge
                        tone={
                          s.status === "insufficient_data"
                            ? "neutral"
                            : "warning"
                        }
                      >
                        {humanize(s.status)}
                      </Badge>
                      <dl>
                        <div>
                          <dt>Exposure / block coverage</dt>
                          <dd>
                            {s.eligible_intervals} intervals /{" "}
                            {rate(s.coverage)}
                          </dd>
                        </div>
                        <div>
                          <dt>Blocks / leader / follower episodes</dt>
                          <dd>
                            {s.blocks} / {s.leader_episodes} /{" "}
                            {s.follower_episodes}
                          </dd>
                        </div>
                        <div>
                          <dt>Following / leader opportunities</dt>
                          <dd>
                            {s.following_events} / {s.opportunities}
                          </dd>
                        </div>
                        <div>
                          <dt>Baseline events / controls</dt>
                          <dd>
                            {s.control_events} / {s.control_opportunities}
                          </dd>
                        </div>
                        <div>
                          <dt>Conditional rate / baseline rate</dt>
                          <dd>
                            {rate(s.conditional_rate)} / {rate(s.baseline_rate)}
                          </dd>
                        </div>
                        <div>
                          <dt>Effect / lift</dt>
                          <dd>
                            {decimal(s.effect)} / {decimal(s.lift)}
                          </dd>
                        </div>
                        <div>
                          <dt>Simultaneous onsets</dt>
                          <dd>{s.simultaneous}</dd>
                        </div>
                        <div>
                          <dt>Bootstrap interval / BY adjusted p</dt>
                          <dd>
                            {s.interval
                              ? s.interval.map((v) => decimal(v)).join(" to ")
                              : "Unavailable"}{" "}
                            / {decimal(s.adjusted_p)}
                          </dd>
                        </div>
                      </dl>
                      <p>{s.explanation}</p>
                    </div>
                  ))
              )}
            </Panel>
            <Panel
              title="Evidence-backed discoveries"
              subtitle="No finding is created to fill this view. First 200 records; inspect evidence before interpretation."
            >
              {data.discoveries.length ? (
                data.discoveries.map((finding) => (
                  <Finding key={finding.id} finding={finding} />
                ))
              ) : (
                <Empty title="No research discoveries">
                  Insufficient history or absent qualifying effects remain valid
                  research outcomes.
                </Empty>
              )}
            </Panel>
          </>
        )}
      </QueryState>
    </>
  );
}
export default function ResearchLab() {
  const status = useResearchStatus();
  const experiments = useExperiments(
    status.data?.state === "available" || status.data?.state === "not_started",
  );
  const [selected, setSelected] = useState("");
  const current =
    experiments.data?.find((e) => e.id === selected) ?? experiments.data?.[0];
  return (
    <>
      <PageHeading
        eyebrow="RESEARCH / PHASE 05"
        title="Research Lab"
        description="Reproducible replay, structural changes and cautious cross-asset discovery."
      >
        <FlaskConical size={25} />
      </PageHeading>
      <QueryState query={status}>
        {(state) => (
          <>
            <div className="notice">
              <Badge>{humanize(state.state)}</Badge>
              <span>{state.explanation}</span>
            </div>
            {state.state === "schema_not_migrated" ? (
              <Empty title="Research migration pending approval">
                The live market pipeline is unchanged. An explicit verified
                backup and schema migration are required before experiments can
                be published here.
              </Empty>
            ) : (
              <QueryState query={experiments}>
                {(items) => (
                  <>
                    <div className="research-controls">
                      <label>
                        Historical experiment
                        <select
                          aria-label="Historical experiment"
                          value={current?.id ?? ""}
                          onChange={(e) => setSelected(e.target.value)}
                        >
                          {!items.length && (
                            <option value="">No experiments</option>
                          )}
                          {items.map((e) => (
                            <option value={e.id} key={e.id}>
                              {utc(e.start)} → {utc(e.end)} · {e.id.slice(0, 8)}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    {current ? (
                      <ExperimentView key={current.id} experiment={current} />
                    ) : (
                      <Empty title="No historical experiments">
                        Run an explicitly bounded research experiment after
                        migration. No synthetic results are inserted into
                        production.
                      </Empty>
                    )}
                  </>
                )}
              </QueryState>
            )}
          </>
        )}
      </QueryState>
    </>
  );
}
