#!/bin/bash
echo "Fetching running workflows..."
temporal workflow list --query "ExecutionStatus='Running'" | awk '/Running[[:space:]]+[^\s]+Workflow/ {print $2}' > /tmp/wfs_to_kill.txt
count=$(wc -l < /tmp/wfs_to_kill.txt)
echo "Found $count workflows to terminate."

while IFS= read -r wfid; do
  # Trim potential surrounding space or odd characters
  clean_id=$(echo "$wfid" | tr -d '\r' | xargs)
  if [ -n "$clean_id" ]; then
    echo "Terminating: $clean_id"
    temporal workflow terminate --workflow-id "$clean_id" --reason "Purging legacy backlog"
  fi
done < /tmp/wfs_to_kill.txt

echo "Backlog Purge Completed."
