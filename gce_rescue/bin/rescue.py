#!/usr/bin/env python3

# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" Main script to be used to set/reset rescue mode. """

from datetime import datetime
import logging

from gce_rescue.config import process_args, set_configs
from gce_rescue import messages
from gce_rescue.gce import Instance
from gce_rescue.tasks.actions import call_tasks
from gce_rescue.utils import read_input, set_logging

def main():
  """ Main script function. """
  # Process command line arguments and set up configurations.
  parser = process_args()
  args = parser.parse_args()
  set_configs(args)

  # Configure logging for the script.
  set_logging(vm_name=args.name)

  # Prepare arguments for creating the Instance object.
  instance_kwargs = {
      'zone': args.zone,
      'name': args.name,
  }
  if args.project:
    instance_kwargs['project'] = args.project

  # Create an Instance object to interact with the VM.
  vm = Instance(test_mode=False, **instance_kwargs)
  rescue_on = vm.rescue_mode_status['rescue-mode']

  # Check if the VM is already in rescue mode.
  if rescue_on:
    # If in rescue mode, prepare to restore the original configuration.
    rescue_ts = vm.rescue_mode_status['ts']
    rescue_date = datetime.fromtimestamp(int(rescue_ts))
    confirmation_msg = (
        f'The instance "{vm.name}" is currently configured '
        f'to boot as rescue mode since {rescue_date}.\nWould you like to'
        ' restore the original configuration ? [y/N]: ')
    start_msg = 'Restoring VM...'
    action = 'reset_rescue_mode'
    success_msg = messages.tip_restore_disk(vm, snapshot=vm.snapshot)
  else:
    # If not in rescue mode, prepare to enable it.
    confirmation_msg = (
        f'This option will boot the instance {vm.name} in '
        'RESCUE MODE. \nIf your instance is running it will be rebooted. '
        '\nDo you want to continue [y/N]: ')
    start_msg = 'Starting...'
    # Save the current VM configuration as a backup before making changes.
    logging.info('RESTORE#%s\n', vm.data)
    action = 'set_rescue_mode'
    success_msg = messages.tip_connect_ssh(vm)

  # If the --force flag is not used, ask for user confirmation.
  if not args.force:
    read_input(msg=confirmation_msg)

  # Execute the chosen action (set or reset rescue mode).
  print(start_msg)
  call_tasks(vm=vm, action=action)
  print(success_msg)




if __name__ == '__main__':
  main()
