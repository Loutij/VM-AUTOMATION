#!/usr/bin/env python3
"""
Check BITS ISO download progress and auto-complete finished transfers.

Usage:
    python scripts/check_iso_downloads.py          # Check status
    python scripts/check_iso_downloads.py --loop    # Poll every 30s until done
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()


async def check_status(client) -> bool:
    """Check BITS status. Returns True if all done."""
    result = await client._execute(r"""
        $jobs = Get-BitsTransfer -ErrorAction SilentlyContinue
        if (-not $jobs) {
            Write-Output "NO_JOBS"
            return
        }
        foreach ($j in $jobs) {
            $pct = if ($j.BytesTotal -gt 0) { [math]::Round($j.BytesTransferred / $j.BytesTotal * 100, 1) } else { 0 }
            $sizeGB = [math]::Round($j.BytesTotal / 1GB, 2)
            $transferredGB = [math]::Round($j.BytesTransferred / 1GB, 2)

            # Auto-complete transferred jobs
            if ($j.JobState -eq 'Transferred') {
                Complete-BitsTransfer -BitsJob $j
                Write-Output "COMPLETED|$($j.DisplayName)|$sizeGB"
            } elseif ($j.JobState -eq 'Error') {
                $errMsg = $j.ErrorDescription
                Write-Output "ERROR|$($j.DisplayName)|$errMsg"
                # Retry
                Resume-BitsTransfer -BitsJob $j -Asynchronous -ErrorAction SilentlyContinue
            } else {
                Write-Output "PROGRESS|$($j.DisplayName)|$($j.JobState)|$pct|$transferredGB|$sizeGB"
            }
        }
    """, timeout=30)

    stdout = result.stdout or ""
    if "NO_JOBS" in stdout:
        print("Aucun telechargement BITS en cours.")
        return True

    all_done = True
    for line in stdout.strip().split("\n"):
        parts = line.strip().split("|")
        if not parts:
            continue

        if parts[0] == "COMPLETED":
            print(f"  TERMINE: {parts[1]} ({parts[2]} Go)")
        elif parts[0] == "ERROR":
            print(f"  ERREUR:  {parts[1]} -> {parts[2] if len(parts) > 2 else '?'}")
            all_done = False
        elif parts[0] == "PROGRESS" and len(parts) >= 6:
            name, state, pct, transferred, total = parts[1:6]
            bar_len = 30
            filled = int(float(pct) / 100 * bar_len)
            bar = "#" * filled + "-" * (bar_len - filled)
            print(f"  {name}: [{bar}] {pct}% ({transferred}/{total} Go) [{state}]")
            all_done = False

    # Space check
    result2 = await client._execute(r"""
        $g = Get-PSDrive -Name G
        Write-Output "$([math]::Round($g.Free / 1GB, 1))"
    """, timeout=15)
    if result2.stdout:
        print(f"\n  G: {result2.stdout.strip()} Go libre")

    return all_done


async def main(loop: bool = False):
    from src.integrations.hypervisors.hyperv_client import HyperVClient

    client = HyperVClient(
        host=os.getenv("HYPERV_HOST"),
        username=os.getenv("HYPERV_USER"),
        password=os.getenv("HYPERV_PASSWORD"),
        use_ssl=False,
    )

    if loop:
        print("=== Monitoring des telechargements (Ctrl+C pour arreter) ===\n")
        while True:
            done = await check_status(client)
            if done:
                print("\nTous les telechargements sont termines!")
                break
            print()
            await asyncio.sleep(30)
    else:
        await check_status(client)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Poll every 30s until done")
    args = parser.parse_args()
    try:
        asyncio.run(main(loop=args.loop))
    except KeyboardInterrupt:
        print("\nArret.")
