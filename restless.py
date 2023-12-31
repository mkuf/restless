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

def runProcess(cmd):
  process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  stdout, stderr = process.communicate()

  logger.debug( "cmd:\n+ " + cmd )
  logger.debug( "out:\n" + stdout.decode('utf-8') )

  if process.returncode != 0:
    logger.error(f"Failure during {cmd} :\n{stdout.decode('utf-8')}")
    raise Exception(stdout.decode('utf-8'))

def runScript(backup,stage):
  try:
    cmd = cfg["backups"][backup]["scripts"][stage]
    try:
      logger.info("Running " + stage + " script for " + backup)
      runProcess(cmd)
    except:
      notifications.notify(title="restless: error", body=stage + " Script for " + backup + " failed.")
      sys.exit(1)
  except KeyError:
    logger.debug("No " + stage + " script set for " + backup)

class restic():
  def export(repo):
    for key,value in cfg["repos"][repo]["vars"].items():
      logger.debug(key + "=" + value)
      os.environ[key]=value

  def init():
    try:
      runProcess("restic init")
    except Exception as e:
      if not str("already exists") in str(e):
        notifications.notify(title="restless: error during init", body=str(e))
        raise e
  
  def backup(backupname):
    cmd = [ "restic", "backup" ] 
    cmd.extend(cfg["backups"][backupname]["include"])
    cmd.extend(["--tag", "restless/" + args[0]])
    for exclude in cfg["backups"][backupname]["exclude"]:
      cmd.extend(["--exclude", exclude])

    try:
      runProcess(' '.join(cmd))
    except Exception as e:
      notifications.notify(title="restless: error during backup", body=str(e))
      sys.exit(1)

  def forget(backupname):
    cmd = ["restic", "forget"]
    cmd.extend(cfg["backups"][args[0]]["retention"])
    cmd.extend(["--tag", "restless/" + args[0]])
    cmd.extend(["--group-by", "host"])

    try:
      runProcess(' '.join(cmd))
    except Exception as e:
      notifications.notify(title="restless: error during forget", body=str(e))
      sys.exit(1)

###
### main
match options.mode:
  case "backup":
    logger.info('Starting Backup')

    # Export variables and run init
    restic.export(cfg["backups"][args[0]]["repo"])
    restic.init()
    runScript(backup=args[0],stage="pre")
    restic.backup(args[0])
    restic.forget(args[0])
    runScript(backup=args[0],stage="post")

  case "replica":
    logger.info('Starting Replication')
  case _:
    logger.critical("Mode " + options.mode + " not supported")
    notifications.notify(title="restless: critical error", body="Unsupported Mode has been requested.")
    sys.exit(1)