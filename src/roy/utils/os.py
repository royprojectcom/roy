import os
import pwd
import asyncio
import pathlib


class RunInShellError(Exception):
    pass


def get_username() -> str:
    return pwd.getpwuid(os.getuid())[0]


def get_homepath() -> pathlib.Path:
    return pathlib.Path(os.path.expanduser('~'))


async def run_in_shell(command: str, interactive: bool = False) -> str:
    stdout = stderr = asyncio.subprocess.PIPE
    if interactive:
        stdout = stderr = None
    proc = await asyncio.create_subprocess_shell(
        command, stdout=stdout, stderr=stderr
    )
    stdout, stderr = await proc.communicate()
    if stderr and proc.returncode != 0:
        raise RunInShellError(
            f'Shell command "{command}" finished with '
            f'error code [{proc.returncode}]:\n'
            f'{stderr.decode()} '
        )
    if stdout:
        return stdout.decode()
