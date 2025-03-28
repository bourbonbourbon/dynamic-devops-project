# dynamic-devops-project
[![Dynamic DevOps Roadmap](https://devopshive.net/badges/dynamic-devops-roadmap.svg)](https://github.com/DevOpsHiveHQ/dynamic-devops-roadmap)

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/bourbonbourbon/dynamic-devops-project/badge)](https://scorecard.dev/viewer/?uri=github.com/bourbonbourbon/dynamic-devops-project)

### Setup
1. .env file
```
PORT="8080"
HOST="0.0.0.0"
SENSEBOXES="5eba5fbad46fb8001b799786,5a77184229b729001a150c10,6448d061258367000707ec8b,5e5fc72957703e001b7b1f0a,5eb3d2ea9724e9001ce71aa9,5f70d5b9a98020001bbd2c89"
MURL="localhost:9000"
MAK="ROOTUSER"
MSK="CHANGEME123"
MBUCKET="avg-temp"
MOBJECT="avg-temp"
VKURL="localhost"
VKPORT="6379"
```
2. Build the docker file
3. docker run -p 8080:8080 imagename:tag