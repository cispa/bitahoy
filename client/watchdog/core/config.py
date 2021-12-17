import json
import logging
from typing import List, Union


class Config:
    def __init__(self):
        try:
            with open("./config.json") as f:
                # read the config file and strip comments
                self.config = json.loads("".join(list(map(lambda x: "" if x.strip().startswith("//") else x.strip(), f.readlines()))))
        except FileNotFoundError:
            self.config = {}

    def get(self, path: Union[str, List[str]], default=None):
        """
        Get a value from the config file.

        :param path: The path to the value.
        :param default: The default value if the path is not found.
        :return: The value at the path or the default value.
        """
        config = self.config
        if isinstance(path, str):
            sliced_path = path.split(".")
        else:
            sliced_path = path
            if isinstance(path, list) and len(path) == 1:
                logging.warning("DEPRECATED: Use get(path) instead of get([path])")
        for element in sliced_path:
            try:
                config = config[element]
            except (KeyError, TypeError):
                try:
                    config = self.config[path]
                    logging.warning("DEPRECATED: Move variable names with a '.' to their own sub-dictionary.")
                except KeyError:
                    return default
        return config
