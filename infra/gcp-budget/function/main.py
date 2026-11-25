"""Budget hard cap: turns off billing on the project when actual spend reaches the budget.

Triggered by the budget's Pub/Sub notifications (sent several times a day). Only actual spend
(costAmount) counts, never the forecast. Turning billing off stops every paid service in the
project, running VMs included; re-enable with `gcloud billing projects link`.

DRY_RUN=true logs what it would do without changing anything.
"""

import base64
import json
import os

import functions_framework
from google.cloud import billing_v1
from google.cloud import resourcemanager_v3
from google.iam.v1 import iam_policy_pb2

PROJECT_ID = os.environ["TARGET_PROJECT_ID"]
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
NEEDED = "resourcemanager.projects.deleteBillingAssignment"


def _can_disable() -> bool:
    req = iam_policy_pb2.TestIamPermissionsRequest(resource=f"projects/{PROJECT_ID}", permissions=[NEEDED])
    return NEEDED in resourcemanager_v3.ProjectsClient().test_iam_permissions(request=req).permissions


@functions_framework.cloud_event
def stop_billing(cloud_event):
    data = json.loads(base64.b64decode(cloud_event.data["message"]["data"]).decode())
    cost, budget = float(data["costAmount"]), float(data["budgetAmount"])
    cur = data.get("currencyCode", "")
    print(f"budget notice: spent {cost:.2f} of {budget:.2f} {cur} (dry_run={DRY_RUN}, can_disable={_can_disable()})")
    if cost < budget:
        return

    if DRY_RUN:
        print(f"DRY RUN: would disable billing on {PROJECT_ID}")
        return
    # Unlinking an already-unlinked project is a no-op, so repeated notices are harmless.
    billing_v1.CloudBillingClient().update_project_billing_info(
        name=f"projects/{PROJECT_ID}", project_billing_info=billing_v1.ProjectBillingInfo(billing_account_name="")
    )
    print(f"BUDGET REACHED: billing disabled on {PROJECT_ID}")
