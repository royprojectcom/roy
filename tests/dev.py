import json
import pathlib
# from roy.utils.collections import update_dict_recur

# TODO: add support for auto task assign per namespace -> we can replace any
# TODO: after postgres rebuild copy data folder
# (stop postgres -> copy folder) -> build new version
# TODO: fix geoip build for nginx (?) do we need this (?) -> probably no
# TODO: we need to mount media folder of all (backend - nginx - nfs (?))
# TODO: migrate data from one server to other

SETTINGS = {'deploy': {
    'env': 'dev',
    'services': {
        'backend': [{
            'hosts': [
                {
                    'name': 'django',
                    'count': 1,
                    'provider': 'vagrant',
                    'cpus': 1,
                    'ram': 512,
                    'vm': 'parallels'
                }
            ],
            'components': {
                'python': {},
                'iptables': {
                    'allow': ['nginx'],
                }
            },
        }],
        'frontend': [{
            'hosts': [
                {
                    'name': 'nginx',
                    'provider': 'vagrant',
                    'cpus': 1,
                    'ram': 512,
                }
            ],
            'components': {
                'nginx': {},
                'iptables': {}
            },
        }],
        'db': [
            {
                'hosts': [
                    {
                        'name': 'postgres',
                        'count': 1,
                        'provider': 'vagrant',
                    }
                ],
                'components': {
                    'postgres': {},
                    'iptables': {
                        'allow': ['python']
                    }
                }
            },
            {
                'hosts': [
                    {
                        'name': 'redis',
                        'count': 1,
                        'provider': 'vagrant',
                    }
                ],
                'components': {
                    'redis': {'listen_private_ip': False},
                    'iptables': {
                        'allow': ['python']
                    }
                }
            }
        ]
    }
}}
