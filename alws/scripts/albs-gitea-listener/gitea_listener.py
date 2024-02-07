#!/usr/bin/env python3
# -*- mode:python; coding:utf-8; -*-
# author: Mariia Boldyreva <mboldyreva@cloudlinux.com>
# created: 2021-09-03

"""
AlmaLinux Build System Gitea queue listener.
"""

import urllib
import json
import os
import logging
import requests
import re
from redis import asyncio as aioredis
import asyncio
import traceback
from ruamel.yaml import YAML

from paho.mqtt import client as mqtt_client
from gitea_models import GiteaListenerConfig, PushedEvent
from git_cacher import load_redis_cache, save_redis_cache

LOGGER: logging.Logger


async def get_gitea_cache(redis_client, redis_key):
    cached_data = await load_redis_cache(redis_client, redis_key)
    return cached_data


async def save_gitea_cache(redis_client, redis_key, new_cache):
    updated_cache = await save_redis_cache(redis_client, redis_key, new_cache)
    return updated_cache


def connect_mqtt(config: GiteaListenerConfig) -> mqtt_client:

    """
    Connection to MQTT Gitea Listener queue.

    Parameters
    ----------
    config : GiteaListenerConfig
        Gitea Listener Configuration.

    Returns
    -------
    MQTT connected client.
    """

    LOGGER.info('Connecting to the MQTT Queue...')

    def on_connect(client, userdata, flags, rc):

        """
        The broker response to new connection request.

        Parameters
        ----------
        client : MQTT Client
            The client instance for this callback.
        userdata :
            The private user data as set in Client().
        flags :
            Response flags sent by the broker.
        rc : int
            The connection result.
        """

        if rc == 0:
            LOGGER.info(f'Connected OK. Returned code={rc}')
        else:
            LOGGER.info(f'Bad connection. Returned code={rc}')

    client = mqtt_client.Client(client_id=config.mqtt_client_id,
                                clean_session=config.mqtt_queue_clean_session)
    client.username_pw_set(username=config.mqtt_queue_username,
                           password=config.mqtt_queue_password)
    client.on_connect = on_connect
    client.connect(config.mqtt_queue_host, config.mqtt_queue_port)
    return client


def create_build(received_data: PushedEvent,
                 config: GiteaListenerConfig) -> str:

    """
    Create a new build in AlmaLinux Build System from received new
    event in Gitea.

    Parameters
    ----------
    received_data : PushedEvent
        Validated new event from Gitea Listener.

    config : GiteaListenerConfig
        Gitea Listener Configuration.

    Returns
    -------
    str
        Created build's identifier.
    """

    git_url = received_data.repository.clone_url
    git_ref = re.sub('refs/tags/', '', received_data.ref)
    build_query = {
        'platforms': ['Alma84'],
        'tasks': [
            {
                # this is only for local dev testing
                # 'url': git_url.replace('localhost', '192.168.1.118'),
                'url': git_url,
                'git_ref': git_ref
            }
        ]
    }
    url = urllib.parse.urljoin(config.albs_address,
                               '/api/v1/builds/')
    headers = {'authorization': f'Bearer {config.albs_jwt_token}'}
    response = getattr(requests, 'post')(
        url, json=build_query, headers=headers
    )
    response.raise_for_status()
    return response.json()['id']


def subscribe(client: mqtt_client, config: GiteaListenerConfig):

    """
    Listener for new events in MQTT Gitea queue.

    client: MQTT Client
        Connected MQTT Client.
    config: GiteaListenerConfig.
        Gitea Listener Configuration.
    """

    def on_message(client, userdata, msg):

        """
        Receives a new message from MQTT queue and
        creates a new build out of its data.

        Parameters
        ----------
        client : MQTT Client
            The client instance for this callback.
        userdata :
            The private user data as set in Client().
        msg : MQTT Message
            Received message from MQTT queue.
        """

        try:
            received = json.loads(msg.payload.decode())
            received = PushedEvent(**received)
            LOGGER.info(f'Received new event from {msg.topic} topic: '
                        f'ref {received.ref} commit {received.after} '
                        f'from repository {received.repository.name}')
            LOGGER.info('Checking gitea cache')
            redis_client = aioredis.from_url(config.redis_host)
            redis_key = config.redis_cache_key
            loop = asyncio.get_event_loop()
            gitea_cache = loop.run_until_complete(get_gitea_cache(
                redis_client, redis_key))
            try:
                repo = received.repository.full_name
                if 'tags' in received.ref:
                    LOGGER.info('Making a new build for found new tag...')
                    git_ref = re.sub('refs/tags/', '', received.ref)
                    if received.ref not in gitea_cache[repo]['tags']:
                        gitea_cache[repo]['tags'].append(git_ref)
                    created = create_build(received, config)
                    LOGGER.info(f'Build {created} was successfully created')
                else:
                    if 'heads' in received.ref:
                        git_ref = re.sub('refs/heads/', '', received.ref)
                        if received.ref not in gitea_cache[repo]['branches']:
                            gitea_cache[repo]['branches'].append(git_ref)
                    LOGGER.info('Skipping new commit')

                loop.run_until_complete(save_gitea_cache(redis_client,
                                                         redis_key,
                                                         gitea_cache))

            except Exception as error:
                LOGGER.error(f'Failed to create a build. Traceback: {error}')
                LOGGER.error(traceback.format_exc())
                client.reconnect()

        except Exception as error:
            LOGGER.error(f'Failed to receive new event from {msg.topic} topic.'
                         f'\nTraceback: {error}')
            LOGGER.error(traceback.format_exc())
            client.reconnect()

    client.subscribe([(config.mqtt_queue_topic_unmodified,
                       config.mqtt_queue_qos),
                      (config.mqtt_queue_topic_modified,
                       config.mqtt_queue_qos)])
    client.on_message = on_message


def run():

    """
    Launches AlmaLinux gitea listener for builds creation.
    """

    config_path = os.path.abspath(os.path.expanduser(
        os.path.expandvars('albs-gitea-listener-config.yaml')))
    loader = YAML(typ='safe')
    with open(config_path, 'rt') as config_file:
        gitea_config = GiteaListenerConfig.parse_obj(loader.load(config_file))

    global LOGGER
    logging.basicConfig(level='INFO')
    LOGGER = logging.getLogger(gitea_config.mqtt_client_id)
    client = connect_mqtt(gitea_config)
    subscribe(client, gitea_config)
    client.loop_forever()


if __name__ == '__main__':
    run()
