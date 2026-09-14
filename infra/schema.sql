-- TS-Bench relational schema (T5).
--
-- Four tables:
--   dataset_versions  -- one row per immutable, published task-set snapshot
--   tasks             -- the task instances themselves, tagged with a version
--   models            -- one row per model under evaluation
--   runs / results    -- one evaluation session, and its per-task outcomes
--
-- results mirrors harness/eval_result.py's EvalResult field-for-field (see
-- T6's note) plus the `repeat` column T9's --repeats flag needs.

CREATE TABLE IF NOT EXISTS dataset_versions (
    version         TEXT PRIMARY KEY,        -- e.g. 'v0.1', immutable once published
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    instance_count  INTEGER NOT NULL,
    description     TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    instance_id         TEXT NOT NULL,
    dataset_version     TEXT NOT NULL REFERENCES dataset_versions(version),
    repo                TEXT NOT NULL,
    base_commit         TEXT NOT NULL,
    problem_statement   TEXT NOT NULL,
    gold_patch          TEXT NOT NULL,
    test_patch          TEXT NOT NULL,
    fail_to_pass        JSONB NOT NULL,
    pass_to_pass        JSONB NOT NULL,
    environment         JSONB NOT NULL,
    -- T11 contamination metadata -- disclosure, not a validity claim.
    head_commit         TEXT,
    pr_merge_date       DATE,
    PRIMARY KEY (instance_id, dataset_version)
);

CREATE TABLE IF NOT EXISTS models (
    model_id            TEXT PRIMARY KEY,   -- e.g. 'anthropic/claude-haiku-4-5-20251001', 'mock/gold'
    provider            TEXT,
    knowledge_cutoff    DATE,               -- for contamination_risk() joins against tasks.pr_merge_date
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id              BIGSERIAL PRIMARY KEY,
    model_id            TEXT NOT NULL REFERENCES models(model_id),
    dataset_version     TEXT NOT NULL REFERENCES dataset_versions(version),
    scaffold_version    TEXT,               -- fairness-contract identifier (T7)
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    config              JSONB               -- budget/turns/wall-clock/etc
);

CREATE TABLE IF NOT EXISTS results (
    result_id               BIGSERIAL PRIMARY KEY,
    run_id                   BIGINT NOT NULL REFERENCES runs(run_id),
    instance_id              TEXT NOT NULL,
    dataset_version          TEXT NOT NULL,
    repeat                   INTEGER NOT NULL DEFAULT 0,   -- 0-indexed, T9's --repeats
    status                   TEXT NOT NULL,                -- EvalStatus value
    resolved                 BOOLEAN NOT NULL DEFAULT false,
    fail_to_pass_results     JSONB NOT NULL DEFAULT '{}',
    pass_to_pass_results     JSONB NOT NULL DEFAULT '{}',
    patch_strategy           TEXT,
    reset_paths              JSONB NOT NULL DEFAULT '[]',
    wall_clock_seconds       DOUBLE PRECISION NOT NULL DEFAULT 0,
    stdout_tail              TEXT,
    stderr_tail              TEXT,
    cost_usd                 DOUBLE PRECISION,
    tokens_used              INTEGER,
    FOREIGN KEY (instance_id, dataset_version) REFERENCES tasks(instance_id, dataset_version),
    UNIQUE (run_id, instance_id, repeat)
);

CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
CREATE INDEX IF NOT EXISTS idx_results_instance ON results(instance_id, dataset_version);
CREATE INDEX IF NOT EXISTS idx_tasks_dataset_version ON tasks(dataset_version);
