import os

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
                    'provider': 'vultr',
                    'ssh-key': '3e0b30d7-0a41-434b-affa-0e67f8af0eef',
                    'key': os.environ['VULTR_API_KEY']
                }
            ],
            'components': {
                'python': {
                    'systemd': {
                        'instances': {'count': 1}
                    }
                },
                'iptables': {
                    'allow': ['nginx'],
                }
            },
        }],
        'frontend': [{
            'hosts': [
                {
                    'name': 'nginx',
                    'count': 0,
                    'provider': 'vultr',
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
                        'count': 0,
                        'provider': 'vultr',
                    }
                ],
                'components': {
                    'postgres': {},
                    'iptables': {
                        'allow': ['python']
                    }
                }
            },
        ],
        'cache': [
            {
                'hosts': [
                    {
                        'name': 'redis',
                        'count': 0,
                        'provider': 'vultr',
                    }
                ],
                'components': {
                    'redis': {'listen_private_ip': True},
                    'iptables': {
                        'allow': ['python']
                    }
                }
            }
        ]
    }
}}
