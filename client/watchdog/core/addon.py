import asyncio
import json
import os
import pathlib
import string
from hashlib import sha256

from watchdog.core.config import Config


def rm(pth):
    if pth.exists():
        for sub in pth.iterdir():
            if sub.is_dir():
                rm(sub)
            else:
                sub.unlink()
        pth.rmdir()


def cleanup():
    if not Config().get("addons.dont_cleanup", False):
        rm(pathlib.Path("./addons"))
    if not pathlib.Path("./addons").exists():
        os.mkdir("./addons")
    with open("./addons/__init__.py", "w") as f:
        f.write("")


class InvalidAddon(Exception):
    pass


# usage of namedtuple here causes error when executing
class InterceptorReference:  # noqa
    def __init__(self, name, path, addonhash):
        self.name = name
        self.path = path
        self.addonhash = addonhash


class AddonReference:
    def __init__(self, name, repo, commit):
        assert set(commit) <= set(string.hexdigits)
        assert set(name) <= set(string.ascii_letters + string.digits + "_-")
        self.name = name
        self.repo = repo
        self.commit = commit
        self.hash = "ba" + sha256("{}|{}|{}".format(name, commit, repo).encode()).hexdigest()[:24]
        self.pathname = "{}".format(self.hash)
        self.path = pathlib.Path("./addons/" + self.pathname)

    def is_installed(self):
        return self.path.exists()

    def uninstall(self):
        rm(self.path)

    def load_metadata(self):
        with (self.path / "addon.json").open() as f:
            data = f.read()
        try:
            return json.loads(data)
        except json.decoder.JSONDecodeError:
            raise InvalidAddon("addon.json is not a valid json file")

    def get_interceptors(self):
        meta = self.load_metadata()
        res = []
        if "interceptors" in meta:
            for name in meta["interceptors"]:
                entry = meta["interceptors"][name]
                clazz = entry["class"]
                assert ".." not in clazz
                assert set(clazz) <= set(string.ascii_letters + string.digits + "_.")
                path = "addons.{}.{}".format(self.pathname, clazz)
                res += [InterceptorReference(name, path, self.hash)]
        return res

    async def install(self):
        assert not self.is_installed()
        assert set(self.commit) <= set(string.hexdigits)
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--recurse-submodules",
            "--",
            self.repo,
            str(self.path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if self.logger:
            await self.logger.verbose(out.decode())
            if proc.returncode != 0:
                await self.logger.error(err.decode())
            else:
                await self.logger.info(err.decode())
        proc = await asyncio.create_subprocess_exec(
            "git",
            "--git-dir",
            str(self.path) + "/.git",
            "config",
            "advice.detachedHead",
            "false",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        proc = await asyncio.create_subprocess_exec(
            "git",
            "--git-dir",
            str(self.path) + "/.git",
            "checkout",
            self.commit,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if self.logger:
            await self.logger.verbose(out.decode())
            if proc.returncode != 0:
                await self.logger.error(err.decode())
            else:
                await self.logger.info(err.decode())
        rm(self.path / ".git")
        with (self.path / "__init__.py").open("w") as f:
            f.write("")
