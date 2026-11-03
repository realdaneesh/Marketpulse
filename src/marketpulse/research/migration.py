"""Explicit opt-in migration; opening an API does not install research tables."""

import sqlite3

STATEMENTS = (
    """CREATE TABLE research_experiments (
       seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
       experiment_json TEXT NOT NULL, inputs_json TEXT NOT NULL, results_json TEXT)""",
    """CREATE TABLE research_evaluations (
       experiment_id TEXT NOT NULL, position INTEGER NOT NULL, result_json TEXT NOT NULL,
       PRIMARY KEY(experiment_id,position))""",
    """CREATE TABLE research_metrics (
       experiment_id TEXT NOT NULL, position INTEGER NOT NULL, result_json TEXT NOT NULL,
       PRIMARY KEY(experiment_id,position))""",
    """CREATE TABLE research_change_points (
       seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
       experiment_id TEXT NOT NULL, result_json TEXT NOT NULL)""",
    """CREATE TABLE research_sequences (
       experiment_id TEXT NOT NULL, position INTEGER NOT NULL, result_json TEXT NOT NULL,
       PRIMARY KEY(experiment_id,position))""",
    """CREATE TABLE research_discoveries (
       seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
       experiment_id TEXT NOT NULL, result_json TEXT NOT NULL)""",
    "CREATE INDEX research_changes_experiment ON research_change_points(experiment_id,seq)",
    "CREATE INDEX research_discoveries_experiment ON research_discoveries(experiment_id,seq)",
)


def migrate(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (3, 4):
            raise RuntimeError("Research migration requires schema 3 or 4")
        if version == 3:
            for statement in STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version=4")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
