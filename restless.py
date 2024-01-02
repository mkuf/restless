#!/usr/bin/env python3

import os
import sys
import yaml
import json
import logging
import apprise
import optparse
import subprocess

###
### setup

# Parse arguments
usage = "%prog [options] <backupname|replicaname>"
opts = optparse.OptionParser(usage)
opts.add_option("-c", "--config",
                dest="configfile",
                default="restless.yaml",
                help="Path to config file. Default: ./restless.yaml")
opts.add_option("-m", "--mode",
                dest="mode",
                default="backup",
                help="Execution Mode. Either 'backup' or 'replication'. Default: backup")
(options, args) = opts.parse_args()

if len(args) != 1:
  opts.error("Incorrect number of argumens")

# Load Configfile
with open(options.configfile, "r") as file:
  cfg = yaml.safe_load(file)

# Set up apprise notifications
notifications = apprise.Apprise()
notifications.add(cfg["notifications"]["url"])

# Set up logging
logger = logging.getLogger('restless')
logger.setLevel(cfg["log"]["level"].upper())

fh = logging.FileHandler(cfg["log"]["location"])
ch = logging.StreamHandler()

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

logger.addHandler(fh)
logger.addHandler(ch)

class run():
  def normal(cmd):
    """Run a command"""
    logger.debug( "running command:\n+ " + cmd )

    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout, stderr = process.communicate()

    logger.info( "out:\n" + stdout.decode('utf-8') )

    if process.returncode != 0:
      logger.error(f"Failure during {cmd} :\n{stdout.decode('utf-8')}")
      raise Exception(stdout.decode('utf-8'))

    return stdout

  def required(cmd):
    """Run a command and send a notification if it fails"""
    if cmd:
      try:
        out = run.normal(cmd)
        return out
      except Exception as e:
        notifications.notify(title="restless: error", body=f"Error while running {cmd}:\n\n{str(e)}")
        sys.exit(1)
    else:
      logger.debug("no cmd given, skipping execution")

class restic():
  def export(vars):
    """Set environment Variables.

    Keyword arguments:
    vars -- dict of key value pairs that will be set as environment variables
    """
    logger.debug(vars)
    for key,value in vars.items():
      logger.debug(key + "=" + value)
      os.environ[key]=value

  def init(repo,password):
    """Initialize a restic Repository.

    Keyword arguments:
    repo -- value for RESTIC_REPOSITORY
    password -- restic password for the repository
    """
    try:
      cmd = ["restic", "init"]
      cmd.extend(["--repo", repo])

      restic.export({"RESTIC_PASSWORD": password})
      run.normal(' '.join(cmd))
    except Exception as e:
      if str("already exists") in str(e):
        logger.info("Repo already initialized.")
      else:
        notifications.notify(title="restless: error during init", body=str(e))
        raise e

  def snapshots(repo,password,tags):
    """List restic snapshots.
    Returns a list of dicts.

    Keyword arguments:
    repo -- value for RESTIC_REPOSITORY
    password -- restic password for the repository
    tags -- list of tags for that snapshots should be retrieved
    """
    cmd = ["restic", "snapshots"]
    cmd.extend(["--json"])
    cmd.extend(["--repo", repo])
    for tag in tags:
      cmd.extend(["--tag", tag])

    restic.export({"RESTIC_PASSWORD": password})
    out = run.required(' '.join(cmd))

    return json.loads(out.decode('utf8'))

  def backup(repo,password,tags,includes,excludes):
    """Create a backup.

    Keyword arguments:
    repo -- value for RESTIC_REPOSITORY
    password -- restic password for the repository
    tags -- list of tags for that snapshots should be retrieved
    includes -- list of files and directories that should be included
    excludes -- list of exclude patterns
    """
    cmd = [ "restic", "backup" ] 
    cmd.extend(includes)
    cmd.extend(["--repo", repo])
    for tag in tags:
      cmd.extend(["--tag", tag])
    for exclude in excludes:
      cmd.extend(["--exclude", exclude])

    restic.export({"RESTIC_PASSWORD": password})
    run.required(' '.join(cmd))

  def copy(from_repo,from_repo_password,to_repo,to_repo_password,snapshots):
    """Copy restic snapshots between repositories.

    Keyword arguments:
    from_repo -- value for RESTIC_REPOSITORY of the source repository
    from_repo_password -- restic password for the source repository
    to_repo -- value for RESTIC_REPOSITORY of the target repository
    to_repo_password -- restic password for the target repository
    snapshots -- list of snapshots that should be copied from source to target repo
    """
    cmd = ["restic", "copy"]
    cmd.extend(["--from-repo", from_repo])
    cmd.extend(["--repo", to_repo])
    cmd.extend(snapshots)

    restic.export({
      "RESTIC_FROM_PASSWORD": from_repo_password,
      "RESTIC_PASSWORD": to_repo_password
    })
    run.required(' '.join(cmd))

  def forget(repo,password,tags,retention={},snapshots={}):
    """Remove snapshots.

    Keyword arguments:
    repo -- value for RESTIC_REPOSITORY
    password -- restic password for the repository
    tags -- list of tags for that snapshots should be retrieved
    retention -- list of keep options to apply during restic forget
    snapshots -- list of snapshots to remove
    """
    cmd = ["restic", "forget"]
    cmd.extend(retention)
    cmd.extend(["--prune"])
    cmd.extend(["--group-by", "host"])
    cmd.extend(["--repo", repo])
    for tag in tags:
      cmd.extend(["--tag", tag])
    cmd.extend(snapshots)

    restic.export({"RESTIC_PASSWORD": password})
    run.required(' '.join(cmd))

###
### main
match options.mode:
  case "backup":
    logger.info('Starting Backup')

    run.required(cfg["backups"][args[0]].get("scripts",{}).get("pre"))
    restic.export(cfg["repos"][cfg["backups"][args[0]]["repo"]].get("env", {}))
    restic.init(
      repo=cfg["repos"][cfg["backups"][args[0]]["repo"]]["repository"],
      password=cfg["repos"][cfg["backups"][args[0]]["repo"]]["password"]
    )
    restic.backup(
      repo=cfg["repos"][cfg["backups"][args[0]]["repo"]]["repository"],
      password=cfg["repos"][cfg["backups"][args[0]]["repo"]]["password"],
      tags=[ "restless/" + args[0] ],
      includes=cfg["backups"][args[0]]["include"],
      excludes=cfg["backups"][args[0]].get("exclude",[])
    )
    restic.forget(
      repo=cfg["repos"][cfg["backups"][args[0]]["repo"]]["repository"],
      password=cfg["repos"][cfg["backups"][args[0]]["repo"]]["password"],
      tags=[ "restless/" + args[0] ],
      retention=cfg["backups"][args[0]]["retention"]
    )
    run.required(cfg["backups"][args[0]].get("scripts",{}).get("post"))

  case "replication":
    logger.info('Starting Replication')

    ## Prep Source
    restic.export(cfg["repos"][cfg["replication"][args[0]]["from"]].get("env", {}))
    restic.init(
      repo=cfg["repos"][cfg["replication"][args[0]]["from"]]["repository"],
      password=cfg["repos"][cfg["replication"][args[0]]["from"]]["password"]
    )

    ## Build list of snapshots to copy from source
    snaps_to_sync = list()
    for include in cfg["replication"][args[0]]["include"]:
      snaps = restic.snapshots(
        repo=cfg["repos"][cfg["replication"][args[0]]["from"]]["repository"],
        password=cfg["repos"][cfg["replication"][args[0]]["from"]]["password"],
        tags=["restless/" + include["backup"] ]
      )
      logger.debug(str(snaps))

      for i in range(1,include["syncLast"]+1):
        snaps_to_sync.append(snaps[-abs(i)]["short_id"])
    logger.info("Snaps to sync: " + str(snaps_to_sync))

    ## Copy Snapshots
    restic.export({} | cfg["repos"][cfg["replication"][args[0]]["from"]].get("env",{}) | cfg["repos"][cfg["replication"][args[0]]["to"]].get("env",{}))
    restic.init(
      repo=cfg["repos"][cfg["replication"][args[0]]["to"]]["repository"],
      password=cfg["repos"][cfg["replication"][args[0]]["to"]]["password"]
    )
    restic.copy(
      from_repo=cfg["repos"][cfg["replication"][args[0]]["from"]]["repository"],
      from_repo_password=cfg["repos"][cfg["replication"][args[0]]["from"]]["password"],
      to_repo=cfg["repos"][cfg["replication"][args[0]]["to"]]["repository"],
      to_repo_password=cfg["repos"][cfg["replication"][args[0]]["to"]]["password"],
      snapshots=snaps_to_sync
    )

    for include in cfg["replication"][args[0]]["include"]:
      restic.forget(
        repo=cfg["repos"][cfg["replication"][args[0]]["to"]]["repository"],
        password=cfg["repos"][cfg["replication"][args[0]]["to"]]["password"],
        tags=[ "restless/" + include["backup"] ],
        retention=include["retention"]
      )

  case _:
    logger.critical("Mode " + options.mode + " not supported")
    notifications.notify(title="restless: critical error", body="Unsupported Mode has been requested.")
    sys.exit(1)
