"Fetch and save gzipped tar files from the local and web instances."

import os

import requests


def fetch_and_save(url, dirpath):
    "Fetch the gzipped tar file and save to local disk."

    apikey = os.environ["MDBOOK_APIKEY"]

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

    with open(os.path.join(dirpath, parts[1]), "wb") as outfile:
        outfile.write(response.raw.read())


if __name__ == "__main__":
    dirpath = os.environ["MDBOOK_BACKUP_DIR"]
    fetch_and_save("http://0.0.0.0:5001/tgz", os.path.join(dirpath, "local"))
    fetch_and_save("https://mdbook.onrender.com/tgz", os.path.join(dirpath, "web"))
