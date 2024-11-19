"Permissions handling; attribute-based access control."

from pathlib import Path

from json_logic import jsonLogic


class Permissions:
    "Permissions handling; attribute-based access control."

    def __init__(self, filepath):
        self.filepath = filepath
        self.read()

    def read(self):
        "Read the global database."
        raise NotImplementedError

    def write(self):
        "Write the global database."
        raise NotImplementedError

    def __call__(self, user, resource, action, context):
        "Is the  action on the resource allowed for the user in the context?"
        raise NotImplementedError


if __name__ == "__main__":
    expression = {"==": [1, 1]}
    print(jsonLogic(expression))
    expression = {"==": [{"var": "user.name"}, "pekrau"]}
    data = {"user": {"name": "pekrau"}}
    print(jsonLogic(expression, data))
    
