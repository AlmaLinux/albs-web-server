# System overview  

AlmaLinux Build System Web-Server (albs-web-server) is designed to control multiple Build System processes like build, sign and release packages. Depending on a request, Web-Server assigns a build from the queue as a task for the [Build Node](https://github.com/AlmaLinux/albs-node) or the [Sign Node](https://github.com/AlmaLinux/albs-sign-node).
Web-server receives a request from the Build Node, and if there is an idle (not started) task, it sends this task to the Build Node. It also works with `failed` and `started` statuses depending on a build result from the Build Node. 
Web-server allows to maintain platforms for builds - you can add a new platform with architectures. Authorization to the Web-server is via GitHub. It makes it possible for a user to maintain builds, create, delete, etc. 
Web-server works with `gitea_listener` and `git_cacher`.

Web-server also works with PULP.

Mentioned tools and libraries are required for ALBS Web-Server to run in the current state:
* PostgreSQL == 13
* Pulp
* Redis
* Nginx
* Docker
* Docker-compose

# Config 

This config file is needed for the Web-Server to launch [gitea-listener](https://github.com/AlmaLinux/gitea-listener):

```
---
mqtt_queue_host: mosquitto
mqtt_queue_port: 1883
mqtt_queue_topic_unmodified: gitea-webhooks-unmodified
mqtt_queue_topic_modified: gitea-webhooks-modified
mqtt_queue_qos: 2
mqtt_client_id: albs_gitea_listener
mqtt_queue_username:
mqtt_queue_password:
mqtt_queue_clean_session: False
albs_jwt_token:
albs_address: http://web_server:8080
```

# Running docker-compose 

You can start the system using the Docker Compose tool.

Pre-requisites:
* `docker` and `docker-compose` tools are installed and set up;

To start the system, run the following command: `docker-compose up -d`. To rebuild images after your local changes, just run `docker-compose up -d --build`.

In case you are building containers for the first time, there is how it should be done:

```
#!/bin/bash

set -e pipefail

mkdir -p volumes/pulp/settings

echo "CONTENT_ORIGIN='http://pulp'
ANSIBLE_API_HOSTNAME='http://pulp'
ANSIBLE_CONTENT_HOSTNAME='http://pulp/pulp/content'
TOKEN_AUTH_DISABLED=True" >> volumes/pulp/settings/settings.py

docker-compose up -d --build --force-recreate --remove-orphans
sleep 25
docker exec -it albs-web-server_pulp_1 bash -c 'pulpcore-manager reset-admin-password --password="admin"'
```

# Create new migration
(inside web_server container)
`PYTHONPATH="." alembic --config alws/alembic.ini revision --autogenerate -m "Migration name"`

# Scheduling tasks 
Web-server works with multiple parts of the Build System. Web-server works with API requests that are divided by usage. 

## build-node

**`POST /ping`** endpoint accepts the following payload: 
```ruby
{
  node_status: { 
    active_tasks: list # accepts a list of integer values;
  } 
}
```
**`POST /build_done`** endpoint accepts the following payload:
```ruby
{
  build_done: {
    task_id: integer # accepts a integer value;
    status: string # accepts literal values that are 'done', 'failed', 'excluded';
    artifacts: {
     name: string # accepts a string value; 
     type: string # accepts literal values that are 'rpm', 'build_log';
     href: string # accepts a string value;
    }     
  }
}
```

**`GET /get_task`** endpoint accepts the following payload: 
```ruby
{
  request: {
     supported_arches: list # accepts a list of string values;
  }
}
```
This endpoint has a response model that returns information about the platform:

```ruby
{
  id: integer # accepts an integer value;
  arch: string # accepts a string value;
  ref: {
    url: string # accepts a string value;
    git_ref: accepts an optional string value # it's an optional value that allows to be absent;
  }
  platform: {
    name: string # accepts a string value;
    type: string # accepts literal values that are 'rpm', 'deb';
    data: dictrionary # dictionary, where a key should be a string while a value could be of any type;
  }
  created_by: {
    name: string # accepts a string value;
    email: string # accepts a string value;
  }
  repositories: string # accepts a list of string values that are 'name' and 'url'; 
  linked_builds: accepts a list of integer values # it's an optional value that allows being absent;
}
```

## builds 

**`POST /`** endpoint accepts the following payload:
```ruby
{
  build: {
    platforms: { # check that a list has at least one item; 
      name: string # accepts a string value;
      arch_list: list # accepts a list of string values;
    }
    tasks: { # check that a list has at least one item; 
      url: string # accepts a string value;
      git_ref: accepts an optional string value # it's an optional value that allows being absent;
    }
    linked_builds: accepts a list of integer values # it's an optional value that allows being absent;
  }
}
```
This endpoint has a response model that returns information about the platform:
```ruby
{
  id: integer # accepts an integer value;
  created_at: datetime # accepts date time like year,month, etc;
  tasks: {
    id: integer # accepts an integer value;
    ts: accepts date time timestamp like year, month, etc # it's an optional value that allows to be absent;
    status: integer # accepts an integer value;
    index: integer # accepts an integer value;
    arch: string #accepts a string value;
    platform: {
      id: integer # accepts an integer value;
      type: string # accepts a string value;
      name: string # accepts a string value;
      arch_list: list # accepts a list of string values;
    }
    ref: {
      url: string # accepts a string value;
      git_ref: accepts an optional string value # it's an optional value that allows to be absent;
    }
    artifacts: {
      id: integer # accepts an integer value;
      name: string # accepts a string value;
      type: string # accepts a string value;
      href: string # accepts a string value;
    }
  } 
  user: {
    id: integer # accepts an integer value;
    username: string # accepts a string value;
    email: string # accepts a string value;
  }
  linked_builds: accepts a list of integer values # it's an optional value that allows being absent;
}
```
        
**`GET /`** this endpoint has a response model that returns one of the options.
It can return a list of platforms: 
```ruby
{
  id: integer # accepts an integer value;
  created_at: datetime # accepts date time like year, month, etc;
  tasks: {
     id: integer # accepts a integer value;
     ts: accepts date time timestamp like year, month, etc # it's an optional value that allows to be absent;
     status: integer # accepts an integer value;
     index: integer # accepts an integer value;
     arch: string # accepts a string value;
     platform: {
       id: integer # accepts an integer value;
       type: string # accepts a string value;
       name: string # accepts a string value
       arch_list: list # accepts a list of a string values;
     }
     ref: {
       url: string # accepts a string value;
       git_ref: optional string value # it's an optional value that allows to be absent;
     }
     artifacts: {
       id: integer # accepts an integer value;
       name: string # accepts a string value;
       type: string # accepts a string value;
       href: string # accepts a string value;
     }
  }
  user: {
     id: integer # accepts an integer value;
     username: string # accepts a string value;
     email: string # accepts a string value;
  }
  linked_builds: string value # it's an optional value that allows being absent;
}
```
or it can return the following information about the platform:
```ruby
{
  builds: {
    id: integer # accepts an integer value;
    created_at: datetime # accepts date time like year, month, etc;
    tasks: {
      id: integer # accepts an integer value;
      ts: datetime timestamp like year, month, etc # it's an optional value that allows to be absent;
      status: integer # accepts an integer value;
      index: integer # accepts an integer value;
      arch: string # accepts a string value;
      platform: {
        id: integer # accepts an integer value;
        type: string # accepts a string value;
        name: string # accepts a string value
        arch_list: list # accepts a list of string values;
      }
     ref: {
       url: string # accepts a string value;
       git_ref: optional string value # it's an optional value that allows to be absent;
     }
     artifacts: {
       id: integer # accepts an integer value;
       name: string # accepts a string value;
       type: string # accepts a string value;
       href: string # accepts a string value;
     }
   }
    user: {
      id: integer # accepts an integer value;
      username: string # accepts a string value;
      email: string # accepts a string value;
    }
    linked_builds: string value # it's an optional value that allows being absent;
  }
  total_builds: optional integer value # it's an optional value that allows being absent;
  current_page: optional integer value # it's an optional value that allows to be absent;
}
```

**`GET /{build_id}/`** endpoint accepts an integer value `build_id `. This endpoint has a response model that returns information about the platform: 
```ruby
{
  id: integer # accepts an integer value;
  created_at: datetime # accepts date time like year, month, etc;
  tasks: {
     id: integer # accepts an integer value;
     ts: date time timestamp like year, month, etc # it's an optional value that allows to be absent;
     status: integer # accepts an integer value;
     index: integer # accepts an integer value;
     arch: string # accepts a string value;
     platform: {
       id: integer # acceptrs an integer value;
       type: string # accepts a string value;
       name: string # accepts a string value
       arch_list: list # accepts a list of string values;
     }
     ref: {
       url: string # accepts string value;
       git_ref: optional string value # it's an optional value that allows to be absent;
     }
     artifacts: {
       id: integer # accepts an integer value;
       name: string # accepts a string value;
       type: string # accepts a string value;
       href: string # accepts a string value;
     }
  }
  user: {
     id: integer # accepts an integer value;
     username: string # accepts a string value;
     email: string # accepts a string value;
  }
  linked_builds: string value # it's an optional value that allows being absent;
}
```

## distributions

**`POST /`** accepts the following payload:
```ruby
{
  distribution: {
    name: string # accepts a string value;
    platforms: list # accepts a list of a string values; 
 }
}
```
This endpoint has a response model that returns information about the platform:
```ruby
{
  id: integer # accepts an integer value;
  name: string # accepts a string value;
}
```

**`POST /add/{build_id}/{distribution}/`** endpoint accepts a string `distribution` value and an integer `build_id` value. This endpoint has a response model that returns a dictionary, where the key should be a string while the value could be of boolean type. 

**`POST /remove/{build_id}/{distribution}/`** endpoint accepts a string `distribution` value and an integer `build_id` value. This endpoint has a response model that returns a dictionary, where the key should be a string while the value could be of boolean type. 

**`GET /`** endpoint has a response model that returns the list of platforms:
```ruby
{
  id: integer # accepts an integer value;
  name: string # accepts a string value;
}
```

## platforms

**`POST /`** endpoint accepts the following payload:
```ruby
{
  name: string # accepts a string value;
  type: literal # accepts literal values that are 'rpm', 'deb';
  distr_type: string # accepts a string value;
  distr_version: string # accepts a string value;
  test_dist_name: string # accepts a string value
  arch_list: list # accepts a list of a string values; 
  repos: {
    name: string # aceppts a string value;
    arch: string # accepts a string value;
    url: string # accepts a string value;
    type: string # accepts a string value;
  }
  data: dictionary # dictionary with a key should be a string while a value could be any type.
}
```
This endpoint has a response model that returns information about the platform:
```ruby
{
  id: integer # accepts an integer value;
  name: string # accepts a string value;
  arch_list: list # accepts list of a string values;
}
```

**`PUT /`** endpoint accepts the following payload:
```ruby
{
  name: strint # accepts a string value;
  type: literal value that is 'rpm' or 'deb' # it's an optional value that allows to be absent;
  distr_type: string value # it's an optional value that allows to be absent;
  distr_version: string value # it's an optional value that allows to be absent;
  arch_list: list of string values # it's an optional value that allows to be absent;
  repos: { # this is optional and allows to be absent; 
    name: string # accepts a string value;
    arch: string # accepts a string value;
    url: string # accepts a string value;
    type: string # accepts a string value;
  }
  data: dictionary, where a key should be a string while a value could be of any type # it's an optional value that allows being absent;
}
```

This endpoint has a response model that returns information about the platform:

```ruby
{
  id: integer # accepts an integer value;
  name: string # accepts a string value;
  arch_list: list # accepts a list of string values;
}
```
        
**`GET /`** has a response model that returns a list of platforms:
```ruby
{
  id: integer # accepts an integer value;
  name: string # accepts a string value;
  arch_list: list # accepts a list of string values;
}
```

## projects

**`GET /alma`** has a response model that returns a list of platforms:
```ruby
{
  name: string # accepts a string value;
  clone_url: string # accepts a string value;
  tags: list # accepts a list of string values; 
  branches: list # accepts a list og string values;
}
```

## tests 

**`POST /{test_task_id}/result/`** endpoint accepts an integer `test_task_id` value and the following payload:
```ruby
{
  result: {
    api_version: string # accepts a string value;
    result: dictionary # a dictionary where a key and a value are of any type;
  }
}
```

**`PUT /build/{build_id}/restart`** endpoint accepts an integer `build_id` value. 

**`PUT /build_task/{build_task_id}/restart`** endpoint accepts an integer `build_task_id` value.

**`GET /{build_task_id}/latest`** endpoint accepts an integer `build_task_id` value. This endpoint has a response model that returns a list of platforms:
```ruby
{
  id: integer # accepts an integer value;
  package_name: string # accepts a string value;
  package_version: string # accepts a string value;
  package_release: string value # it's an optional value that allows to be absent;
  status: integer # accepts an integer value;
  revision: integer # accepts an integer value;
  alts_response: dictionary # a dictionary where a key and a value are of any type;
}
```

**`GET /{build_task_id}/{revision}`** endpoint accepts an integer `build_task_id` value and an integer `revision` value. This endpoint has a response model that returns a list of platforms:
```ruby
{
  id: integer # accepts an integer value;
  package_name: string # accepts a string value;
  package_version: string # accepts a string value;
  package_release: string value # it's an optional value that allows to be absent;
  status: integer # accepts an integer value;
  revision: integer # accepts an integer value;
  alts_response: dictionary # a dictionary where a key and a value are of any type;
}
```

## users

**`POST /login/github`** endpoint accepts the following payload: 
```ruby
{
  user: {
    code: string # accepts a string value;
  }
}
```

This endpoint has a response model that returns information about the platform:
```ruby
{
  id: integer # accepts an integer value;
  username: string # accepts a string value;
  email: string # accepts a string value;
  jwt_token: string # accepts a string value;
}
```

**`GET /`** endpoint has a response model that returns information about the platform:
```ruby
  id: integer # accepts an integer value;
  username: string # accepts a string value;
  email: string # accepts a string value;
```
# Reporting issues 

All issues should be reported to the [Build System project](https://github.com/AlmaLinux/build-system).