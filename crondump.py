"Fetch and save gzipped tar files from the local and web instances."

import os
import json

import requests


def fetch_and_save(url, dirpath, apikey):
    "Fetch the gzipped tar file and save to local disk."

    print(f"fetching mdbook.tgz from {url}")
    response = requests.get(url, headers=dict(mdbook_apikey=apikey), stream=True)

    if response.status_code != 200:
        raise ValueError(f"Invalid status code for response: {response.status_code}")
    try:
        content_disposition = response.headers["content-disposition"]
    except KeyError:
        raise ValueError("No content-disposition in response")
    parts = content_disposition.split('"')
    if len(parts) != 3:
        raise ValueError("No filename in content-disposition in response")

    filepath = os.path.join(dirpath, parts[1])
    with open(filepath, "wb") as outfile:
        outfile.write(response.raw.read())
    print(f"wrote mdbook.tgz to {filepath}")


if __name__ == "__main__":
    with open(os.path.join(os.path.dirname(__file__), "crondump.json")) as infile:
        config = json.load(infile)
    for instance in config["instances"]:
        fetch_and_save(instance["url"], instance["dirpath"], config["mdbook_apikey"])
