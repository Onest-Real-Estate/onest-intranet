# Restore DocuSeal columns in the database after the OpenSign cutover was
# reverted in code. Migration state already expects DocuSeal fields (0006);
# only the live Postgres schema still has OpenSign columns.
# SQLite (tests) never had the OpenSign cutover — skip the data DDL there.

from django.db import migrations


RESTORE_DOCUSEAL_SQL = """
-- ContractTemplateVersion
ALTER TABLE contract_contracttemplateversion
    DROP COLUMN IF EXISTS opensign_template_id;
ALTER TABLE contract_contracttemplateversion
    ADD COLUMN IF NOT EXISTS docuseal_external_id
        varchar(120) DEFAULT '' NOT NULL;
ALTER TABLE contract_contracttemplateversion
    ADD COLUMN IF NOT EXISTS docuseal_template_id
        bigint NULL;

-- AgentContract
ALTER TABLE contract_agentcontract
    DROP COLUMN IF EXISTS opensign_document_id;
ALTER TABLE contract_agentcontract
    DROP COLUMN IF EXISTS opensign_signer_url;
ALTER TABLE contract_agentcontract
    ADD COLUMN IF NOT EXISTS docuseal_agent_submitter_slug
        varchar(120) DEFAULT '' NOT NULL;
ALTER TABLE contract_agentcontract
    ADD COLUMN IF NOT EXISTS docuseal_submission_id
        bigint NULL;
CREATE UNIQUE INDEX IF NOT EXISTS
    contract_agentcontract_docuseal_submission_id_key
    ON contract_agentcontract (docuseal_submission_id);

-- ContractSigningIntent
ALTER TABLE contract_contractsigningintent
    DROP COLUMN IF EXISTS opensign_document_id;
ALTER TABLE contract_contractsigningintent
    DROP COLUMN IF EXISTS opensign_signer_url;
ALTER TABLE contract_contractsigningintent
    ADD COLUMN IF NOT EXISTS docuseal_submission_id
        bigint NULL;
ALTER TABLE contract_contractsigningintent
    ADD COLUMN IF NOT EXISTS docuseal_submitter_slug
        varchar(120) DEFAULT '' NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS
    contract_contractsigningintent_docuseal_submission_id_key
    ON contract_contractsigningintent (docuseal_submission_id);

-- ContractSignature
ALTER TABLE contract_contractsignature
    DROP COLUMN IF EXISTS opensign_document_id;
ALTER TABLE contract_contractsignature
    DROP COLUMN IF EXISTS opensign_signer_url;
ALTER TABLE contract_contractsignature
    ADD COLUMN IF NOT EXISTS docuseal_submission_id
        bigint NOT NULL DEFAULT 0;
ALTER TABLE contract_contractsignature
    ALTER COLUMN docuseal_submission_id DROP DEFAULT;
ALTER TABLE contract_contractsignature
    ADD COLUMN IF NOT EXISTS docuseal_submitter_slug
        varchar(120) DEFAULT '' NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS
    contract_contractsignature_docuseal_submission_id_key
    ON contract_contractsignature (docuseal_submission_id);
UPDATE contract_contractsignature
    SET signature_method = 'docuseal_embedded'
    WHERE signature_method = 'opensign_embedded';
"""


def restore_docuseal_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(RESTORE_DOCUSEAL_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("contract", "0007_contracttemplateversion_field_layout"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunPython(
                    restore_docuseal_columns, migrations.RunPython.noop
                ),
            ],
        ),
    ]
