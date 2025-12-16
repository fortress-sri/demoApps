## Description
This repository contains FORTRESS demonstration applications and associated support infrastructure.

Note that the code base is oriented toward running the system either on bare metal or within Docker containers (cf., Kubernetes pods).

## Directory Layout
```
    *Ctrl.sh                         # scripts to build, run, and manage the demo apps
    {sat,const}CtrlDebug.sh          # scripts that build 'debug' enabled satellite and constellation apps
    webHook.sh                       # script to configure, scaffold, and run web hook
    {_dockerCtrl,_bareMetal}.sh      # utility scripts sourced by most of above

    Dockerfile.{_3rd,_base,_const,   # template files used to build applications
                _qApp}
    startApp.sh                      # bash script used by edge node containers

    src/python/
        *.py                         # application and support source code
        img/                         # contains flat Earth JPEG displayed by template/index.html (see next)
        template/                    # HTML served by geo_map_server.py
        requirements-*.txt           # pip3 application requirements (baked into top-level Dockerfile.* files)
                                     # and referenced by _bareMetal.sh
    test/
      orbit/
        *.json                       # demo configuration JSON files
      webhook/
        webhook_tun                  # web hook ssh private key
        webhook_tun.pub              # web hook ssh public key
    tmp_patch_bns/                   # script and file used to modify github's Basic_Network_Scanner used by
                                     # the Third Party application
    util/                            # miscellaneous utilities
        test/                        # source geom_utils.sh for commands to interact with geom_map_server.py
        proc_net_tcp.py              # displays /proc/net TCP connections when netstat is unavailable
        WikiTextToHtmlConverter.java # custom java app that converts Markdown to HTML
```

## JSON Configuration File

The JSON configuration file typically resides in `test/orbit/` and specifies

* The number of orbital planes (`num-planes`, `> 0`).
* The number of satellites per plane (`num-sats`, `> 0`).
* Orbital inclination (`inclination` in degrees, `-90..90`); a closed range.
* Initial longitude (`longitude` in degrees, `-180..180`; ignored when inclination is `0` (zero) degrees); a closed range.
* Update interval (`interval` in seconds, `> 0`).
* The location and ports for
    * The `Q Controller`'s
       * `REST API` (`Q-endpoint`) and
       * `ZMQ Publication` (`Q-ZMQ-pub`),
    * Satellite `REST API` endpoints (`endpoint`, `<string>` or `<string>` array):
       * `Flat Earth`'s endpoint,
       * `Table Display`'s `REST API` endpoint,
    * Satellite exfiltration endpoint (`exfilt-endpoint`), and
    * The `Web Hook`'s
       * `REST API` (`WebHook-endpoint`).
    * `Table Display`'s OpenHorizon services `REST API` endpoint (`OH_endpoint`, `<string>`).
   * The Third Party application's Basic Network Scanner mode (`type`).
   * The `Web Hook`'s `ssh` reverse tunnel to the `FORTRESS` DMZ VM (`WebHook-tunnel`).
* Time-Multiplier (`time-multiplier`; `> 0`), real-time scaler (e.g., `100.0` runs the orbit a hundred times faster).
* A list of Hardware-In-the-Loop (HIL) nodes (`HIL`, `dict` with `<host>` as key and `<ordinal>` or `<plane>,<ordinal>` as value).

  Example:

```
    "HIL": {
        "fortress1":     1,
        "fortress2":  "2,2",
        "fortress3":     3,
        "fortress4":  "2,4",
        "fortress5":  "1,5",
        "fortress6":  "2,6",
        "fortress7":     7
    }
```

### REST API Endpoints

The endpoint URL syntax is

```
    http://<host>:<port>/<path>
```

Note that `<path>` *must be globally unique* (viz., not shared between endpoints) because the `*Ctrl*.sh` scripts use
their paths to assign the `host` and `port` to their underlying services.

Satellite endpoints may also have associated intervals, which may be specified by appending `,<interval>` to the URL.  As examples,

```
   "endpoint"="http://fortress21:25250/api/marker,2"
```

and

```
   "endpoint"=["http://fortress21:25250/api/marker",
               "http://fortress21:34142/api/record,15.0"]
```

The last example's first entry's (implicit) `interval` is the global `interval` value.

N.b.: the Flat Earth display endpoint `<path>` is `"api/marker"`, while the Table display endpoint `<path>` is `"api/record"`.

## Set Up

As a convenience, for all `bash` sessions, enter

```
     export JSON_CONF=<JSON configuration>
```
where `<JSON configuration>` resides in `test/orbit/`.

## Building

Given an application script, `{map,orbit,q,sat,table}Ctrl.sh`, enter

```
   ./<app>Ctrl.sh build
```

To build an image from a host not listed in `<JSON configuration>`, enter

```
   ANY_HOST=1 ./<app>Ctrl.sh build
```

For further information, replace `build` with `-h` or `--help`.

## Running

Once an application image is created, you may either `create` or `run` the associated container.

The containers should be started in this order:

1. Q Controller (`./qCtrl.sh run`)
2. Flat Earth display (`./mapCtrl.sh run`) and Table display (`./tableCtrl.sh run`)
3. Constellation (`./constCtrl.sh run`; `./QController.sh stop hil`)
4. Satellites (`./satCtrl.sh run`) and Third Party application (`./thirdCtrl.sh run`)

## Run-Time Control

### `QController.sh`

`QController.sh` communicates with Q Controller service to control the running demonstration.

```
    QController.sh [--help] [<JSON conf>] <command>

    where <command> is
        stop [<node spec>] [<app class>]
                   stops specified application class, where <app class>
                   is 'node', 'sat*', '3rd', 'third*', 'hil', or
                   (implicitly) any
        debug [<node spec>] [disable]
                   enables or disables satellite intervals debug mode
        exfilt [<node spec>] [disable]
                   enables or disables satellite intervals exfiltration
        thirdParty [<node spec>]
                   enables third party nmap application
        info       shows registered satellite intervals
        hil        shows configured Hardware-In-the-Loop (HIL) hosts

    and

        <node spec> is
            <plane range> [<ordinal range>]
          or
            <HIL hostname>

    The ancillary development <command>

        _start     sends start notification to satellites; this is
                   needed when there are fewer running satellites than
                   are specified in the JSON configuration

    If the environment variable, JSON_CONF, is defined, viz.,

       export JSON_CONF=<JSON conf>

    then the <JSON conf> CLI argument is not required.
```

### `*Ctrl*.sh`

`*Ctrl*.sh` scripts build, run, and manage the demo apps.

```
    *Ctrl*.sh [--help] [--force] <command> [<arg>]

    where <command> is
        build    provisionally builds docker image ("<IMAGE>")
        create   provisionally creates container ("<CONTAINER>")
        run      provisionally runs or starts container ("<CONTAINER>")
        stop     stops running container
        restart  restarts running container
        shell    executes an interactive shell in the running container
        log [clear]
                 clears or continuously displays application's console log
        status   displays image and container status
        pause    pauses running container  
        resume   resumes/unpauses container
        signal <signal val>
                 sends signal to running container
        inspect [image]
                 inspects container ("<CONTAINER>") or image ("<IMAGE>")
        bcreate  builds docker image ("<IMAGE>") and creates container ("<CONTAINER>")
        brun     builds docker image ("<IMAGE>") and runs container ("<CONTAINER>")
        lcreate  creates container ("<CONTAINER>") and displays log
        lrun     runs container ("<CONTAINER>") and displays log
    and
        --force  automagically satisfies build, run, and shell command prerequisites

    Note:

        To build an image on a host not specified in the JSON config file,
        run

            ANY_HOST=1 *Ctrl*.sh [--force] build 

        RUNNING ON BARE METAL
        ------- -- ---- -----
        To run *Ctrl*.py directly on a host (cf., inside Docker containers), run

        $_BNAME [--help] (--bare | --metal) [build|prep]

        where
            build  satisfies installation dependencies but does not run *Ctrl*.py
            prep
```
