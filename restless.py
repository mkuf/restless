#!/usr/bin/env python3

import os
import sys
import yaml
import logging
import apprise
import optparse
import subprocess

###
### setup

# Parse arguments
opts = optparse.OptionParser()
opts.add_option("-c", "--config", dest="configfile", default="restless.yaml")
opts.add_option("-m", "--mode", dest="mode", default="backup")
(options, args) = opts.parse_args()

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
    logger.debug( "running command:\n+ " + cmd )

    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout, stderr = process.communicate()

    logger.debug( "out:\n" + stdout.decode('utf-8') )

    if process.returncode != 0:
      logger.error(f"Failure during {cmd} :\n{stdout.decode('utf-8')}")
      raise Exception(stdout.decode('utf-8'))

  def required(cmd):
    if cmd:
      try:
        run.normal(cmd)
      except Exception as e:
        notifications.notify(title="restless: error", body=f"Error while running {cmd}:\n\n{str(e)}")
        sys.exit(1)
    else:
      logger.debug("no cmd given, skipping execution")

class restic():
  def export(vars):
    logger.debug(vars)
    for key,value in vars.items():
      logger.debug(key + "=" + value)
      os.environ[key]=value

  def init(repo,password):
    try:
      cmd = ["restic", "init"]
      cmd.extend(["--repo", repo])

      os.environ["RESTIC_PASSWORD"] = password
      run.normal(' '.join(cmd))
      del os.environ["RESTIC_PASSWORD"]

    except Exception as e:
      if not str("already exists") in str(e):
        notifications.notify(title="restless: error during init", body=str(e))
        sys.exit(1)
        raise e

  def backup(repo,password,tags,includes,excludes):
    cmd = [ "restic", "backup" ] 
    cmd.extend(includes)
    cmd.extend(["--repo", repo])
    for tag in tags:
      cmd.extend(["--tag", tag])
    for exclude in excludes:
      cmd.extend(["--exclude", exclude])

    os.environ["RESTIC_PASSWORD"] = password
    run.required(' '.join(cmd))
    del os.environ["RESTIC_PASSWORD"]

  def forget(repo,password,tags,retention):
    cmd = ["restic", "forget"]
    cmd.extend(retention)
    cmd.extend(["--group-by", "host"])
    cmd.extend(["--repo", repo])
    for tag in tags:
      cmd.extend(["--tag", tag])

    os.environ["RESTIC_PASSWORD"] = password
    run.required(' '.join(cmd))
    del os.environ["RESTIC_PASSWORD"]

###
### main
match options.mode:
  case "backup":
    logger.info('Starting Backup')

    restic.export(cfg["repos"][cfg["backups"][args[0]]["repo"]].get("env", {}))
    restic.init(
      repo=cfg["repos"][cfg["backups"][args[0]]["repo"]]["repository"],
      password=cfg["repos"][cfg["backups"][args[0]]["repo"]]["password"]
    )
    run.required(cfg["backups"][args[0]]["scripts"].get("pre"))
    restic.backup(
      repo=cfg["repos"][cfg["backups"][args[0]]["repo"]]["repository"],
      password=cfg["repos"][cfg["backups"][args[0]]["repo"]]["password"],
      tags=[ "restless/" + args[0] ],
      includes=cfg["backups"][args[0]]["include"],
      excludes=cfg["backups"][args[0]]["exclude"]
    )
    restic.forget(
      repo=cfg["repos"][cfg["backups"][args[0]]["repo"]]["repository"],
      password=cfg["repos"][cfg["backups"][args[0]]["repo"]]["password"],
      tags=[ "restless/" + args[0] ],
      retention=cfg["backups"][args[0]]["retention"]
    )
    run.required(cfg["backups"][args[0]]["scripts"].get("post"))

  case "replica":
    logger.info('Starting Replication')
  case _:
    logger.critical("Mode " + options.mode + " not supported")
    notifications.notify(title="restless: critical error", body="Unsupported Mode has been requested.")
    sys.exit(1)