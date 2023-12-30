#!/usr/bin/env python3

import os
import sys
import json
import yaml
import restic
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

def runScript(backup,stage):
  try:
    cmd = cfg["backups"][backup]["scripts"][stage]
    try:
      logger.info("Running " + stage + " script for " + backup)
      logger.debug(cmd)
      subprocess.run(cmd, shell=True, check=True)
    except:
      logger.error(stage + " Script for " + backup + " failed.")
      notifications.notify(title="restless: error", body=stage + " Script for " + backup + " failed.")
      sys.exit(1)
  except KeyError:
    logger.debug("No " + stage + " script set for " + backup)

def exportResticVars(repo):
  for key,value in cfg["repos"][repo]["vars"].items():
    logger.debug(key + "=" + value)
    os.environ[key]=value

def resticInit():
  try:
    restic.init()
  except restic.errors.ResticFailedError as e:
    if not str("already exists") in str(e):
      logger.critical("Failure during restic init")
      notifications.notify(title="restless: critical error", body="Restic Init failed: " + str(e) )
      raise e

###
### main
match options.mode:
  case "backup":
    logger.info('Starting Backup')

    # Run pre script
    runScript(backup=args[0],stage="pre")

    # Export variables and run init
    exportResticVars(cfg["backups"][args[0]]["repo"])
    resticInit()

    # Run backup and notify on error
    try:
      bkp = restic.backup(
        tags=[str("restless/" + args[0])],
        paths=cfg["backups"][args[0]]["include"],
        exclude_patterns=cfg["backups"][args[0]]["exclude"]
      )
      logger.info(json.dumps(bkp))
    except Exception as e:
      logger.critical("Backup failed: " + str(e) )
      notifications.notify(title="restless: backup " + args[0] + " failed",body=str(e))
      sys.exit(1)

    # Run prune and notify on error
    try:
      forget = restic.forget(
        group_by="host",
        tags=[str("restless/" + args[0])],
        keep_last=cfg["backups"][args[0]]["keep"]
      )
      logger.info(json.dumps(forget))
    except Exception as e:
      logger.critical("Forget failed: " + str(e) )
      notifications.notify(title="restless: forget for " + args[0] + " failed",body=str(e))
      sys.exit(1)

    # Run post script
    runScript(backup=args[0],stage="post")

  case "replica":
    logger.info('Starting Replication')
  case _:
    logger.critical("Mode " + options.mode + " not supported")
    notifications.notify(title="restless: critical error", body="Unsupported Mode has been requested.")
    sys.exit(1)