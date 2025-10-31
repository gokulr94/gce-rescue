"""Simple GCE Rescue - Just make it work.

No fancy error handling, logging, or progress bars.
Just the core rescue and restore operations.

After this works, we'll add the nice-to-haves.
"""

import time
import google.auth
from googleapiclient import discovery


# Startup script that auto-mounts the original disk
# This runs when the rescue VM boots
STARTUP_SCRIPT = """#!/bin/bash
# Change hostname to indicate rescue mode
sed -i "s/$(hostname)/$(hostname)-rescue/g" /etc/hosts
hostname $(hostname)-rescue

# Wait for original disk and mount it
disk=DISK_NAME_PLACEHOLDER
mkdir -p /mnt/sysroot

# Wait for disk to appear
while [ ! -e /dev/disk/by-id/google-${disk} ]; do
    sleep 5
done

# Find filesystem and mount
disk_p=$(lsblk -rf /dev/disk/by-id/google-${disk} | egrep -i 'ext[3-4]|xfs|microsoft' | head -1)
if [ -n "$disk_p" ]; then
    mount /dev/${disk_p%% *} /mnt/sysroot
    # Mount proc, sys, dev for chroot
    [ -d /mnt/sysroot/proc ] && mount -t proc proc /mnt/sysroot/proc
    [ -d /mnt/sysroot/sys ] && mount -t sysfs sys /mnt/sysroot/sys
    [ -d /mnt/sysroot/dev ] && mount -o bind /dev /mnt/sysroot/dev
fi
"""


def get_client(project=None):
    """Get authenticated compute client."""
    creds, default_project = google.auth.default()
    compute = discovery.build('compute', 'v1', credentials=creds, cache_discovery=False)
    project = project or default_project
    return compute, project


def rescue_vm(project, zone, vm_name):
    """Enter rescue mode - simple version."""

    compute, project = get_client(project)
    timestamp = int(time.time())

    print(f"Rescuing VM: {vm_name}")

    # Get VM info
    print("→ Getting VM info...")
    vm = compute.instances().get(project=project, zone=zone, instance=vm_name).execute()

    # Find boot disk
    boot_disk = None
    for disk in vm['disks']:
        if disk.get('boot'):
            boot_disk = {
                'name': disk['source'].split('/')[-1],
                'device': disk['deviceName']
            }
            break

    print(f"  Boot disk: {boot_disk['name']}")

    # Stop VM
    print("→ Stopping VM...")
    compute.instances().stop(project=project, zone=zone, instance=vm_name).execute()

    # Wait for stop
    while True:
        vm = compute.instances().get(project=project, zone=zone, instance=vm_name).execute()
        if vm['status'] == 'TERMINATED':
            break
        time.sleep(5)

    print("  VM stopped")

    # Create rescue disk
    rescue_disk_name = f"rescue-disk-{timestamp}"
    print(f"→ Creating rescue disk: {rescue_disk_name}")

    # Prepare startup script with actual disk name
    startup_script = STARTUP_SCRIPT.replace('DISK_NAME_PLACEHOLDER', boot_disk['name'])

    disk_body = {
        'name': rescue_disk_name,
        'sizeGb': '10',
        'type': f'projects/{project}/zones/{zone}/diskTypes/pd-standard',
        'sourceImage': 'projects/debian-cloud/global/images/family/debian-11'
    }

    compute.disks().insert(project=project, zone=zone, body=disk_body).execute()

    # Wait for disk creation
    while True:
        try:
            disk = compute.disks().get(project=project, zone=zone, disk=rescue_disk_name).execute()
            if disk['status'] == 'READY':
                break
        except:
            pass
        time.sleep(5)

    print("  Rescue disk created")

    # Detach boot disk
    print("→ Detaching boot disk...")
    compute.instances().detachDisk(
        project=project,
        zone=zone,
        instance=vm_name,
        deviceName=boot_disk['device']
    ).execute()
    time.sleep(3)

    # Attach rescue disk as boot
    print("→ Attaching rescue disk as boot...")
    attach_body = {
        'source': f'projects/{project}/zones/{zone}/disks/{rescue_disk_name}',
        'boot': True,
        'autoDelete': False
    }
    compute.instances().attachDisk(
        project=project,
        zone=zone,
        instance=vm_name,
        body=attach_body
    ).execute()
    time.sleep(3)

    # Set startup script metadata
    print("→ Setting startup script...")
    metadata = {
        'items': [
            {'key': 'startup-script', 'value': startup_script},
            {'key': 'rescue-mode', 'value': str(timestamp)}
        ]
    }
    compute.instances().setMetadata(
        project=project,
        zone=zone,
        instance=vm_name,
        body={'fingerprint': vm['metadata']['fingerprint'], **metadata}
    ).execute()
    time.sleep(2)

    # Start VM
    print("→ Starting VM in rescue mode...")
    compute.instances().start(project=project, zone=zone, instance=vm_name).execute()

    # Wait for start
    while True:
        vm = compute.instances().get(project=project, zone=zone, instance=vm_name).execute()
        if vm['status'] == 'RUNNING':
            break
        time.sleep(5)

    # Re-attach original disk as secondary
    print("→ Re-attaching original disk...")
    time.sleep(10)  # Wait for VM to fully boot

    attach_body = {
        'source': f'projects/{project}/zones/{zone}/disks/{boot_disk["name"]}',
        'boot': False,
        'autoDelete': False
    }
    compute.instances().attachDisk(
        project=project,
        zone=zone,
        instance=vm_name,
        body=attach_body
    ).execute()

    print(f"\n✅ VM is now in rescue mode!")
    print(f"   SSH: gcloud compute ssh {vm_name} --zone={zone}")
    print(f"   Original disk will be mounted at: /mnt/sysroot")


def restore_vm(project, zone, vm_name):
    """Exit rescue mode - restore original boot disk."""

    compute, project = get_client(project)

    print(f"Restoring VM: {vm_name}")

    # Get VM info
    print("→ Getting VM info...")
    vm = compute.instances().get(project=project, zone=zone, instance=vm_name).execute()

    # Find rescue disk and original disk
    rescue_disk = None
    original_disk = None

    for disk in vm['disks']:
        disk_name = disk['source'].split('/')[-1]
        if 'rescue-disk' in disk_name:
            rescue_disk = {'name': disk_name, 'device': disk['deviceName']}
        elif disk.get('boot'):
            # This shouldn't be boot if in rescue mode, but check anyway
            pass
        else:
            original_disk = {'name': disk_name, 'device': disk['deviceName']}

    if not original_disk:
        print("  Cannot find original disk!")
        return

    print(f"  Original disk: {original_disk['name']}")
    print(f"  Rescue disk: {rescue_disk['name']}")

    # Stop VM
    print("→ Stopping VM...")
    compute.instances().stop(project=project, zone=zone, instance=vm_name).execute()

    while True:
        vm = compute.instances().get(project=project, zone=zone, instance=vm_name).execute()
        if vm['status'] == 'TERMINATED':
            break
        time.sleep(5)

    print("  VM stopped")

    # Detach rescue disk
    print("→ Detaching rescue disk...")
    compute.instances().detachDisk(
        project=project,
        zone=zone,
        instance=vm_name,
        deviceName=rescue_disk['device']
    ).execute()
    time.sleep(2)

    # Detach original disk
    print("→ Detaching original disk...")
    compute.instances().detachDisk(
        project=project,
        zone=zone,
        instance=vm_name,
        deviceName=original_disk['device']
    ).execute()
    time.sleep(2)

    # Re-attach original disk as boot
    print("→ Re-attaching original disk as boot...")
    attach_body = {
        'source': f'projects/{project}/zones/{zone}/disks/{original_disk["name"]}',
        'boot': True,
        'autoDelete': False
    }
    compute.instances().attachDisk(
        project=project,
        zone=zone,
        instance=vm_name,
        body=attach_body
    ).execute()
    time.sleep(3)

    # Remove rescue metadata
    print("→ Removing rescue metadata...")
    vm = compute.instances().get(project=project, zone=zone, instance=vm_name).execute()
    metadata = vm['metadata'].copy()
    metadata['items'] = [item for item in metadata.get('items', [])
                         if item['key'] not in ['rescue-mode', 'startup-script']]
    compute.instances().setMetadata(
        project=project,
        zone=zone,
        instance=vm_name,
        body=metadata
    ).execute()
    time.sleep(2)

    # Start VM
    print("→ Starting VM...")
    compute.instances().start(project=project, zone=zone, instance=vm_name).execute()

    while True:
        vm = compute.instances().get(project=project, zone=zone, instance=vm_name).execute()
        if vm['status'] == 'RUNNING':
            break
        time.sleep(5)

    print("  VM started")

    # Delete rescue disk
    print(f"→ Deleting rescue disk: {rescue_disk['name']}...")
    compute.disks().delete(
        project=project,
        zone=zone,
        disk=rescue_disk['name']
    ).execute()

    print(f"\n✅ VM restored to normal mode!")
    print(f"   SSH: gcloud compute ssh {vm_name} --zone={zone}")


# Quick test function
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 4:
        print("Usage:")
        print("  Rescue:  python simple_rescue.py rescue <zone> <vm-name>")
        print("  Restore: python simple_rescue.py restore <zone> <vm-name>")
        sys.exit(1)

    action = sys.argv[1]
    zone = sys.argv[2]
    vm_name = sys.argv[3]

    if action == 'rescue':
        rescue_vm(None, zone, vm_name)
    elif action == 'restore':
        restore_vm(None, zone, vm_name)
    else:
        print(f"Unknown action: {action}")
