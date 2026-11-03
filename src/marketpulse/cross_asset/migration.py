"""Additive v3 schema; original raw trades and Phase 2 rows stay untouched."""

STATEMENTS = (
    """CREATE TABLE cross_profiles (
        profile_id TEXT PRIMARY KEY, source_profile_id TEXT NOT NULL,
        config_json TEXT NOT NULL, processed_through TEXT,
        snapshot_count INTEGER NOT NULL DEFAULT 0, last_completed_at TEXT
    )""",
    """CREATE TABLE cross_snapshots (
        profile_id TEXT NOT NULL, window_end TEXT NOT NULL, id TEXT NOT NULL UNIQUE,
        result_json TEXT NOT NULL, PRIMARY KEY(profile_id,window_end)
    )""",
    """CREATE TABLE cross_breakdown_events (
        profile_id TEXT NOT NULL, window_end TEXT NOT NULL, pair TEXT NOT NULL,
        id TEXT NOT NULL UNIQUE, event_json TEXT NOT NULL,
        PRIMARY KEY(profile_id,window_end,pair)
    )""",
    "CREATE INDEX cross_event_pair ON cross_breakdown_events(profile_id,pair,window_end)",
)
