---
name: cost-check
description: Protect the $200 / 30-day Azure credit. Use at the start of every working session (daily cost log), before running any command that creates or starts a billable Azure or Databricks resource, and at the end of a session to confirm nothing is left running.
---

# Cost check

The whole budget is $200 for 30 days, target spend under $120. Storage is cheap;
compute and anything with an hourly minimum is what burns credit.

## 1. Start of session

Run these and show the result in a few lines:

```bash
az account show -o table                                   # right subscription?
az consumption usage list --start-date <first-day> --end-date <today> \
  --query "[].{name:instanceName, cost:pretaxCost}" -o table
az resource list --tag project=predictiq-azure -o table    # what exists
databricks clusters list                                   # anything running?
```

Then append one line to `docs/cost-log.md`:

```
| YYYY-MM-DD | total so far | change since last entry | what caused it | still running |
```

If anything is running that should not be, say so first, before any other work.
Commands and output shapes change; if one fails, check the current `az` docs
rather than guessing.

## 2. Before anything billable

Before a command that creates, starts, or scales something, show this block and
wait for an explicit "yes":

```
Creates:      <resource and size>
Billed how:   per hour while it exists | per use | per GB
Estimate:     <$ for how we plan to use it this month>
Stops when:   <auto-terminate / we delete it / never on its own>
Undo:         <exact delete command>
Tags:         project=predictiq-azure env=dev owner=<user>
```

Check prices against the Azure pricing page or calculator, not memory.

**Things that bill every hour just for existing** (extra care, delete when not
in use): VMs and their disks, all-purpose clusters, Event Hubs namespaces,
Postgres Flexible Server, AI Search Basic, Synapse dedicated pools, Fabric
capacity, NAT gateways, public IPs.

## 3. End of session

- `databricks clusters list`: nothing in RUNNING.
- `az resource list --tag project=predictiq-azure -o table`: only things we
  meant to keep (storage, Key Vault, the workspace itself).
- If a compute resource group is no longer needed today, offer to delete it.
  Deleting is the main cost control; recreating from IaC should be one command.

Never remove the subscription spending limit to make a job run.
