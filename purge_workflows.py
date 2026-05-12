import subprocess
import re

def main():
    # Get all running workflows
    try:
        res = subprocess.run(["docker", "exec", "ks_temporal", "temporal", "workflow", "list", "--query", "ExecutionStatus='Running'"], capture_output=True, text=True, check=True)
        output = res.stdout
        
        # Extract workflow IDs
        # Lines look like: "  Running  enr-399c49a6...         EnrichmentWorkflow         1 day ago  "
        pattern = re.compile(r"Running\s+([^\s]+)\s+\w+Workflow")
        ids = pattern.findall(output)
        
        print(f"Found {len(ids)} running workflows to terminate.")
        
        for wf_id in ids:
            wf_id = wf_id.strip()
            print(f"Terminating {wf_id}...")
            subprocess.run(["docker", "exec", "ks_temporal", "temporal", "workflow", "terminate", "--workflow-id", wf_id], capture_output=True)
            
        print("Force Cleanup Complete.")
    except Exception as e:
        print(f"Error executing purge: {e}")

if __name__ == "__main__":
    main()
