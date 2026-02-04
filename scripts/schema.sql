-- Homunculus Database Schema v1

-- ============================================================
-- METADATA
-- ============================================================

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO metadata (key, value) VALUES ('schema_version', '1');

-- ============================================================
-- SESSIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    project_path TEXT,
    observation_count INTEGER DEFAULT 0,
    gaps_detected INTEGER DEFAULT 0,
    proposals_generated INTEGER DEFAULT 0,
    capabilities_installed INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);

-- ============================================================
-- OBSERVATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_path TEXT,
    event_type TEXT NOT NULL CHECK (event_type IN ('pre_tool', 'post_tool', 'notification', 'stop', 'user_signal')),
    tool_name TEXT,
    tool_success INTEGER,
    tool_error TEXT,
    friction_turn_count INTEGER,
    friction_corrections INTEGER,
    friction_clarifications INTEGER,
    failure_explicit_cant INTEGER DEFAULT 0,
    failure_missing_capability TEXT,
    raw_json TEXT,
    processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_observations_processed ON observations(processed);
CREATE INDEX IF NOT EXISTS idx_observations_timestamp ON observations(timestamp);
CREATE INDEX IF NOT EXISTS idx_observations_event_type ON observations(event_type);

-- ============================================================
-- GAPS
-- ============================================================

CREATE TABLE IF NOT EXISTS gaps (
    id TEXT PRIMARY KEY,
    detected_at TEXT NOT NULL,
    gap_type TEXT NOT NULL,
    domain TEXT,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    recommended_scope TEXT NOT NULL CHECK (recommended_scope IN ('session', 'project', 'global')),
    project_path TEXT,
    desired_capability TEXT NOT NULL,
    example_invocation TEXT,
    evidence_summary TEXT,
    detector_rule_id TEXT NOT NULL,
    detector_rule_version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'synthesizing', 'proposed', 'rejected', 'resolved', 'dismissed')),
    resolved_by_proposal_id TEXT,
    dismissed_at TEXT,
    dismissed_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (resolved_by_proposal_id) REFERENCES proposals(id)
);

CREATE INDEX IF NOT EXISTS idx_gaps_status ON gaps(status);
CREATE INDEX IF NOT EXISTS idx_gaps_type ON gaps(gap_type);
CREATE INDEX IF NOT EXISTS idx_gaps_detector ON gaps(detector_rule_id);
CREATE INDEX IF NOT EXISTS idx_gaps_confidence ON gaps(confidence);

-- ============================================================
-- GAP-OBSERVATION LINKS
-- ============================================================

CREATE TABLE IF NOT EXISTS gap_observations (
    gap_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    contribution_weight REAL DEFAULT 1.0,
    PRIMARY KEY (gap_id, observation_id),
    FOREIGN KEY (gap_id) REFERENCES gaps(id) ON DELETE CASCADE,
    FOREIGN KEY (observation_id) REFERENCES observations(id) ON DELETE CASCADE
);

-- ============================================================
-- PROPOSALS
-- ============================================================

CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    gap_id TEXT NOT NULL,
    capability_type TEXT NOT NULL CHECK (capability_type IN ('skill', 'hook', 'agent', 'command', 'mcp_server')),
    capability_name TEXT NOT NULL,
    capability_summary TEXT,
    scope TEXT NOT NULL CHECK (scope IN ('session', 'project', 'global')),
    project_path TEXT,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    reasoning TEXT,
    template_id TEXT NOT NULL,
    template_version INTEGER NOT NULL DEFAULT 1,
    template_variant TEXT,  -- For A/B testing: which variant was used
    synthesis_model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'installed', 'rolled_back')),
    reviewed_at TEXT,
    reviewer_action TEXT CHECK (reviewer_action IN ('approve', 'reject', 'edit')),
    rejection_reason TEXT,
    rejection_details TEXT,
    installed_at TEXT,
    rolled_back_at TEXT,
    rollback_reason TEXT,
    files_json TEXT,
    settings_patch_json TEXT,
    rollback_instructions TEXT,
    pre_install_state_json TEXT,

    FOREIGN KEY (gap_id) REFERENCES gaps(id)
);

CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_gap ON proposals(gap_id);
CREATE INDEX IF NOT EXISTS idx_proposals_template ON proposals(template_id);
CREATE INDEX IF NOT EXISTS idx_proposals_capability_type ON proposals(capability_type);

-- ============================================================
-- CAPABILITIES
-- ============================================================

CREATE TABLE IF NOT EXISTS capabilities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    capability_type TEXT NOT NULL CHECK (capability_type IN ('skill', 'hook', 'agent', 'command', 'mcp_server')),
    scope TEXT NOT NULL CHECK (scope IN ('session', 'project', 'global')),
    project_path TEXT,
    source_proposal_id TEXT NOT NULL,
    source_gap_id TEXT NOT NULL,
    installed_at TEXT NOT NULL,
    installed_files_json TEXT,
    settings_changes_json TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'rolled_back')),
    disabled_at TEXT,
    rolled_back_at TEXT,

    FOREIGN KEY (source_proposal_id) REFERENCES proposals(id),
    FOREIGN KEY (source_gap_id) REFERENCES gaps(id)
);

CREATE INDEX IF NOT EXISTS idx_capabilities_type ON capabilities(capability_type);
CREATE INDEX IF NOT EXISTS idx_capabilities_scope ON capabilities(scope);
CREATE INDEX IF NOT EXISTS idx_capabilities_status ON capabilities(status);

-- ============================================================
-- CAPABILITY DEPENDENCIES
-- ============================================================

CREATE TABLE IF NOT EXISTS capability_dependencies (
    capability_id TEXT NOT NULL,
    depends_on_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL CHECK (dependency_type IN ('required', 'optional', 'suggested')),
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,

    PRIMARY KEY (capability_id, depends_on_id),
    FOREIGN KEY (capability_id) REFERENCES capabilities(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_id) REFERENCES capabilities(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_capability_dependencies_capability ON capability_dependencies(capability_id);
CREATE INDEX IF NOT EXISTS idx_capability_dependencies_depends_on ON capability_dependencies(depends_on_id);

-- ============================================================
-- CAPABILITY USAGE
-- ============================================================

CREATE TABLE IF NOT EXISTS capability_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id TEXT NOT NULL,
    used_at TEXT NOT NULL,
    session_id TEXT NOT NULL,
    context TEXT,

    FOREIGN KEY (capability_id) REFERENCES capabilities(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_capability_usage_capability ON capability_usage(capability_id);
CREATE INDEX IF NOT EXISTS idx_capability_usage_date ON capability_usage(used_at);

-- ============================================================
-- DETECTOR RULES (versioned)
-- ============================================================

CREATE TABLE IF NOT EXISTS detector_rules (
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    gap_type TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('high', 'medium', 'low')),
    enabled INTEGER DEFAULT 1,
    content_yaml TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT 'system',
    deprecated_at TEXT,
    deprecation_reason TEXT,

    PRIMARY KEY (id, version)
);

CREATE INDEX IF NOT EXISTS idx_detector_rules_type ON detector_rules(gap_type);
CREATE INDEX IF NOT EXISTS idx_detector_rules_enabled ON detector_rules(enabled);

-- ============================================================
-- SYNTHESIS TEMPLATES (versioned)
-- ============================================================

CREATE TABLE IF NOT EXISTS synthesis_templates (
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    output_type TEXT NOT NULL CHECK (output_type IN ('skill', 'hook', 'agent', 'command', 'mcp_server')),
    content_yaml TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT 'system',
    deprecated_at TEXT,
    deprecation_reason TEXT,

    PRIMARY KEY (id, version)
);

CREATE INDEX IF NOT EXISTS idx_synthesis_templates_type ON synthesis_templates(output_type);

-- ============================================================
-- TEMPLATE VARIANTS (for A/B testing)
-- ============================================================

CREATE TABLE IF NOT EXISTS template_variants (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    variant_name TEXT NOT NULL,
    variant_description TEXT,
    weight REAL DEFAULT 1.0,  -- Higher weight = more likely to be selected
    enabled INTEGER DEFAULT 1,
    patches_json TEXT,  -- JSON patches to apply to base template
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'system',

    UNIQUE(template_id, variant_name)
);

CREATE INDEX IF NOT EXISTS idx_template_variants_template ON template_variants(template_id);
CREATE INDEX IF NOT EXISTS idx_template_variants_enabled ON template_variants(enabled);

-- ============================================================
-- META-OBSERVATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS meta_observations (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('detector_rule', 'synthesis_template', 'gap_type', 'workflow')),
    subject_id TEXT NOT NULL,
    metrics_json TEXT,
    insight TEXT,
    confidence REAL CHECK (confidence >= 0 AND confidence <= 1),
    processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_meta_observations_type ON meta_observations(observation_type);
CREATE INDEX IF NOT EXISTS idx_meta_observations_subject ON meta_observations(subject_type, subject_id);

-- ============================================================
-- META-PROPOSALS
-- ============================================================

CREATE TABLE IF NOT EXISTS meta_proposals (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    meta_observation_id TEXT,
    proposal_type TEXT NOT NULL CHECK (proposal_type IN ('detector_patch', 'template_patch', 'new_gap_type', 'config_change')),
    target_id TEXT,
    target_version INTEGER,
    proposed_changes_json TEXT,
    reasoning TEXT,
    confidence REAL CHECK (confidence >= 0 AND confidence <= 1),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'applied', 'rolled_back')),
    reviewed_at TEXT,
    rejection_reason TEXT,
    applied_at TEXT,
    rolled_back_at TEXT,

    FOREIGN KEY (meta_observation_id) REFERENCES meta_observations(id)
);

CREATE INDEX IF NOT EXISTS idx_meta_proposals_status ON meta_proposals(status);
CREATE INDEX IF NOT EXISTS idx_meta_proposals_type ON meta_proposals(proposal_type);

-- ============================================================
-- FEEDBACK LOG
-- ============================================================

CREATE TABLE IF NOT EXISTS feedback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('proposal_review', 'meta_review', 'capability_usage', 'rollback')),
    proposal_id TEXT,
    action TEXT,
    rejection_reason TEXT,
    rejection_details TEXT,
    capability_id TEXT,
    usage_outcome TEXT,
    gap_type TEXT,
    capability_type TEXT,
    template_id TEXT,
    detector_rule_id TEXT,
    confidence_at_proposal REAL,

    FOREIGN KEY (proposal_id) REFERENCES proposals(id),
    FOREIGN KEY (capability_id) REFERENCES capabilities(id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback_log(feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_template ON feedback_log(template_id);
CREATE INDEX IF NOT EXISTS idx_feedback_detector ON feedback_log(detector_rule_id);
CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON feedback_log(timestamp);

-- ============================================================
-- DAILY METRICS
-- ============================================================

CREATE TABLE IF NOT EXISTS metrics_daily (
    date TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    dimensions_json TEXT,

    PRIMARY KEY (date, metric_name)
);

-- ============================================================
-- VIEWS
-- ============================================================

CREATE VIEW IF NOT EXISTS v_pending_proposals AS
SELECT
    p.*,
    g.gap_type,
    g.domain,
    g.desired_capability
FROM proposals p
JOIN gaps g ON p.gap_id = g.id
WHERE p.status = 'pending'
ORDER BY p.confidence DESC;

CREATE VIEW IF NOT EXISTS v_template_performance AS
SELECT
    template_id,
    template_version,
    COUNT(*) as total_proposals,
    SUM(CASE WHEN status = 'installed' THEN 1 ELSE 0 END) as installed,
    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
    ROUND(
        CAST(SUM(CASE WHEN status = 'installed' THEN 1 ELSE 0 END) AS REAL) /
        NULLIF(COUNT(*), 0) * 100,
        2
    ) as acceptance_rate
FROM proposals
GROUP BY template_id, template_version;

CREATE VIEW IF NOT EXISTS v_detector_performance AS
SELECT
    g.detector_rule_id,
    g.detector_rule_version,
    COUNT(DISTINCT g.id) as gaps_detected,
    COUNT(DISTINCT p.id) as proposals_generated,
    SUM(CASE WHEN p.status = 'installed' THEN 1 ELSE 0 END) as proposals_installed,
    SUM(CASE WHEN g.status = 'dismissed' THEN 1 ELSE 0 END) as gaps_dismissed
FROM gaps g
LEFT JOIN proposals p ON g.id = p.gap_id
GROUP BY g.detector_rule_id, g.detector_rule_version;

CREATE VIEW IF NOT EXISTS v_capability_usage_summary AS
SELECT
    c.id,
    c.name,
    c.capability_type,
    c.scope,
    c.installed_at,
    COUNT(u.id) as usage_count,
    MAX(u.used_at) as last_used
FROM capabilities c
LEFT JOIN capability_usage u ON c.id = u.capability_id
WHERE c.status = 'active'
GROUP BY c.id;

CREATE VIEW IF NOT EXISTS v_active_gaps AS
SELECT * FROM gaps
WHERE status IN ('pending', 'synthesizing')
ORDER BY confidence DESC, detected_at DESC;

CREATE VIEW IF NOT EXISTS v_capability_dependencies AS
SELECT
    cd.capability_id,
    c1.name as capability_name,
    cd.depends_on_id,
    c2.name as depends_on_name,
    cd.dependency_type,
    cd.added_at,
    cd.notes
FROM capability_dependencies cd
JOIN capabilities c1 ON cd.capability_id = c1.id
JOIN capabilities c2 ON cd.depends_on_id = c2.id
WHERE c1.status = 'active' AND c2.status = 'active';

CREATE VIEW IF NOT EXISTS v_capability_dependents AS
SELECT
    cd.depends_on_id as capability_id,
    c2.name as capability_name,
    cd.capability_id as dependent_id,
    c1.name as dependent_name,
    cd.dependency_type,
    cd.added_at
FROM capability_dependencies cd
JOIN capabilities c1 ON cd.capability_id = c1.id
JOIN capabilities c2 ON cd.depends_on_id = c2.id
WHERE c1.status = 'active' AND c2.status = 'active';

CREATE VIEW IF NOT EXISTS v_template_variant_performance AS
SELECT
    template_id,
    template_variant,
    COUNT(*) as total_proposals,
    SUM(CASE WHEN status IN ('approved', 'installed') THEN 1 ELSE 0 END) as approved,
    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
    ROUND(
        CAST(SUM(CASE WHEN status IN ('approved', 'installed') THEN 1 ELSE 0 END) AS REAL) /
        NULLIF(COUNT(*), 0) * 100,
        2
    ) as approval_rate,
    AVG(confidence) as avg_confidence
FROM proposals
WHERE template_variant IS NOT NULL
GROUP BY template_id, template_variant;
