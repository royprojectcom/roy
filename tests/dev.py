import json
import pathlib

SETTINGS = {'deploy': {
    'env': 'roy-dev',
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
