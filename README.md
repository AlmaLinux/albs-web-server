# System overview

<picture>
  <img alt="Test Coverage" src="https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/andrewlukoshko/082466afa48717ae249ff072a0db02a3/raw/coverage-badge.json">
</picture>
<br/><br/>

AlmaLinux Build System Web-Server (albs-web-server) is designed to control multiple Build System's processes like build, sign and release packages. Web-Server maintains the following functionality:
* Creates, restarts and deletes builds;
* Depending on a request, Web-Server assigns a build from the queue as a task for the [Build Node](https://github.com/AlmaLinux/albs-node), the [Test System](https://github.com/AlmaLinux/alts), the [Sign Node](https://github.com/AlmaLinux/albs-sign-node). When the task is done, Web-Server gathers the result.
  * Web-server receives a request from the Build Node, and if there is an idle (not started) task, it sends this task to the Build Node. It also works with `failed` and `started` statuses depending on a build result from the Build Node. After the build task is successfully completed, the Web Server schedules this task to the Test System.
  * When testing the package is successfully completed, Web-Server sends it to the Sign Node and releases the signed package to production repositories.
* Web-server allows maintaining platforms for builds - you can add a new platform with architectures. It also manages distributions, repositories and signing keys.
* Authorization to the Web-server is via GitHub. 
* Web-Server has the Multilib support via beholder and noarch support to copy noarch packages throughout architectures.
* Web-Server sync production repositories into Build System's Pulp.
* Web-server works with `gitea_listener`, `git_cacher` and Pulp.

Mentioned tools and libraries are required for ALBS Web-Server to run in the current state:
* PostgreSQL 13 - database
* Pulp - artifacts storage (packages, repositories, distributions, etc.)
* Redis - storage for source repositories info and frontend info cache
* Nginx
* Docker
* Docker-compose
* Python 3.9
* FastAPI - REST API framework
* SQLAlchemy - database ORM
* Alembic - database schema migration tool;

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

mkdir -p ../volumes/pulp/settings

echo "CONTENT_ORIGIN='http://pulp'
ANSIBLE_API_HOSTNAME='http://pulp'
ANSIBLE_CONTENT_HOSTNAME='http://pulp/pulp/content'
TOKEN_AUTH_DISABLED=True" >> ../volumes/pulp/settings/settings.py

docker-compose up -d --build --force-recreate --remove-orphans
sleep 25
docker exec -it albs-web-server_pulp_1 bash -c 'pulpcore-manager reset-admin-password --password="admin"'
```

# Scheduling tasks 

Web-server works with multiple parts of the Build System. Web-server works with API requests that are divided by usage. 

## Build-node

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

**`POST /get_task`** endpoint accepts the following payload: 

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
    git_ref: accepts an optional string value # it's an optional value that allows being absent;
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

## Builds 

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
    ts: accepts date time timestamp like year, month, etc # it's an optional value that allows being absent;
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
      git_ref: accepts an optional string value # it's an optional value that allows being absent;
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
       git_ref: optional string value # it's an optional value that allows being absent;
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
       git_ref: optional string value # it's an optional value that allows being absent;
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
  current_page: optional integer value # it's an optional value that allows being absent;
}
```

**`GET /{build_id}/`** endpoint accepts an integer value `build_id `. This endpoint has a response model that returns information about the platform: 

```ruby
{
  id: integer # accepts an integer value;
  created_at: datetime # accepts date time like year, month, etc;
  tasks: {
     id: integer # accepts an integer value;
     ts: date time timestamp like year, month, etc # it's an optional value that allows being absent;
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
       git_ref: optional string value # it's an optional value that allows being absent;
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

**`PATCH /{build_id}/restart-failed`** endpoint accepts an integer value `build_id`. This endpoint has a response model that returns information about the platform: 

```ruby
{
  id: integer # accepts an integer value;
  created_at: datetime # accepts date time like year, month, etc;
  tasks: {
     id: integer # accepts an integer value;
     ts: date time timestamp like year, month, etc # it's an optional value that allows being absent;
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
       git_ref: optional string value # it's an optional value that allows being absent;
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

**`DELETE /{build_id}/remove`** endpoint accepts an integer value `build_id`. This endpoint returns the `'204'` status code.

## Distributions

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

## Platforms

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
  type: literal value that is 'rpm' or 'deb' # it's an optional value that allows being absent;
  distr_type: string value # it's an optional value that allows being absent;
  distr_version: string value # it's an optional value that allows being absent;
  arch_list: list of string values # it's an optional value that allows bein absent;
  repos: { # this is optional and allows being absent; 
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
        
**`GET /`** endpoint has a response model that returns a list of platforms:

```ruby
{
  id: integer # accepts an integer value;
  name: string # accepts a string value;
  arch_list: list # accepts a list of string values;
}
```

**`PATCH /{platform_id}/add-repositories`** endpoint has a response model that returns information about the platform:

```ruby
{
  id: integer # accepts an integer value;
  name: string # accepts a string value;
  arch_list: list # accepts a list of string values;
}
```

**`PATCH /{platform_id}/remove-repositories`**  endpoint has a response model that returns information about the platform:

```ruby
{
  id: integer # accepts an integer value;
  name: string # accepts a string value;
  arch_list: list # accepts a list of string values;
}
```

## Projects

**`GET /alma`** has a response model that returns a list of projects:

```ruby
{
  name: string # accepts a string value;
  clone_url: string # accepts a string value;
  tags: list # accepts a list of string values; 
  branches: list # accepts a list of string values;
}
```

**`GET /alma/modularity`** endpoint has a response model that returns a list of projects:

```ruby
{
  name: string # accepts a string value;
  clone_url: string # accepts a string value;
  tags: list # accepts a list of string values; 
  branches: list # accepts a list of string values;
}
```

## Releases

**`GET /`** has a response model that returns a list of releases:

```ruby
{   id: integer # accepts an integer value;
    status: integer # accepts an integer value;
    build_ids: list # accepts a list of integer values;
    plan: dictionary, where the key should be a string while value can be of any type # it's an optional value that allows being absent;
    created_by: {
        id: integer # accepts an integer value;
        username: string # accepts a string value;
        email: string # accepts a string value;
    }
}
```

**`POST /new/`** endpoint accepts the following payload:

```ruby
{
  builds: list # accepts a list of integer values;
  platform_id: integer # accepts an integer value;
  reference_platform_id: integer # accepts an integer value;
}
```

This endpoint has a response model that returns information about the release:

```ruby
{   id: integer # accepts an integer value;
    status: integer # accepts an integer value;
    build_ids: list # accepts a list of integer values;
    plan: dictionary, where the key should be a string while value can be of any type # it's an optional value that allows being absent;
    created_by: {
        id: integer # accepts an integer value;
        username: string # accepts a string value;
        email: string # accepts a string value;
    }
}
```

**`PUT /{release_id}/`** endpoint accepts an integer value `release_id` and the following payload:

```ruby
{
  builds: optional list value # accepts a list of integer values;
  plan:  dictionary, where the key should be a string while value can be of any type # it's an optional value that allows being absent;
}
```

This endpoint has a response model that returns information about the release:

```ruby
{   id: integer # accepts an integer value;
    status: integer # accepts an integer value;
    build_ids: list # accepts a list of integer values;
    plan: dictionary, where the key should be a string while value can be of any type # it's an optional value that allows being absent;
    created_by: {
        id: integer # accepts an integer value;
        username: string # accepts a string value;
        email: string # accepts a string value;
    }
}
```

**`POST /{release_id}/commit/`** endpoint accepts an integer value `release_id`. This endpoint has a response model that returns the result of the release commit:

```ruby
{
  release: {
    id: integer # accepts an integer value;
    status: integer # accepts an integer value;
    build_ids: list # accepts a list of integer values;
    plan: dictionary, where key should be a string while value can be of any type # it's an optional value that allows being absent;
    created_by: {
        id: integer # accepts an integer value;
        username: string # accepts a string value;
        email: string # accepts a string value;
    }
}
  message: string # accepts a string value;
}
```
        
## Repositories

**`GET /`** endpoint has a response model that returns a list of repositories:

```ruby
{
  id: integer # accepts an integer value;
  name: string # accepts a string value;
  arch: string # accepts a string value;
  url: string # accepts a string  value;
  type: string # accepts a string value;
  debug: optional boolean value # it's an optional value that allows being absent;
  production: optional boolean value # it's an optional value that allows being absent;
  pulp_href: optional boolean value # it's an optional value that allows being absent;
}
```

**`GET /{repository_id}/`** endpoint accepts an integer value `repository_id`. This endpoint has a response model that returns information about the repository or 'None':

```ruby
{
  id: integer # accepts an integer value;
  name: string # accepts a string value;
  arch: string # accepts a string value;
  url: string # accepts a string  value;
  type: string # accepts a string value;
  debug: optional boolean value # it's an optional value that allows being absent;
  production: optional boolean value # it's an optional value that allows being absent;
  pulp_href: optional boolean value # it's an optional value that allows being absent;
}
```

## Sign key

**`GET /`** endpoint has a response model that returns a list of sign keys:

```ruby
{
    id: integer # accepts an integer value;
    name: string # accepts a string value;
    description: string # accepts a string value;
    keyid: string # accepts a string value;
    public_url: string # accepts a string value;
    inserted: datetime # accepts date time like year, month, etc;
}
```

**`POST /new/`** endpoint accepts the following payload:

```ruby
{
    name: string # accepts a string value;
    description: string # accepts a string value;
    keyid: string # accepts a string value;
    fingerprint: string # accepts a string value;
    public_url: string # accepts a string value;
}
```
This endpoint has a response model that returns information about the sign key:

```ruby
{
    id: integer # accepts an integer value;
    name: string # accepts a string value;
    description: string # accepts a string value;
    keyid: string # accepts a string value;
    public_url: string # accepts a string value;
    inserted: datetime # accepts date time like year, month, etc;
}
```


**`PUT /{sign_key_id/`** endpoint accepts an integer value `sign_key_id` and the following payload:

```ruby
{
    name: string value # it's an optional value that allows being absent;
    description: string value # it's an optional value that allows being absent;
    keyid: string value # it's an optional value that allows being absent;
    fingerprint: string value # it's an optional value that allows being absent;
    public_url: string value # it's an optional value that allows being absent;
}
```

This endpoint has a response model that returns information about the sign key:

```ruby
{
    id: integer # accepts an integer value;
    name: string # accepts a string value;
    description: string # accepts a string value;
    keyid: string # accepts a string value;
    public_url: string # accepts a string value;
    inserted: datetime # accepts date time like year, month, etc;
}
```

## Sign task

**`GET /`** endpoint accepts an integer value `build_id`. This endpoint has a response model that returns the list of sign tasks:

```ruby
{
    id: integer # accepts an integer value;
    build_id: integer # accepts an integer value;
    sign_key: {
        id: integer # accepts an integer value;
        name: string # accepts a string value;
        description: string # accepts a string value;
        keyid: string # accepts a string value;
        public_url: string # accepts a string value;
        inserted: datetime # accepts date time like year, month, etc;
    }
    status: integer # accepts an integer value;
    error_message: string value # it's an optional value that allows being absent;
    log_href: string value # it's an optional value that allows being absent;
}
```

**`POST /`** endpoint accepts the following payload:

```ruby
{
    build_id: integer # accepts an integer value;
    sign_key_id: integer # accepts an integer value;
}
```

This endpoint has a response model that returns the sign task:

```ruby
{
    id: integer # accepts an integer value;
    build_id: integer # accepts an integer value;
    sign_key: {
        id: integer # accepts an integer value;
        name: string # accepts a string value;
        description: string # accepts a string value;
        keyid: string # accepts a string value;
        public_url: string # accepts a string value;
        inserted: datetime # accepts date time like year, month, etc;
    }
    status: integer # accepts an integer value;
    error_message: string value # it's an optional value that allows being absent;
    log_href: string value # it's an optional value that allows being absent;
}
```

**`POST /get_sign_task/`** endpoint accepts the following payload:
```ruby
{
    key_ids: string # accepts a list of string values;
}
```

This endpoint has a response model that returns a union of a dictionary with key and value of any type, and the information about available sign tasks:

```ruby
{
    id: integer value # it's an optional value that allows being absent;
    build_id: integer value # it's an optional value that allows being absent;
    keyid: string value # it's an optional value that allows being absent;
    packages: {
        key_ids: a list of string values # it's an optional value that allows being absent;
    }
}
```

**`POST /{sign_task_id}/complete/`** endpoint accepts an integer value `sign_task_id` and the following payload:

```ruby
{
    build_id: integer # accepts an ingeter valut 
    success:  boolean # accepts a boolean value;
    error_message: string value # it's an optional value that allows being absent;
    log_href: string value # it's an optional value that allows being absent;
    packages: {
        key_ids: a list of string values # it's an optional value that allows being absent;
    }
}
```

This endpoint has a response model that returns information about the completed task:

```ruby
{
    success: boolean # accepts a boolean value;
}
```
## Tests 

**`POST /{test_task_id}/result/`** endpoint accepts an integer `test_task_id` value and the following payload:

```ruby
{
  result: {
    api_version: string # accepts a string value;
    result: dictionary # a dictionary where key and value are of any type;
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
  package_release: string value # it's an optional value that allows being absent;
  status: integer # accepts an integer value;
  revision: integer # accepts an integer value;
  alts_response: dictionary # a dictionary where key and value are of any type;
}
```

**`GET /{build_task_id}/{revision}`** endpoint accepts an integer `build_task_id` value and an integer `revision` value. This endpoint has a response model that returns a list of platforms:

```ruby
{
  id: integer # accepts an integer value;
  package_name: string # accepts a string value;
  package_version: string # accepts a string value;
  package_release: string value # it's an optional value that allows being absent;
  status: integer # accepts an integer value;
  revision: integer # accepts an integer value;
  alts_response: dictionary # a dictionary where key and value are of any type;
}
```

## Users

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

**`GET /all_user`** endpoint has a response model that returns information about users:

```ruby
{
    id: integer # accepts an integer value;
    username: string # accepts a string value;
    email: string # accepts a string value;
}
```

# Reporting issues 

All issues should be reported to the [Build System project](https://github.com/AlmaLinux/build-system).
