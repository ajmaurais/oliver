import argparse
import json

from typing import Dict

from ..lib import api, errors, reporting, utils, workflows as _workflows
from ..lib.parsing import parse_workflow_inputs


def call(args: Dict):
    """Execute the subcommand.
    
    Args:
        args (Dict): Arguments parsed from the command line.
    """

    cromwell = api.CromwellAPI(
        server=args["cromwell_server"], version=args["cromwell_api_version"]
    )

    workflow = None
    show_only_aborted_and_failed = not args["all"]

    if args["scope"] == "workflow":
        workflows = _workflows.get_workflows(
            cromwell,
            cromwell_workflow_uuid=args["predicate"],
            opt_into_reporting_failed_jobs=show_only_aborted_and_failed,
            opt_into_reporting_aborted_jobs=show_only_aborted_and_failed,
        )
    elif args["scope"] == "batch":
        workflows = _workflows.get_workflows(
            cromwell,
            batches=int(args["predicate"]),
            batch_interval_mins=args["batch_interval_mins"],
            relative_batching=True,
            opt_into_reporting_failed_jobs=show_only_aborted_and_failed,
            opt_into_reporting_aborted_jobs=show_only_aborted_and_failed,
        )
    else:
        errors.report(
            f"Unsupported scope: {args['scope']}!",
            fatal=True,
            exitcode=errors.ERROR_INVALID_INPUT,
        )

    if not args.get("dry_run"):
        if not args["yes"] and not utils.ask_boolean_question(
            f"Wishing to resubmit {len(workflows)} jobs. Continue?"
        ) in ["yes", "y"]:
            errors.report("User cancelled submission.", fatal=True, exitcode=0)

    results = []
    for w in workflows:
        metadata = cromwell.get_workflows_metadata(w["id"])

        workflowUrl = metadata.get("submittedFiles", {}).get("workflowUrl", {})
        workflowInputs = metadata.get("submittedFiles", {}).get("inputs", {})
        workflowOptions = metadata.get("submittedFiles", {}).get("options", {})
        workflowLabels = metadata.get("submittedFiles", {}).get("labels", {})
        workflow_args = {}
        (
            workflow_args["workflowInputs"],
            workflow_args["workflowOptions"],
            workflow_args["workflowLabels"],
        ) = parse_workflow_inputs(
            args.get("workflowInputs"),
            inputs=json.loads(workflowInputs),
            options=json.loads(workflowOptions),
            labels=json.loads(workflowLabels),
        )

        if args.get("dry_run"):
            for key, value in workflow_args.items():
                print(f"{key} = {value}")
            continue

        results.append(
            cromwell.post_workflows(
                workflowUrl=workflowUrl,
                workflowInputs=workflow_args["workflowInputs"],
                workflowOptions=workflow_args["workflowOptions"],
                labels=workflow_args["workflowLabels"],
            )
        )

    reporting.print_dicts_as_table(results)


def register_subparser(subparser: argparse._SubParsersAction):
    """Registers a subparser for the current command.
    
    Args:
        subparser (argparse._SubParsersAction): Subparsers action.
    """

    subcommand = subparser.add_parser(
        "retry",
        aliases=["re"],
        help="Resubmit a workflow with the same parameters. By default, only restarts workflows which are 'Failed' or 'Aborted'.",
    )
    subcommand.add_argument(
        "scope", help="Currently `workflow` and `batch` are supported."
    )
    subcommand.add_argument(
        "predicate",
        help="If scope is `workflow`, the workflow's UUID. If scope is `batch`, N batches ago to restart.",
    )
    subcommand.add_argument(
        "workflowInputs",
        nargs="*",
        help="JSON files or key=value pairs to add to inputs, options, or labels (see documentation for more information).",
    )
    subcommand.add_argument(
        "-a",
        "--all",
        help="Restart all workflows, not just 'Failed' and 'Aborted' workflows.",
        default=False,
        action="store_true",
    )
    subcommand.add_argument(
        "--batch-interval-mins",
        help="Split batches by any two jobs separated by N minutes.",
        type=int,
    )
    subcommand.add_argument(
        "-d",
        "--dry-run",
        help="Print what would be submitted rather than actually submitting.",
        default=False,
        action="store_true",
    )
    subcommand.add_argument(
        "-y",
        "--yes",
        help="Instead of prompting, go ahead and resubmit the jobs.",
        default=False,
        action="store_true",
    )
    subcommand.add_argument(
        "--grid-style",
        help="Any valid `tablefmt` for python-tabulate.",
        default="fancy_grid",
    )
    subcommand.set_defaults(func=call)
