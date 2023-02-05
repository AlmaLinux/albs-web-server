import datetime
import os
import sys
import uuid

from sqlalchemy import select


sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.database import PulpSession, SyncSession
from alws.models import Build, BuildTask, BuildTaskArtifact
from alws.pulp_models import CoreArtifact, CoreContentArtifact


def main():
    first_subq = (
        select(Build.id)
        # commit date that brings wrong cas_hashes
        .where(Build.created_at >= datetime.datetime(2022, 10, 30))
        .scalar_subquery()
    )
    second_subq = (
        select(BuildTask.id).where(BuildTask.build_id.in_(first_subq)).scalar_subquery()
    )
    query = select(BuildTaskArtifact).where(
        BuildTaskArtifact.build_task_id.in_(second_subq),
        BuildTaskArtifact.cas_hash.is_not(None),
        BuildTaskArtifact.type == "rpm",
    )
    with SyncSession() as session, PulpSession() as pulp_session, session.begin():
        alma_artifacts_mapping = {}
        for artifact in session.execute(query).scalars().all():
            key = uuid.UUID(artifact.href.split("/")[-2])
            if key in alma_artifacts_mapping:
                alma_artifacts_mapping[key].append(artifact)
                continue
            alma_artifacts_mapping[key] = [artifact]
        query = select(CoreContentArtifact).where(
            CoreContentArtifact.content_id.in_(list(alma_artifacts_mapping))
        )
        pulp_artifacts_mapping = {
            record.artifact_id: record.content_id
            for record in pulp_session.execute(query).scalars().all()
        }
        query = select(CoreArtifact).where(
            CoreArtifact.pulp_id.in_(list(pulp_artifacts_mapping))
        )
        for pulp_artifact in pulp_session.execute(query).scalars().all():
            alma_artifact_href = pulp_artifacts_mapping[pulp_artifact.pulp_id]
            alma_artifacts = alma_artifacts_mapping[alma_artifact_href]
            for alma_artifact in alma_artifacts:
                if alma_artifact.cas_hash == pulp_artifact.sha256:
                    continue
                alma_artifact.cas_hash = pulp_artifact.sha256
        session.commit()


if __name__ == "__main__":
    main()
