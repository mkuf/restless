<p align=center><img src=img/restless-logo.jpeg height=400px></p>

# restless
restless is a wrapper script written in python to create backups via restic and sync snapshots between repos.

## Install
```bash
apt install restic python3-venv

git clone https://github.com/mkuf/restless.git
cd restless
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Configure
Backup and Replica configs are persisted in a yaml file.  
To have a starting point, copy `restless.yaml.example` to a location of your choice.  
By default, restless looks for `restless.yaml` in the current directory where restless is run.

### Notifications
[Apprise](https://github.com/caronc/apprise) is used to send Notifications in case of Issues.  
`.url` specifies the Url to send Notifications to, see https://github.com/caronc/apprise?tab=readme-ov-file#productivity-based-notifications for examples and available notification providers

#### Example
```yaml
notifications:
  url: pover://user@token
```

### Logging
Log file location is defined in `.log.location`, log level via `.log.level`.  
Supported log levels are: 
* debug
* info
* warning
* error
* critical

#### Example
```yaml
log:
  level: info
  location: /var/log/restless.log
```

### Repositories
Each key in the `.repos` map defines the name for a repository that may be referenced by backup or replication jobs. 

The `repository` and `password` keys within the repository definition are required and are the respective values used for `$RESTIC_REPOSITORY` and `$RESTIC_PASSWORD`. Additional environment variables may be defined in the `.env` map.

#### Example
```yaml
repos:
  myrepository:
    repository: s3:https://s3.amazonaws.com/restic-demo
    password: supersecurepassword
    env:
      AWS_DEFAULT_REGION: eu-west-1
      AWS_ACCESS_KEY_ID: IDIDIDIDIDIDIDIDID
      AWS_SECRET_ACCESS_KEY: KEYKEYKEYKEYKEYKEY
```

### Backups
Each key in the `.backups` map defines the name for a job that has to be specified when running restless in backup mode.  

|Key|Description|Type|Default|Required|
|---|-----------|----|-------|--------|
|`.repo`|Name of the repository to use. Defined in `.repositories` on root level|String|`''`|Yes|
|`.retention`|List of Keep-Arguments passed to restic. Used when calling `restic forget`. See [Restic Docs](https://restic.readthedocs.io/en/latest/060_forget.html#removing-snapshots-according-to-a-policy) for Reference|List|`[]`|Yes|
|`.include`|List of Files and Directories that should be included when creating a backup|List|`[]`|Yes|
|`.exclude`|List of exclude patterns that should be applied when creating a backup|List|`[]`|No|
|`.scripts.pre`|Script to run before creating a Backup|String|`''`|No|
|`.scripts.post`|Script to run after a Backup has been created and `restic forget` has been executed|String|`''`|No|

#### Example
```yaml
backups:
  mybackup:
    repo: myrepository
    retention:
    - --keep-hourly 24
    - --keep-daily 7
    - --keep-weekly 4
    include:
    - /home
    - /root
    exclude:
    - .cache
    scripts:
      pre: |
        echo "Mounting Repository disk Writable"
        mount -o remount,rw /data/repo
      post: |
        echo "Mounting Repository disk Readonly"
        mount -o remount,ro /data/repo
```

### Replicas
Each key in the `.replication` map defines the name for a job that has to be specified when running restless in replication mode.  

|Key|Description|Type|Default|Required|
|---|-----------|----|-------|--------|
|`.from`|Name of the Repository from which snapshots should be copied|String|`''`|Yes|
|`.to`|Name of the Repository to which snapshots should be copied|String|`''`|Yes|
|`.include`|List of backups that should be included in the replication job|List|`[]`|Yes|
|`.include[*].backup`|Name of the backup from which snapshots should be synced. Backup Must be located in the `from`-Repository|String|`''`|Yes|
|`.include[*].syncLast`|Nuber of snapshots to sync, starting at the most recent snapshot|Int|`None`|Yes|
|`.include[*].retention`|List of Keep-Arguments passed to restic. Used when calling `restic forget`. See [Restic Docs](https://restic.readthedocs.io/en/latest/060_forget.html#removing-snapshots-according-to-a-policy) for Reference|List|`[]`|Yes|
|`.scripts.pre`|Script to run before replication|String|`''`|No|
|`.scripts.post`|Script to run after replication|String|`''`|No|

#### Example
```yaml
replication:
  myreplica:
    from: local
    to: offsite
    include:
      - backup: daily
        syncLast: 7
        retention:
        - --keep-last 12
      - backup: weekly
        syncLast: 4
        retention:
        - --keep-last 12
    scripts:
      pre: |
        echo "This will run before any restic operations"
      post: |
        echo "This will run after all restic operations"
```

## Run
### Get help
```bash
./venv/bin/python3 restless.py --help

Usage: restless.py [options] <backupname|replicaname>

Options:
  -h, --help            show this help message and exit
  -c CONFIGFILE, --config=CONFIGFILE
                        Path to config file. Default: ./restless.yaml
  -m MODE, --mode=MODE  Execution Mode. Either 'backup' or 'replication'.
                        Default: backup
```

### Create a backup
#### Basic Syntax
```bash
./venv/bin/python3 restless.py --config <path-to-config-file> --mode backup <backup config name>
```
#### Example
```bash
./venv/bin/python3 restless.py --config /etc/restless.yaml --mode backup daily
```

### Sync Repos
#### Basic Syntax
```bash
./venv/bin/python3 restless.py --config <path-to-config-file> --mode replication <replication config name>
```
#### Example
```bash
./venv/bin/python3 restless.py --config /etc/restless.yaml --mode replication weekly
```