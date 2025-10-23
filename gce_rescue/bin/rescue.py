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

"""Main script to be used to set/reset rescue mode."""

from datetime import datetime
import logging
from typing import Any, Dict

from gce_rescue import messages
from gce_rescue.config import process_args, set_configs
from gce_rescue.gce import Instance
from gce_rescue.tasks.actions import call_tasks
from gce_rescue.utils import read_input, set_logging


logger = logging.getLogger(__name__)


def _confirm_action(prompt: str) -> None:
  """Request user confirmation before proceeding."""
  read_input(msg=prompt)


def main() -> None:
  """Main script function."""
  parser = process_args()
  args = parser.parse_args()
  set_configs(args)

  set_logging(vm_name=args.name)

  parse_kwargs: Dict[str, Any] = {
      'zone': args.zone,
      'name': args.name,
  }

  if args.project:
    parse_kwargs['project'] = args.project

  try:
    vm = Instance(test_mode=False, **parse_kwargs)
  except Exception as err:  # pylint: disable=broad-except
    logger.exception('Failed to initialise instance %s', args.name)
    raise SystemExit(1) from err

  rescue_status: Dict[str, Any] = vm.rescue_mode_status or {}
  rescue_on = rescue_status.get('rescue-mode', False)
  if not rescue_on:
    if not args.force:
      info = (f'This option will boot the instance {vm.name} in '
              'RESCUE MODE. \nIf your instance is running it will be rebooted. '
              '\nDo you want to continue [y/N]: ')
      _confirm_action(info)

    logger.info('Starting rescue mode for VM %s', vm.name)
    # save in the log file current configuration of the VM as backup.
    logger.info('RESTORE#%s\n', vm.data)
    action = 'set_rescue_mode'
    msg = messages.tip_connect_ssh(vm)

  else:
    try:
      rescue_ts_raw = rescue_status['ts']
      rescue_ts = int(rescue_ts_raw)
    except (KeyError, TypeError, ValueError) as err:
      logger.exception('Unable to determine rescue timestamp for VM %s',
                       vm.name)
      raise SystemExit(1) from err

    rescue_date = datetime.fromtimestamp(rescue_ts)

    if not args.force:
      info = (f'The instance "{vm.name}" is currently configured '
              f'to boot as rescue mode since {rescue_date}.\nWould you like to'
              ' restore the original configuration ? [y/N]: ')
      _confirm_action(info)

    has_snapshot = vm.snapshot
    logger.info('Restoring VM %s from rescue mode set at %s', vm.name,
                rescue_date)
    if has_snapshot:
      logger.info('Snapshot detected for VM %s during rescue mode.', vm.name)
    action = 'reset_rescue_mode'
    msg = messages.tip_restore_disk(vm, snapshot=has_snapshot)

  try:
    call_tasks(vm=vm, action=action)
  except Exception as err:  # pylint: disable=broad-except
    logger.exception('Failed to execute %s for VM %s', action, vm.name)
    raise SystemExit(1) from err

  logger.info('%s', msg)


if __name__ == '__main__':
  main()
